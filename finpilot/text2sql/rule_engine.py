# -*- coding: utf-8 -*-
"""
规则引擎
- 基于关键词模板匹配生成 SQL
- 覆盖：公司+指标查询 / 派生指标 / 多公司对比
- 命中固定置信度 0.7，无法匹配返回 confidence=0
"""
import re

from .engine import NL2SQLResult
from .schema import (
    METRIC_TO_COLUMN,
    DERIVED_METRICS,
    extract_year,
    extract_period,
)

# 规则引擎命中置信度
_RULE_CONFIDENCE = 0.7

# 公司名常见后缀（长在前，逐个剥离得到核心名用于 LIKE 模糊匹配）
_COMPANY_SUFFIXES = [
    "股份有限公司", "有限责任公司", "有限公司", "集团公司", "控股", "集团", "公司",
]


class RuleBasedEngine:
    """基于关键词模板的规则引擎"""

    def generate_sql(self, question: str) -> NL2SQLResult:
        # 1. 多公司对比："对比XX和YY的净利润"
        result = self._match_comparison(question)
        if result is not None:
            return result

        # 2. 派生指标："资产负债率"/"毛利率"/"ROE"
        result = self._match_derived_metric(question)
        if result is not None:
            return result

        # 3. 公司 + 基础指标："XX公司营业收入"
        result = self._match_company_metric(question)
        if result is not None:
            return result

        # 无法匹配
        return NL2SQLResult(
            sql="",
            confidence=0.0,
            backend="rule",
            explanation="规则引擎无法匹配该问题",
        )

    @staticmethod
    def _escape(value: str) -> str:
        """转义 SQL 字符串中的单引号，防止注入"""
        return value.replace("'", "''")

    @staticmethod
    def _company_core(raw: str) -> str:
        """剥离公司名常见后缀，得到核心名用于 LIKE 模糊匹配
        例: '阿里巴巴公司' -> '阿里巴巴'，'示例科技有限公司' -> '示例科技'"""
        name = raw
        changed = True
        while changed:
            changed = False
            for suffix in _COMPANY_SUFFIXES:
                if name.endswith(suffix) and len(name) > len(suffix):
                    name = name[: -len(suffix)]
                    changed = True
                    break
        return name or raw

    @staticmethod
    def _period_conds(question: str, column: str = "period") -> list[str]:
        """从问题提取年份/期间，构造 period 过滤条件片段"""
        year = extract_year(question)
        period = extract_period(question)
        conds: list[str] = []
        if year and period:
            conds.append(f"{column} LIKE '{year}-{period}%'")
        elif year:
            conds.append(f"{column} LIKE '{year}%'")
        elif period:
            conds.append(f"{column} LIKE '%{period}%'")
        return conds

    def _match_comparison(self, question: str) -> NL2SQLResult | None:
        """对比模式：对比XX和YY的<指标>"""
        m = re.search(r"对比(.+?)[和与跟](.+?)的(.+)", question)
        if not m:
            return None

        company_a = self._escape(self._company_core(m.group(1).strip()))
        company_b = self._escape(self._company_core(m.group(2).strip()))
        metric_text = m.group(3).strip()

        # 查找指标
        info = None
        for metric, mi in METRIC_TO_COLUMN.items():
            if metric in metric_text:
                info = mi
                break
        if info is None:
            return None

        category = info["category"]
        # category 支持 list（如总资产=流动资产+非流动资产），拼接为 IN 条件
        if isinstance(category, list):
            cat_list = ",".join("'" + c + "'" for c in category)
            cat_cond = f"fa.account_category IN ({cat_list})"
        else:
            cat_cond = f"fa.account_category='{category}'"
        metric_like = self._escape(metric_text)
        period_conds = self._period_conds(question, "fa.period")

        # 子查询取各公司对应科目余额，外层按公司名过滤两公司
        where_extra = "".join(f" AND {c}" for c in period_conds)
        sql = (
            "SELECT fr.company_name, "
            f"(SELECT fa.balance FROM financial_accounts fa "
            f"WHERE fa.report_id = fr.id AND {cat_cond} "
            f"AND fa.account_name LIKE '%{metric_like}%'{where_extra}) AS {metric_like} "
            "FROM financial_reports fr "
            f"WHERE fr.company_name LIKE '%{company_a}%' "
            f"OR fr.company_name LIKE '%{company_b}%'"
        )
        return NL2SQLResult(
            sql=sql,
            confidence=_RULE_CONFIDENCE,
            backend="rule",
            explanation=f"规则匹配:对比 {company_a} 与 {company_b} 的 {metric_text}",
            params={"company_a": company_a, "company_b": company_b, "metric": metric_text},
        )

    def _match_derived_metric(self, question: str) -> NL2SQLResult | None:
        """派生指标模式：资产负债率 / 毛利率 / ROE"""
        target = None
        for metric in DERIVED_METRICS:
            if metric in question:
                target = metric
                break
        if target is None:
            return None

        period_conds = self._period_conds(question)
        where_clause = (" WHERE " + " AND ".join(period_conds)) if period_conds else ""

        # 各派生指标的条件聚合 SQL
        if target == "资产负债率":
            sql = (
                "SELECT "
                "SUM(CASE WHEN account_category IN ('流动负债','非流动负债') THEN balance ELSE 0 END) * 100.0 / "
                "NULLIF(SUM(CASE WHEN account_category IN ('流动资产','非流动资产') THEN balance ELSE 0 END), 0) AS 资产负债率 "
                f"FROM financial_accounts{where_clause}"
            )
        elif target == "毛利率":
            sql = (
                "SELECT "
                "(SUM(CASE WHEN account_category='营业收入' THEN balance ELSE 0 END) "
                "- SUM(CASE WHEN account_name LIKE '%营业成本%' THEN balance ELSE 0 END)) * 100.0 / "
                "NULLIF(SUM(CASE WHEN account_category='营业收入' THEN balance ELSE 0 END), 0) AS 毛利率 "
                f"FROM financial_accounts{where_clause}"
            )
        elif target == "ROE":
            sql = (
                "SELECT "
                "SUM(CASE WHEN account_category='利润' THEN balance ELSE 0 END) * 100.0 / "
                "NULLIF(SUM(CASE WHEN account_category='所有者权益' THEN balance ELSE 0 END), 0) AS ROE "
                f"FROM financial_accounts{where_clause}"
            )
        else:
            return None

        return NL2SQLResult(
            sql=sql,
            confidence=_RULE_CONFIDENCE,
            backend="rule",
            explanation=f"规则匹配:派生指标 {target} ({DERIVED_METRICS[target]})",
            params={"derived_metric": target},
        )

    def _match_company_metric(self, question: str) -> NL2SQLResult | None:
        """公司 + 基础指标模式：XX公司营业收入"""
        # 查找基础指标
        metric_key, info = None, None
        for metric, mi in METRIC_TO_COLUMN.items():
            if metric in question:
                metric_key, info = metric, mi
                break
        if info is None:
            return None

        category = info["category"]
        # 提取公司名（以"公司"结尾的片段），剥离后缀得核心名用于模糊匹配
        m = re.search(r"([\u4e00-\u9fa5A-Za-z0-9·]+公司)", question)
        company = self._escape(self._company_core(m.group(1))) if m else None

        metric_like = self._escape(metric_key)
        # category 支持 list，拼接为 IN 条件
        if isinstance(category, list):
            cat_list = ",".join("'" + c + "'" for c in category)
            cat_cond = f"account_category IN ({cat_list})"
        else:
            cat_cond = f"account_category='{category}'"
        conds = [cat_cond, f"account_name LIKE '%{metric_like}%'"]
        if company:
            conds.append(
                f"report_id IN (SELECT id FROM financial_reports "
                f"WHERE company_name LIKE '%{company}%')"
            )
        # 期间过滤
        conds.extend(self._period_conds(question))

        where_sql = " AND ".join(conds)
        sql = f"SELECT balance FROM financial_accounts WHERE {where_sql}"
        return NL2SQLResult(
            sql=sql,
            confidence=_RULE_CONFIDENCE,
            backend="rule",
            explanation=f"规则匹配:{company or '全部公司'}的 {metric_key}",
            params={"company": company or "", "metric": metric_key},
        )
