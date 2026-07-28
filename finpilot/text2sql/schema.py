# -*- coding: utf-8 -*-
"""
财务数据库 Schema 定义
- 表结构映射、中英文指标→列映射、派生指标公式
- 提供年份/期间提取与给 LLM 的 schema 上下文生成

板块F：schema 反射。``build_schema_context`` 不再只读下方硬编码 dict，
而是先用 ``sqlalchemy.inspect`` 反射真实数据库的列/类型/外键，再叠加本文件中的
中文说明作为"语义增强层"。反射结果按 engine 做模块级缓存，避免每次 LLM 调用
都重新 introspect。硬编码 dict 仍保留，用于：
  1) 反射失败时的降级 schema；
  2) 给反射出的裸列名补充中文释义（反射拿不到注释）；
  3) 指标→列映射 / 派生指标公式等业务语义。
"""
import re
from typing import Optional

from sqlalchemy import inspect

# 财务数据库表结构：表名 -> {列名: 列说明}
# 板块F：补齐与 ORM(database/models.py FinancialReport/FinancialAccount)的偏差字段
# （tenant_id / document_id / data_json 此前缺失，导致 LLM 生成的 SQL 不会按租户/文档过滤）。
FINANCIAL_TABLES: dict[str, dict[str, str]] = {
    "financial_reports": {
        "id": "主键ID",
        "tenant_id": "租户ID（多租户隔离，查询时应按租户过滤）",
        "report_name": "报表名称",
        "company_name": "公司名称",
        "ticker": "股票代码",
        "report_type": "报表类型(balance_sheet/income_statement/cash_flow)",
        "period": "报表期间，如 2024-Q1 / 2024-FY",
        "data_json": "报表原始数据(JSON 文本，一般不直接查询)",
        "document_id": "溯源文档ID(关联 documents.id)",
        "created_at": "创建时间",
    },
    "financial_accounts": {
        "id": "主键ID",
        "report_id": "关联 financial_reports.id",
        "account_name": "会计科目名称",
        "account_category": "科目分类(收入/利润/资产/负债/所有者权益等)",
        "period": "期间",
        "debit_amount": "借方金额",
        "credit_amount": "贷方金额",
        "balance": "余额",
    },
}

# 中英文指标 -> 列名 + 科目分类过滤条件
# category 支持 list 表示多分类匹配（适配种子数据的细分类）
METRIC_TO_COLUMN: dict[str, dict] = {
    "营业收入": {"column": "financial_accounts.balance", "category": ["营业收入"]},
    "revenue": {"column": "financial_accounts.balance", "category": ["营业收入"]},
    "营业成本": {"column": "financial_accounts.balance", "category": ["营业成本费用"]},
    "净利润": {"column": "financial_accounts.balance", "category": ["利润"]},
    "net_income": {"column": "financial_accounts.balance", "category": ["利润"]},
    "利润总额": {"column": "financial_accounts.balance", "category": ["利润"]},
    "总资产": {"column": "financial_accounts.balance", "category": ["流动资产", "非流动资产"]},
    "total_assets": {"column": "financial_accounts.balance", "category": ["流动资产", "非流动资产"]},
    "流动资产": {"column": "financial_accounts.balance", "category": ["流动资产"]},
    "非流动资产": {"column": "financial_accounts.balance", "category": ["非流动资产"]},
    "负债": {"column": "financial_accounts.balance", "category": ["流动负债", "非流动负债"]},
    "liabilities": {"column": "financial_accounts.balance", "category": ["流动负债", "非流动负债"]},
    "流动负债": {"column": "financial_accounts.balance", "category": ["流动负债"]},
    "非流动负债": {"column": "financial_accounts.balance", "category": ["非流动负债"]},
    "所有者权益": {"column": "financial_accounts.balance", "category": ["所有者权益"]},
    "equity": {"column": "financial_accounts.balance", "category": ["所有者权益"]},
}

# 派生指标计算公式（展示与上下文用，规则引擎据此生成聚合 SQL）
DERIVED_METRICS: dict[str, str] = {
    "资产负债率": "负债/总资产*100",
    "毛利率": "(营业收入-营业成本)/营业收入*100",
    "ROE": "净利润/所有者权益*100",
}


def extract_year(text: str) -> str | None:
    """从问题文本中提取 4 位年份（如 2024）"""
    m = re.search(r"(20\d{2})", text)
    return m.group(1) if m else None


def extract_period(text: str) -> str | None:
    """提取报表期间：Q1~Q4 / FY(年报) / H1(半年报)"""
    # 第X季度 / X季度 / Q1
    m = re.search(r"第?\s*([1-4])\s*季度?", text)
    if m:
        return f"Q{m.group(1)}"
    m = re.search(r"q([1-4])", text, re.IGNORECASE)
    if m:
        return f"Q{m.group(1)}"
    # 半年报/中报需先于"年报"判断，避免"半年报"被"年报"子串误匹配
    if "半年报" in text or "中报" in text:
        return "H1"
    if "年报" in text or "年度报告" in text or re.search(r"\bFY\b", text, re.IGNORECASE):
        return "FY"
    return None


