"""模拟企业财务数据集。

设计原则：
- **覆盖 5 类企业形态**：startup / growth / mature / declining / fraudulent
- **覆盖 3 个行业**：manufacturing / retail / technology
- **覆盖 3 种货币**：CNY / USD / EUR（用于汇率校验）
- **每家公司提供**：基础信息 + 年度三表（资负/利润/现金流）+ 月度营收 + 凭证 + 应收 +
  关联交易 + 时序指标
- **所有数据为虚构**，仅用于演示与极限测试

共 15 家公司（5 形态 × 3 行业），可用 ``list_companies()`` 查询，``get_company(id)`` 取详情。
"""
from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# 数据维度
# ---------------------------------------------------------------------------

STAGES = ("startup", "growth", "mature", "declining", "fraudulent")
INDUSTRIES = ("manufacturing", "retail", "technology")
CURRENCIES = ("CNY", "USD", "EUR")


def list_stages() -> list[str]:
    return list(STAGES)


def list_industries() -> list[str]:
    return list(INDUSTRIES)


# ---------------------------------------------------------------------------
# 15 家虚拟公司：5 形态 × 3 行业
# 命名约定：FP-{stage[:2]}-{industry[:2]}-{seq}
# ---------------------------------------------------------------------------

_COMPANIES: list[dict[str, Any]] = [
    # ===== startup =====
    {
        "id": "FP-ST-MA-01",
        "name": "晨星智造有限公司",
        "stage": "startup",
        "industry": "manufacturing",
        "currency": "CNY",
        "fiscal_year": 2024,
        "metrics": {
            "revenue": 12_000_000,
            "net_profit": -3_500_000,
            "total_assets": 8_000_000,
            "total_liabilities": 6_500_000,
            "current_assets": 3_000_000,
            "current_liabilities": 4_500_000,
            "inventory": 1_500_000,
            "accounts_receivable": 2_800_000,
            "operating_cash_flow": -2_000_000,
            "gross_margin": 0.18,
            "net_margin": -0.29,
            "debt_ratio": 0.81,
            "current_ratio": 0.67,
            "ar_turnover_days": 85,
            "inventory_turnover_days": 45,
            "ocf_to_revenue": -0.17,
        },
        "monthly_revenue": [
            {"month": "2024-01", "revenue": 800_000},
            {"month": "2024-02", "revenue": 850_000},
            {"month": "2024-03", "revenue": 900_000},
            {"month": "2024-04", "revenue": 950_000},
            {"month": "2024-05", "revenue": 1_000_000},
            {"month": "2024-06", "revenue": 1_050_000},
            {"month": "2024-07", "revenue": 1_100_000},
            {"month": "2024-08", "revenue": 1_050_000},
            {"month": "2024-09", "revenue": 1_100_000},
            {"month": "2024-10", "revenue": 1_150_000},
            {"month": "2024-11", "revenue": 1_200_000},
            {"month": "2024-12", "revenue": 1_250_000},
        ],
        "exchange_rates": {"USD_CNY": 7.15, "EUR_CNY": 7.85, "USD_EUR": 0.92},
    },
    {
        "id": "FP-ST-RE-01",
        "name": "云上鲜生零售",
        "stage": "startup",
        "industry": "retail",
        "currency": "CNY",
        "fiscal_year": 2024,
        "metrics": {
            "revenue": 8_000_000,
            "net_profit": -1_200_000,
            "total_assets": 5_000_000,
            "total_liabilities": 4_200_000,
            "current_assets": 2_500_000,
            "current_liabilities": 3_500_000,
            "inventory": 1_800_000,
            "accounts_receivable": 600_000,
            "operating_cash_flow": -800_000,
            "gross_margin": 0.22,
            "net_margin": -0.15,
            "debt_ratio": 0.84,
            "current_ratio": 0.71,
            "ar_turnover_days": 27,
            "inventory_turnover_days": 82,
            "ocf_to_revenue": -0.10,
        },
        "monthly_revenue": [
            {"month": "2024-01", "revenue": 600_000},
            {"month": "2024-02", "revenue": 620_000},
            {"month": "2024-03", "revenue": 640_000},
            {"month": "2024-04", "revenue": 660_000},
            {"month": "2024-05", "revenue": 680_000},
            {"month": "2024-06", "revenue": 700_000},
            {"month": "2024-07", "revenue": 720_000},
            {"month": "2024-08", "revenue": 690_000},
            {"month": "2024-09", "revenue": 700_000},
            {"month": "2024-10", "revenue": 730_000},
            {"month": "2024-11", "revenue": 760_000},
            {"month": "2024-12", "revenue": 800_000},
        ],
    },
    {
        "id": "FP-ST-TE-01",
        "name": "极客算法科技",
        "stage": "startup",
        "industry": "technology",
        "currency": "USD",
        "fiscal_year": 2024,
        "metrics": {
            "revenue": 1_500_000,
            "net_profit": -800_000,
            "total_assets": 1_200_000,
            "total_liabilities": 900_000,
            "current_assets": 800_000,
            "current_liabilities": 700_000,
            "inventory": 0,
            "accounts_receivable": 350_000,
            "operating_cash_flow": -600_000,
            "gross_margin": 0.65,
            "net_margin": -0.53,
            "debt_ratio": 0.75,
            "current_ratio": 1.14,
            "ar_turnover_days": 85,
            "inventory_turnover_days": 0,
            "ocf_to_revenue": -0.40,
        },
        "exchange_rates": {"USD_CNY": 7.15, "EUR_CNY": 7.85, "USD_EUR": 0.92},
    },
    # ===== growth =====
    {
        "id": "FP-GR-MA-01",
        "name": "智驱新能源制造",
        "stage": "growth",
        "industry": "manufacturing",
        "currency": "CNY",
        "fiscal_year": 2024,
        "metrics": {
            "revenue": 850_000_000,
            "net_profit": 85_000_000,
            "total_assets": 600_000_000,
            "total_liabilities": 360_000_000,
            "current_assets": 280_000_000,
            "current_liabilities": 150_000_000,
            "inventory": 90_000_000,
            "accounts_receivable": 120_000_000,
            "operating_cash_flow": 70_000_000,
            "gross_margin": 0.28,
            "net_margin": 0.10,
            "debt_ratio": 0.60,
            "current_ratio": 1.87,
            "ar_turnover_days": 51,
            "inventory_turnover_days": 39,
            "ocf_to_revenue": 0.08,
        },
        "monthly_revenue": [
            {"month": "2024-01", "revenue": 55_000_000},
            {"month": "2024-02", "revenue": 58_000_000},
            {"month": "2024-03", "revenue": 62_000_000},
            {"month": "2024-04", "revenue": 65_000_000},
            {"month": "2024-05", "revenue": 68_000_000},
            {"month": "2024-06", "revenue": 72_000_000},
            {"month": "2024-07", "revenue": 75_000_000},
            {"month": "2024-08", "revenue": 78_000_000},
            {"month": "2024-09", "revenue": 82_000_000},
            {"month": "2024-10", "revenue": 85_000_000},
            {"month": "2024-11", "revenue": 88_000_000},
            {"month": "2024-12", "revenue": 92_000_000},
        ],
    },
    {
        "id": "FP-GR-RE-01",
        "name": "鲸落新零售",
        "stage": "growth",
        "industry": "retail",
        "currency": "CNY",
        "fiscal_year": 2024,
        "metrics": {
            "revenue": 320_000_000,
            "net_profit": 18_000_000,
            "total_assets": 180_000_000,
            "total_liabilities": 110_000_000,
            "current_assets": 95_000_000,
            "current_liabilities": 65_000_000,
            "inventory": 45_000_000,
            "accounts_receivable": 12_000_000,
            "operating_cash_flow": 15_000_000,
            "gross_margin": 0.30,
            "net_margin": 0.056,
            "debt_ratio": 0.61,
            "current_ratio": 1.46,
            "ar_turnover_days": 14,
            "inventory_turnover_days": 51,
            "ocf_to_revenue": 0.047,
        },
    },
    {
        "id": "FP-GR-TE-01",
        "name": "星图 AI 科技",
        "stage": "growth",
        "industry": "technology",
        "currency": "USD",
        "fiscal_year": 2024,
        "metrics": {
            "revenue": 25_000_000,
            "net_profit": 4_500_000,
            "total_assets": 18_000_000,
            "total_liabilities": 9_000_000,
            "current_assets": 12_000_000,
            "current_liabilities": 6_000_000,
            "inventory": 0,
            "accounts_receivable": 5_500_000,
            "operating_cash_flow": 3_800_000,
            "gross_margin": 0.72,
            "net_margin": 0.18,
            "debt_ratio": 0.50,
            "current_ratio": 2.00,
            "ar_turnover_days": 80,
            "inventory_turnover_days": 0,
            "ocf_to_revenue": 0.15,
        },
    },
    # ===== mature =====
    {
        "id": "FP-MA-MA-01",
        "name": "蓝海重工集团",
        "stage": "mature",
        "industry": "manufacturing",
        "currency": "CNY",
        "fiscal_year": 2024,
        "metrics": {
            "revenue": 5_200_000_000,
            "net_profit": 416_000_000,
            "total_assets": 4_200_000_000,
            "total_liabilities": 2_100_000_000,
            "current_assets": 1_800_000_000,
            "current_liabilities": 1_100_000_000,
            "inventory": 720_000_000,
            "accounts_receivable": 650_000_000,
            "operating_cash_flow": 520_000_000,
            "gross_margin": 0.25,
            "net_margin": 0.08,
            "debt_ratio": 0.50,
            "current_ratio": 1.64,
            "ar_turnover_days": 46,
            "inventory_turnover_days": 51,
            "ocf_to_revenue": 0.10,
        },
    },
    {
        "id": "FP-MA-RE-01",
        "name": "永辉百货集团",
        "stage": "mature",
        "industry": "retail",
        "currency": "CNY",
        "fiscal_year": 2024,
        "metrics": {
            "revenue": 8_800_000_000,
            "net_profit": 264_000_000,
            "total_assets": 5_500_000_000,
            "total_liabilities": 3_300_000_000,
            "current_assets": 2_400_000_000,
            "current_liabilities": 1_700_000_000,
            "inventory": 1_400_000_000,
            "accounts_receivable": 180_000_000,
            "operating_cash_flow": 300_000_000,
            "gross_margin": 0.20,
            "net_margin": 0.03,
            "debt_ratio": 0.60,
            "current_ratio": 1.41,
            "ar_turnover_days": 7,
            "inventory_turnover_days": 58,
            "ocf_to_revenue": 0.034,
        },
    },
    {
        "id": "FP-MA-TE-01",
        "name": "云栈科技集团",
        "stage": "mature",
        "industry": "technology",
        "currency": "USD",
        "fiscal_year": 2024,
        "metrics": {
            "revenue": 800_000_000,
            "net_profit": 160_000_000,
            "total_assets": 1_200_000_000,
            "total_liabilities": 480_000_000,
            "current_assets": 700_000_000,
            "current_liabilities": 280_000_000,
            "inventory": 0,
            "accounts_receivable": 130_000_000,
            "operating_cash_flow": 200_000_000,
            "gross_margin": 0.62,
            "net_margin": 0.20,
            "debt_ratio": 0.40,
            "current_ratio": 2.50,
            "ar_turnover_days": 59,
            "inventory_turnover_days": 0,
            "ocf_to_revenue": 0.25,
        },
    },
    # ===== declining =====
    {
        "id": "FP-DE-MA-01",
        "name": "夕阳机械制造",
        "stage": "declining",
        "industry": "manufacturing",
        "currency": "CNY",
        "fiscal_year": 2024,
        "metrics": {
            "revenue": 320_000_000,
            "net_profit": -25_000_000,
            "total_assets": 480_000_000,
            "total_liabilities": 360_000_000,
            "current_assets": 150_000_000,
            "current_liabilities": 180_000_000,
            "inventory": 110_000_000,
            "accounts_receivable": 95_000_000,
            "operating_cash_flow": -15_000_000,
            "gross_margin": 0.10,
            "net_margin": -0.078,
            "debt_ratio": 0.75,
            "current_ratio": 0.83,
            "ar_turnover_days": 108,
            "inventory_turnover_days": 125,
            "ocf_to_revenue": -0.047,
        },
    },
    {
        "id": "FP-DE-RE-01",
        "name": "传统百货之光",
        "stage": "declining",
        "industry": "retail",
        "currency": "CNY",
        "fiscal_year": 2024,
        "metrics": {
            "revenue": 1_200_000_000,
            "net_profit": -36_000_000,
            "total_assets": 1_000_000_000,
            "total_liabilities": 750_000_000,
            "current_assets": 350_000_000,
            "current_liabilities": 380_000_000,
            "inventory": 220_000_000,
            "accounts_receivable": 60_000_000,
            "operating_cash_flow": -20_000_000,
            "gross_margin": 0.12,
            "net_margin": -0.03,
            "debt_ratio": 0.75,
            "current_ratio": 0.92,
            "ar_turnover_days": 18,
            "inventory_turnover_days": 67,
            "ocf_to_revenue": -0.017,
        },
    },
    {
        "id": "FP-DE-TE-01",
        "name": "落日软件园",
        "stage": "declining",
        "industry": "technology",
        "currency": "EUR",
        "fiscal_year": 2024,
        "metrics": {
            "revenue": 45_000_000,
            "net_profit": -3_200_000,
            "total_assets": 60_000_000,
            "total_liabilities": 42_000_000,
            "current_assets": 28_000_000,
            "current_liabilities": 22_000_000,
            "inventory": 0,
            "accounts_receivable": 9_500_000,
            "operating_cash_flow": -2_500_000,
            "gross_margin": 0.35,
            "net_margin": -0.071,
            "debt_ratio": 0.70,
            "current_ratio": 1.27,
            "ar_turnover_days": 77,
            "inventory_turnover_days": 0,
            "ocf_to_revenue": -0.056,
        },
        "exchange_rates": {"EUR_CNY": 7.85, "USD_EUR": 0.92, "USD_CNY": 7.15},
    },
    # ===== fraudulent（舞弊场景）=====
    {
        "id": "FP-FR-MA-01",
        "name": "纸面繁荣制造",
        "stage": "fraudulent",
        "industry": "manufacturing",
        "currency": "CNY",
        "fiscal_year": 2024,
        "metrics": {
            "revenue": 680_000_000,
            "net_profit": 65_000_000,
            "total_assets": 520_000_000,
            "total_liabilities": 390_000_000,
            "current_assets": 220_000_000,
            "current_liabilities": 160_000_000,
            "inventory": 80_000_000,
            "accounts_receivable": 165_000_000,
            "operating_cash_flow": 8_000_000,
            "gross_margin": 0.32,
            "net_margin": 0.096,
            "debt_ratio": 0.75,
            "current_ratio": 1.38,
            "ar_turnover_days": 89,
            "inventory_turnover_days": 43,
            "ocf_to_revenue": 0.012,
        },
        # 关键舞弊信号：12 月营收激增 70%（虚增收入），应收账款激增远超营收增速
        "monthly_revenue": [
            {"month": "2024-01", "revenue": 35_000_000},
            {"month": "2024-02", "revenue": 38_000_000},
            {"month": "2024-03", "revenue": 42_000_000},
            {"month": "2024-04", "revenue": 40_000_000},
            {"month": "2024-05", "revenue": 45_000_000},
            {"month": "2024-06", "revenue": 43_000_000},
            {"month": "2024-07", "revenue": 48_000_000},
            {"month": "2024-08", "revenue": 46_000_000},
            {"month": "2024-09", "revenue": 50_000_000},
            {"month": "2024-10", "revenue": 52_000_000},
            {"month": "2024-11", "revenue": 55_000_000},
            {"month": "2024-12", "revenue": 136_000_000},  # 期末激增 147%
        ],
        "revenue_growth": 0.45,  # 营收增 45%
        "ar_growth": 1.85,       # 应收增 185% — 严重背离
        "fraud_hint": "营收增 45% 但应收增 185%，且 12 月营收激增 147%，经营现金流仅 0.012",
    },
    {
        "id": "FP-FR-RE-01",
        "name": "幻影零售",
        "stage": "fraudulent",
        "industry": "retail",
        "currency": "CNY",
        "fiscal_year": 2024,
        "metrics": {
            "revenue": 480_000_000,
            "net_profit": 36_000_000,
            "total_assets": 320_000_000,
            "total_liabilities": 220_000_000,
            "current_assets": 180_000_000,
            "current_liabilities": 120_000_000,
            "inventory": 95_000_000,
            "accounts_receivable": 28_000_000,
            "operating_cash_flow": 4_000_000,
            "gross_margin": 0.42,   # 异常高
            "net_margin": 0.075,
            "debt_ratio": 0.69,
            "current_ratio": 1.50,
            "ar_turnover_days": 21,
            "inventory_turnover_days": 73,
            "ocf_to_revenue": 0.008,
        },
        "fraud_hint": "毛利率 42% 远超同行（零售 20-25%），但现金流极度贫乏（OCF/Revenue=0.008）",
    },
    {
        "id": "FP-FR-TE-01",
        "name": "账面粉饰科技",
        "stage": "fraudulent",
        "industry": "technology",
        "currency": "USD",
        "fiscal_year": 2024,
        "metrics": {
            "revenue": 85_000_000,
            "net_profit": 17_000_000,
            "total_assets": 90_000_000,
            "total_liabilities": 36_000_000,
            "current_assets": 60_000_000,
            "current_liabilities": 22_000_000,
            "inventory": 0,
            "accounts_receivable": 28_000_000,
            "operating_cash_flow": 1_500_000,
            "gross_margin": 0.78,   # 异常高
            "net_margin": 0.20,
            "debt_ratio": 0.40,
            "current_ratio": 2.73,
            "ar_turnover_days": 120,  # 应收周转极慢
            "inventory_turnover_days": 0,
            "ocf_to_revenue": 0.018,  # 现金流贫乏
        },
        "revenue_growth": 0.55,
        "ar_growth": 1.65,
        "fraud_hint": "净利润 17M 但经营现金流仅 1.5M，营收增 55% 但应收增 165%",
    },
]


