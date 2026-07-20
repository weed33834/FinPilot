"""数据异常校验引擎（Financial Rules Engine）。

针对企业财务运营的 9 类边界 case 提供原子校验器，输出 ValidationReport。
"""
from finpilot.validation.financial_rules import (
    ALL_CHECKERS,
    ValidationIssue,
    ValidationReport,
    check_account_age,
    check_division_by_zero,
    check_exchange_rate,
    check_negative_asset,
    check_precision_loss,
    check_related_party_disclosure,
    check_time_travel,
    check_trial_balance,
    check_voucher_no_format,
    validate_financial_data,
)

__all__ = [
    "ALL_CHECKERS",
    "ValidationIssue",
    "ValidationReport",
    "check_account_age",
    "check_division_by_zero",
    "check_exchange_rate",
    "check_negative_asset",
    "check_precision_loss",
    "check_related_party_disclosure",
    "check_time_travel",
    "check_trial_balance",
    "check_voucher_no_format",
    "validate_financial_data",
]
