# -*- coding: utf-8 -*-
"""
财务数据库 Schema 定义
- 表结构映射、中英文指标→列映射、派生指标公式
- 提供年份/期间提取与给 LLM 的 schema 上下文生成
"""
import re

# 财务数据库表结构：表名 -> {列名: 列说明}
FINANCIAL_TABLES: dict[str, dict[str, str]] = {
    "financial_reports": {
        "id": "主键ID",
        "report_name": "报表名称",
        "company_name": "公司名称",
        "ticker": "股票代码",
        "report_type": "报表类型(balance_sheet/income_statement/cash_flow)",
        "period": "报表期间，如 2024-Q1 / 2024-FY",
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


def build_schema_context() -> str:
    """生成提供给 LLM 的 schema 描述文本"""
    lines = ["# 财务数据库 Schema", ""]
    for table, columns in FINANCIAL_TABLES.items():
        lines.append(f"## 表 {table}")
        for col, desc in columns.items():
            lines.append(f"- {col}: {desc}")
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
    return "\n".join(lines)