# ---------------------------------------------------------------------------
# 极端场景数据（用于极限测试 case）
# ---------------------------------------------------------------------------


def _extreme_trial_balance_unbalanced() -> list[dict[str, Any]]:
    """试算不平衡：借贷差 1 元（P0 校验应触发）。"""
    return [
        {"voucher_no": "JZ-2025-001", "account": "1001 库存现金", "debit": 1000.00, "credit": 0},
        {"voucher_no": "JZ-2025-001", "account": "6601 销售费用", "debit": 0, "credit": 999.00},
    ]


def _extreme_division_by_zero() -> dict[str, Any]:
    """除零场景：分母为 0。"""
    return {
        "numerator": 1_000_000,
        "denominator": 0,
        "metric_name": "ROE",
    }


def _extreme_time_travel() -> list[dict[str, Any]]:
    """时间穿越：结账日是 2024-12-31，但有 2025-01-15 的交易。"""
    return [
        {"transaction_id": "T001", "transaction_date": "2024-06-15", "amount": 100_000},
        {"transaction_id": "T002", "transaction_date": "2024-11-30", "amount": 200_000},
        {"transaction_id": "T003", "transaction_date": "2025-01-15", "amount": 500_000},  # 穿越
    ]


def _extreme_negative_asset() -> list[dict[str, Any]]:
    """负数资产：累计折旧 > 原值。"""
    return [
        {"asset_id": "A001", "name": "服务器", "cost": 100_000, "accumulated_depreciation": 120_000},
        {"asset_id": "A002", "name": "办公桌", "cost": 50_000, "accumulated_depreciation": 30_000},
    ]


