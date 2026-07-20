"""风险预警引擎（Risk Warning Engine）。

时序预测 + 风险区间分类 + 财务舞弊识别 + 预警规则引擎。
"""
from finpilot.risk.engine import (
    DEFAULT_THRESHOLDS,
    ForecastResult,
    FraudSignal,
    RiskClassification,
    RiskReport,
    RiskThreshold,
    RiskWarning,
    WarningRule,
    assess_risk,
    classify_risk,
    detect_ar_revenue_divergence,
    detect_cash_profit_divergence,
    detect_inventory_margin_anomaly,
    detect_period_end_surge,
    evaluate_warning_rules,
    exponential_smoothing,
    simple_moving_average,
    year_over_year,
)

__all__ = [
    "DEFAULT_THRESHOLDS",
    "ForecastResult",
    "FraudSignal",
    "RiskClassification",
    "RiskReport",
    "RiskThreshold",
    "RiskWarning",
    "WarningRule",
    "assess_risk",
    "classify_risk",
    "detect_ar_revenue_divergence",
    "detect_cash_profit_divergence",
    "detect_inventory_margin_anomaly",
    "detect_period_end_surge",
    "evaluate_warning_rules",
    "exponential_smoothing",
    "simple_moving_average",
    "year_over_year",
]
