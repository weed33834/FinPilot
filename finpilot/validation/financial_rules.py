"""企业财务数据异常校验引擎（Financial Rules Engine）。

针对企业财务运营的 9 类边界 case 提供原子校验器：
1. 借贷不平衡（试算差额 > 0.01 即阻断结账）
2. 除零保护（毛利率 / 周转率等分母为零）
3. 时间穿越交易（凭证日期晚于结账日 / 早于开账日）
4. 负数资产（存货跌价超成本 / 累计折旧超原值）
5. Decimal 精度保护（避免 float 误差）
6. 汇率合理性（汇率 <= 0 或 > 100 视为异常）
7. 账龄异常（账龄为负 / 超 365 天）
8. 凭证号格式一致性
9. 关联交易披露阈值

设计要点：
- 纯函数 + dataclass，无状态，可独立测试。
- 每个 checker 返回 ValidationIssue 列表，由引擎聚合为 ValidationReport。
- 严重度分级 P0（阻断）/ P1（告警）/ P2（提示）。
- 注册为 Agent 工具供 LLM 调用，也可作为 API 单独暴露。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class ValidationIssue:
    """单条校验问题。"""
    rule_id: str                    # 规则 ID（如 DJE-001）
    severity: str                   # P0 / P1 / P2
    message: str                    # 人读消息
    field_path: str = ""            # 出错字段路径（如 "journal_lines[2].credit"）
    actual_value: Any = None        # 实际值
    expected_value: Any = None      # 期望值
    suggestion: str = ""            # 修复建议

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
            "field_path": self.field_path,
            "actual_value": self.actual_value,
            "expected_value": self.expected_value,
            "suggestion": self.suggestion,
        }


@dataclass
class ValidationReport:
    """校验报告：聚合所有 issue，提供阻断判定与摘要。"""
    issues: list[ValidationIssue] = field(default_factory=list)
    checked_rules: int = 0
    is_blocking: bool = False       # 含 P0 issue 即阻断

    @property
    def p0_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "P0")

    @property
    def p1_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "P1")

    @property
    def p2_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "P2")

    def add(self, issue: ValidationIssue) -> None:
        self.issues.append(issue)
        if issue.severity == "P0":
            self.is_blocking = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_blocking": self.is_blocking,
            "checked_rules": self.checked_rules,
            "p0_count": self.p0_count,
            "p1_count": self.p1_count,
            "p2_count": self.p2_count,
            "issues": [i.to_dict() for i in self.issues],
        }


# ---------------------------------------------------------------------------
# 原子校验器
# ---------------------------------------------------------------------------


def to_decimal(value: Any) -> Decimal | None:
    """安全转 Decimal；失败返回 None。"""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def check_trial_balance(
    journal_lines: list[dict[str, Any]],
    *,
    tolerance: Decimal = Decimal("0.01"),
) -> list[ValidationIssue]:
    """DJL-001 试算平衡校验：所有借方合计 == 贷方合计，差额 > tolerance 即 P0 阻断。"""
    issues: list[ValidationIssue] = []
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    for i, line in enumerate(journal_lines):
        debit = to_decimal(line.get("debit")) or Decimal("0")
        credit = to_decimal(line.get("credit")) or Decimal("0")
        total_debit += debit
        total_credit += credit
        # 每行借贷不能同时有值（标准复式记账）
        if debit and credit:
            issues.append(ValidationIssue(
                rule_id="DJL-001",
                severity="P1",
                message=f"第 {i+1} 行借贷同时有值（借 {debit} / 贷 {credit}），违反复式记账",
                field_path=f"journal_lines[{i}]",
                actual_value={"debit": str(debit), "credit": str(credit)},
                suggestion="借贷不能同时有值，请拆分为两行",
            ))

    diff = (total_debit - total_credit).copy_abs()
    if diff > tolerance:
        issues.append(ValidationIssue(
            rule_id="DJL-001",
            severity="P0",
            message=f"试算不平衡：借方合计 {total_debit} ≠ 贷方合计 {total_credit}，差额 {diff}",
            field_path="journal_lines",
            actual_value=str(diff),
            expected_value=f"≤ {tolerance}",
            suggestion="检查是否有漏记 / 重记 / 错记科目",
        ))
    return issues


def check_division_by_zero(
    numerator: Any, denominator: Any, *, metric_name: str = ""
) -> list[ValidationIssue]:
    """DIV-001 除零保护：分母为零时返回 P1，建议用 null 而非 inf/NaN。"""
    issues: list[ValidationIssue] = []
    denom = to_decimal(denominator)
    if denom is not None and denom == 0:
        issues.append(ValidationIssue(
            rule_id="DIV-001",
            severity="P1",
            message=f"除零风险：{metric_name or '指标'}分母为 0，结果为 inf/NaN",
            actual_value=str(denominator),
            suggestion='分母为 0 时应返回 null 并在 UI 显示"无法计算"，而非 inf',
        ))
    return issues


def check_time_travel(
    transactions: list[dict[str, Any]],
    *,
    closing_date: date | None = None,
    opening_date: date | None = None,
    date_field: str = "transaction_date",
) -> list[ValidationIssue]:
    """TIM-001 时间穿越交易校验：日期晚于结账日 / 早于开账日即 P0。"""
    issues: list[ValidationIssue] = []
    for i, tx in enumerate(transactions):
        raw = tx.get(date_field)
        if not raw:
            continue
        if isinstance(raw, str):
            try:
                tx_date = datetime.fromisoformat(raw).date()
            except ValueError:
                continue
        elif isinstance(raw, datetime):
            tx_date = raw.date()
        elif isinstance(raw, date):
            tx_date = raw
        else:
            continue

        if closing_date and tx_date > closing_date:
            issues.append(ValidationIssue(
                rule_id="TIM-001",
                severity="P0",
                message=f"交易日期 {tx_date} 晚于结账日 {closing_date}（时间穿越）",
                field_path=f"transactions[{i}].{date_field}",
                actual_value=str(tx_date),
                expected_value=f"≤ {closing_date}",
                suggestion="检查日期录入错误或调整结账日",
            ))
        if opening_date and tx_date < opening_date:
            issues.append(ValidationIssue(
                rule_id="TIM-001",
                severity="P0",
                message=f"交易日期 {tx_date} 早于开账日 {opening_date}",
                field_path=f"transactions[{i}].{date_field}",
                actual_value=str(tx_date),
                expected_value=f"≥ {opening_date}",
                suggestion="检查是否误录入历史期间凭证",
            ))
    return issues


def check_negative_asset(
    assets: list[dict[str, Any]],
    *,
    cost_field: str = "cost",
    depreciation_field: str = "accumulated_depreciation",
    asset_name_field: str = "name",
) -> list[ValidationIssue]:
    """NEG-001 负数资产校验：累计折旧超原值 / 存货跌价超成本 → P1。"""
    issues: list[ValidationIssue] = []
    for i, asset in enumerate(assets):
        cost = to_decimal(asset.get(cost_field))
        dep = to_decimal(asset.get(depreciation_field))
        if cost is None or dep is None:
            continue
        net_value = cost - dep
        if net_value < 0:
            issues.append(ValidationIssue(
                rule_id="NEG-001",
                severity="P1",
                message=f"资产 {asset.get(asset_name_field, f'#{i}')} 净值为负：原值 {cost} - 累计折旧 {dep} = {net_value}",
                field_path=f"assets[{i}].{depreciation_field}",
                actual_value=str(net_value),
                expected_value="≥ 0",
                suggestion="累计折旧不应超过原值，检查折旧方法或多记折旧",
            ))
    return issues


def check_precision_loss(
    values: list[Any], *, max_decimals: int = 6
) -> list[ValidationIssue]:
    """PRE-001 精度保护：浮点数小数位超限 → P2 提示用 Decimal。"""
    issues: list[ValidationIssue] = []
    for i, v in enumerate(values):
        if not isinstance(v, float):
            continue
        s = repr(v)
        if "e" in s.lower():
            issues.append(ValidationIssue(
                rule_id="PRE-001",
                severity="P2",
                message=f"第 {i} 个值为科学计数法浮点 {s}，可能存在精度丢失",
                actual_value=s,
                suggestion="财务计算应使用 Decimal 而非 float",
            ))
            continue
        if "." in s and len(s.split(".")[-1]) > max_decimals:
            issues.append(ValidationIssue(
                rule_id="PRE-001",
                severity="P2",
                message=f"第 {i} 个值 {s} 小数位超 {max_decimals} 位，可能存在精度丢失",
                actual_value=s,
                suggestion="财务计算应使用 Decimal 而非 float",
            ))
    return issues


def check_exchange_rate(rates: dict[str, Any]) -> list[ValidationIssue]:
    """FX-001 汇率合理性：汇率 <= 0 或 > 100 → P1。"""
    issues: list[ValidationIssue] = []
    for pair, rate in rates.items():
        r = to_decimal(rate)
        if r is None:
            continue
        if r <= 0:
            issues.append(ValidationIssue(
                rule_id="FX-001",
                severity="P1",
                message=f"汇率 {pair} = {r}，必须 > 0",
                actual_value=str(r),
                expected_value="> 0",
                suggestion="检查汇率方向或数据源",
            ))
        elif r > 100:
            issues.append(ValidationIssue(
                rule_id="FX-001",
                severity="P2",
                message=f"汇率 {pair} = {r}，异常偏高（> 100）",
                actual_value=str(r),
                suggestion="通常是货币对方向写反，如 USD/CNY 写成 CNY/USD",
            ))
    return issues


def check_account_age(
    receivables: list[dict[str, Any]],
    *,
    age_field: str = "age_days",
    customer_field: str = "customer",
) -> list[ValidationIssue]:
    """AGE-001 账龄异常：账龄为负 → P0；超 365 天 → P1。"""
    issues: list[ValidationIssue] = []
    for i, ar in enumerate(receivables):
        age = ar.get(age_field)
        if age is None:
            continue
        try:
            age_int = int(age)
        except (TypeError, ValueError):
            continue
        if age_int < 0:
            issues.append(ValidationIssue(
                rule_id="AGE-001",
                severity="P0",
                message=f"客户 {ar.get(customer_field, f'#{i}')} 账龄 = {age_int} 天（负数，时间穿越）",
                actual_value=age_int,
                expected_value="≥ 0",
                suggestion="检查开票日期或回款日期录入错误",
            ))
        elif age_int > 365:
            issues.append(ValidationIssue(
                rule_id="AGE-001",
                severity="P1",
                message=f"客户 {ar.get(customer_field, f'#{i}')} 账龄 {age_int} 天，超 1 年",
                actual_value=age_int,
                expected_value="≤ 365",
                suggestion="考虑单项计提坏账准备",
            ))
    return issues


_VOUCHER_NO_PATTERN = re.compile(r"^[A-Z]{2,6}[-_]?\d{4,}[-_]?\d*$")


def check_voucher_no_format(
    vouchers: list[dict[str, Any]], *, no_field: str = "voucher_no"
) -> list[ValidationIssue]:
    """VCH-001 凭证号格式一致性：必须形如 JZ-2025001 / FY_2025001 等。"""
    issues: list[ValidationIssue] = []
    for i, v in enumerate(vouchers):
        no = v.get(no_field)
        if not no:
            continue
        if not _VOUCHER_NO_PATTERN.match(str(no)):
            issues.append(ValidationIssue(
                rule_id="VCH-001",
                severity="P2",
                message=f"凭证号 {no} 不符合规范（应形如 JZ-2025001）",
                actual_value=no,
                expected_value="^[A-Z]{2,6}[-_]?\\d{4,}[-_]?\\d*$",
                suggestion="统一编码规则：业务代码-年度-序号",
            ))
    return issues


def check_related_party_disclosure(
    transactions: list[dict[str, Any]],
    *,
    threshold: Decimal = Decimal("10000000"),  # 1000 万元披露阈值
    amount_field: str = "amount",
    party_field: str = "counterparty",
) -> list[ValidationIssue]:
    """RPT-001 关联交易披露：单笔或累计超阈值需披露。"""
    issues: list[ValidationIssue] = []
    cumulative: dict[str, Decimal] = {}
    for i, tx in enumerate(transactions):
        amount = to_decimal(tx.get(amount_field))
        if amount is None:
            continue
        party = str(tx.get(party_field, ""))
        cumulative[party] = cumulative.get(party, Decimal("0")) + amount
        if amount >= threshold:
            issues.append(ValidationIssue(
                rule_id="RPT-001",
                severity="P1",
                message=f"关联交易单笔 {amount} 超披露阈值 {threshold}（对手方：{party}）",
                field_path=f"transactions[{i}]",
                actual_value=str(amount),
                expected_value=f"< {threshold}",
                suggestion="需在财报附注中披露该关联交易",
            ))
    for party, total in cumulative.items():
        if total >= threshold:
            # 已在单笔中提示的不再重复
            has_single = any(
                to_decimal(t.get(amount_field)) and to_decimal(t.get(amount_field)) >= threshold
                and str(t.get(party_field, "")) == party
                for t in transactions
            )
            if not has_single:
                issues.append(ValidationIssue(
                    rule_id="RPT-001",
                    severity="P1",
                    message=f"关联交易累计 {total}（对手方：{party}）超披露阈值 {threshold}",
                    actual_value=str(total),
                    expected_value=f"< {threshold}",
                    suggestion="需在财报附注中按对手方汇总披露",
                ))
    return issues


# ---------------------------------------------------------------------------
# 引擎入口
# ---------------------------------------------------------------------------


@dataclass
class CheckerSpec:
    """校验器描述：函数 + 是否适用判定。"""
    rule_id: str
    name: str
    func: Callable[..., list[ValidationIssue]]


ALL_CHECKERS: list[CheckerSpec] = [
    CheckerSpec("DJL-001", "试算平衡", check_trial_balance),
    CheckerSpec("DIV-001", "除零保护", check_division_by_zero),
    CheckerSpec("TIM-001", "时间穿越", check_time_travel),
    CheckerSpec("NEG-001", "负数资产", check_negative_asset),
    CheckerSpec("PRE-001", "精度保护", check_precision_loss),
    CheckerSpec("FX-001", "汇率合理性", check_exchange_rate),
    CheckerSpec("AGE-001", "账龄异常", check_account_age),
    CheckerSpec("VCH-001", "凭证号格式", check_voucher_no_format),
    CheckerSpec("RPT-001", "关联交易披露", check_related_party_disclosure),
]


def validate_financial_data(
    *,
    journal_lines: list[dict[str, Any]] | None = None,
    division: dict[str, Any] | None = None,
    transactions: list[dict[str, Any]] | None = None,
    closing_date: date | None = None,
    opening_date: date | None = None,
    assets: list[dict[str, Any]] | None = None,
    receivables: list[dict[str, Any]] | None = None,
    vouchers: list[dict[str, Any]] | None = None,
    exchange_rates: dict[str, Any] | None = None,
    related_party_transactions: list[dict[str, Any]] | None = None,
) -> ValidationReport:
    """一站式校验入口：按入参自动调度适用的 checker。

    所有入参都是可选的，只对提供的入参跑校验。
    """
    report = ValidationReport()
    if journal_lines is not None:
        report.issues.extend(check_trial_balance(journal_lines))
        report.checked_rules += 1
    if division:
        report.issues.extend(check_division_by_zero(
            division.get("numerator"),
            division.get("denominator"),
            metric_name=division.get("metric_name", ""),
        ))
        report.checked_rules += 1
    if transactions is not None:
        report.issues.extend(check_time_travel(
            transactions, closing_date=closing_date, opening_date=opening_date
        ))
        report.checked_rules += 1
    if assets is not None:
        report.issues.extend(check_negative_asset(assets))
        report.checked_rules += 1
    if exchange_rates is not None:
        report.issues.extend(check_exchange_rate(exchange_rates))
        report.checked_rules += 1
    if receivables is not None:
        report.issues.extend(check_account_age(receivables))
        report.checked_rules += 1
    if vouchers is not None:
        report.issues.extend(check_voucher_no_format(vouchers))
        report.checked_rules += 1
    if related_party_transactions is not None:
        report.issues.extend(check_related_party_disclosure(related_party_transactions))
        report.checked_rules += 1

    # 重新计算 is_blocking（add 方法已经标记，但保险起见再扫一遍）
    report.is_blocking = any(i.severity == "P0" for i in report.issues)
    return report