def _extreme_precision_loss() -> list[float]:
    """精度损失：金额有 10 位小数。"""
    return [1234.5678901234, 0.00000001, 999999.9999999999]


def _extreme_exchange_rate_anomaly() -> dict[str, Any]:
    """汇率异常：USD_CNY = 0.5（明显偏离公允值 7.15）。"""
    return {"USD_CNY": 0.5, "EUR_CNY": 7.85, "USD_EUR": 0.92}


def _extreme_account_age() -> list[dict[str, Any]]:
    """账龄异常：应收账款账龄 730 天。"""
    return [
        {"customer": "客户A", "amount": 500_000, "age_days": 30},
        {"customer": "客户B", "amount": 1_200_000, "age_days": 730},
        {"customer": "客户C", "amount": 800_000, "age_days": 400},
    ]


def _extreme_voucher_no_format() -> list[dict[str, Any]]:
    """凭证号格式异常：含不符合规范的格式。"""
    return [
        {"voucher_no": "记-2025-001"},   # 正确
        {"voucher_no": "JZ-2025-002"},   # 正确
        {"voucher_no": "ABC001"},        # 错误：无分隔符
        {"voucher_no": "凭证2025003"},   # 错误：无分隔符
    ]


def _extreme_related_party() -> list[dict[str, Any]]:
    """关联交易披露：单笔 1500 万未披露。"""
    return [
        {"transaction_id": "RP001", "counterparty": "母公司A", "amount": 5_000_000, "disclosed": True},
        {"transaction_id": "RP002", "counterparty": "子公司B", "amount": 15_000_000, "disclosed": False},  # P0
        {"transaction_id": "RP003", "counterparty": "联营C", "amount": 8_000_000, "disclosed": True},
    ]


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------