# ── 板块F：schema 反射 + 缓存 ───────────────────────────────────────────────
# 按 engine 身份(id)缓存反射后的 schema 文本，避免每次 LLM 调用都 introspect。
_SCHEMA_CACHE: dict[int, str] = {}


def invalidate_schema_cache(engine=None) -> None:
    """失效 schema 缓存。engine=None 清空全部；否则只清该 engine 的条目。

    在建表/补列/迁移后调用，确保下一次 build_schema_context 重新反射。
    """
    if engine is None:
        _SCHEMA_CACHE.clear()
    else:
        _SCHEMA_CACHE.pop(id(engine), None)


def _resolve_engine(engine=None):
    """engine=None 时回退到主库 engine（finpilot.database.connection.engine）。"""
    if engine is not None:
        return engine
    from finpilot.database.connection import engine as _default_engine
    return _default_engine


def reflect_db_schema(engine=None) -> dict[str, list[dict]]:
    """反射白名单表的真实列结构。

    返回 {table: [{name, type, nullable, fk, comment}, ...]}。
    反射失败（engine 不可用/表不存在）时，降级为 FINANCIAL_TABLES 的键值，
    保证 build_schema_context 永远有内容可输出。
    """
    eng = _resolve_engine(engine)
    result: dict[str, list[dict]] = {}
    try:
        insp = inspect(eng)
        existing = set(insp.get_table_names())
    except Exception:  # noqa: BLE001  反射失败走降级
        existing = set()

    for table, comments in FINANCIAL_TABLES.items():
        cols: list[dict] = []
        if table in existing:
            try:
                fk_map: dict[str, str] = {}
                for fk in insp.get_foreign_keys(table):
                    constrained = fk.get("constrained_columns") or []
                    ref_table = fk.get("referred_table", "")
                    ref_cols = fk.get("referred_columns") or []
                    for c in constrained:
                        fk_map[c] = f"-> {ref_table}({'/'.join(ref_cols)})"
                for col in insp.get_columns(table):
                    name = col.get("name", "")
                    cols.append({
                        "name": name,
                        "type": str(col.get("type", "")),
                        "nullable": bool(col.get("nullable", True)),
                        "fk": fk_map.get(name, ""),
                        "comment": comments.get(name, ""),
                    })
            except Exception:  # noqa: BLE001  单表反射失败用硬编码兜底
                cols = []
        # 反射没拿到列时，用硬编码 dict 兜底
        if not cols:
            for name, comment in comments.items():
                cols.append({
                    "name": name, "type": "", "nullable": True,
                    "fk": "", "comment": comment,
                })
        result[table] = cols
    return result


def build_schema_context(engine=None) -> str:
    """生成提供给 LLM 的 schema 描述文本（反射真实结构 + 中文语义层 + 缓存）。

    输出包含：表名、列名、列类型、是否可空、外键、中文释义、指标→列映射、
    派生指标公式、查询约束。反射结果按 engine 缓存。
    """
    eng = _resolve_engine(engine)
    cached = _SCHEMA_CACHE.get(id(eng))
    if cached is not None:
        return cached

    schema = reflect_db_schema(eng)
    lines = ["# 财务数据库 Schema", ""]
    for table, cols in schema.items():
        lines.append(f"## 表 {table}")
        for c in cols:
            parts = [f"{c['name']}"]
            if c["type"]:
                parts.append(c["type"])
            if not c["nullable"]:
                parts.append("NOT NULL")
            if c["fk"]:
                parts.append(c["fk"])
            desc = c["comment"]
            line = "- " + " | ".join(parts)
            if desc:
                line += f"  # {desc}"
            lines.append(line)
        lines.append("")
    lines.append("## 指标到列映射")
    for metric, info in METRIC_TO_COLUMN.items():
        lines.append(f"- {metric} -> {info['column']} (account_category='{info['category']}')")
    lines.append("")
    lines.append("## 派生指标公式")
    for metric, formula in DERIVED_METRICS.items():
        lines.append(f"- {metric} = {formula}")
    lines.append("")
    lines.append("## 约束")
    lines.append("- 仅允许 SELECT 语句，禁止任何写操作")
    lines.append("- financial_accounts 通过 report_id 关联 financial_reports.id")
    lines.append("- 公司名在 financial_reports.company_name，期间在 period 字段")
    lines.append("- 科目分类在 financial_accounts.account_category")
    lines.append("- financial_reports.tenant_id 用于多租户隔离，跨租户查询应带 tenant_id 过滤")
    text = "\n".join(lines)
    _SCHEMA_CACHE[id(eng)] = text
    return text