def list_companies(
    *,
    stage: str | None = None,
    industry: str | None = None,
) -> list[dict[str, Any]]:
    """列出公司，可按 stage / industry 过滤。返回基础信息（不含 metrics）。"""
    result: list[dict[str, Any]] = []
    for c in _COMPANIES:
        if stage and c["stage"] != stage:
            continue
        if industry and c["industry"] != industry:
            continue
        result.append({
            k: c[k] for k in ("id", "name", "stage", "industry", "currency", "fiscal_year")
        })
    return result


def get_company(company_id: str) -> dict[str, Any] | None:
    """按 ID 取公司完整信息。"""
    for c in _COMPANIES:
        if c["id"] == company_id:
            return c
    return None


def get_extreme_dataset(name: str) -> Any:
    """按名取极限测试数据集。

    可用 name：
        - trial_balance_unbalanced
        - division_by_zero
        - time_travel
        - negative_asset
        - precision_loss
        - exchange_rate_anomaly
        - account_age
        - voucher_no_format
        - related_party
    """
    mapping = {
        "trial_balance_unbalanced": _extreme_trial_balance_unbalanced,
        "division_by_zero": _extreme_division_by_zero,
        "time_travel": _extreme_time_travel,
        "negative_asset": _extreme_negative_asset,
        "precision_loss": _extreme_precision_loss,
        "exchange_rate_anomaly": _extreme_exchange_rate_anomaly,
        "account_age": _extreme_account_age,
        "voucher_no_format": _extreme_voucher_no_format,
        "related_party": _extreme_related_party,
    }
    if name not in mapping:
        raise KeyError(f"未知极限数据集: {name}（可用: {list(mapping.keys())}）")
    return mapping[name]()
