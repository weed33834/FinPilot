"""风险预警引擎（Risk Warning Engine）— 时序预测 + 风险区间分类。

针对企业财务运营的关键风险场景，提供：

1. **时序预测**
   - 简单移动平均（SMA）
   - 指数平滑（ETS）
   - 同环比计算

2. **风险区间分类**
   - 基于阈值的三级分类（高 / 中 / 低风险）
   - 阈值可配置（财务指标规则库）

3. **财务舞弊识别**
   - 期末突击确认收入模式
   - 应收账款与收入增长背离
   - 现金流与利润背离（盈余质量）
   - 存货周转与毛利率异常

4. **预警规则引擎**
   - 可配置规则（指标 + 阈值 + 严重度 + 消息）
   - 输出 RiskWarning 列表

设计要点：
- 纯函数 + dataclass，无状态
- 不依赖 numpy/pandas（避免重依赖），用纯 Python 实现
- 阈值参考《企业财务通则》与业界惯例
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class ForecastResult:
    """时序预测结果。"""
    metric_name: str
    historical_values: list[float]
    forecast_values: list[float]
    method: str                       # "sma" / "ets"
    confidence: float                 # 0-1
    next_value: float                 # 下一期预测值
    trend: str                        # "up" / "down" / "flat"


@dataclass
class RiskClassification:
    """风险区间分类结果。"""
    metric_name: str
    value: float
    level: str                        # "high" / "medium" / "low"
    threshold_high: float
    threshold_low: float
    reason: str


@dataclass
class FraudSignal:
    """舞弊信号。"""
    signal_type: str                  # "period_end_surge" / "ar_revenue_divergence" 等
    severity: str                     # P0 / P1 / P2
    metric: str
    evidence: str
    suggestion: str


@dataclass
class RiskWarning:
    """风险预警。"""
    warning_id: str
    metric_name: str
    level: str                        # high / medium / low
    severity: str                     # P0 / P1 / P2
    current_value: float
    threshold: float
    message: str
    suggestion: str
    detected_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RiskReport:
    """风险报告：聚合所有预警 + 舞弊信号。"""
    warnings: list[RiskWarning] = field(default_factory=list)
    fraud_signals: list[FraudSignal] = field(default_factory=list)
    forecasts: list[ForecastResult] = field(default_factory=list)
    classifications: list[RiskClassification] = field(default_factory=list)

    @property
    def high_risk_count(self) -> int:
        return sum(1 for w in self.warnings if w.level == "high")

    @property
    def p0_count(self) -> int:
        return sum(1 for w in self.warnings if w.severity == "P0") + \
               sum(1 for f in self.fraud_signals if f.severity == "P0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "high_risk_count": self.high_risk_count,
            "p0_count": self.p0_count,
            "warnings": [w.to_dict() for w in self.warnings],
            "fraud_signals": [asdict(f) for f in self.fraud_signals],
            "forecasts": [asdict(f) for f in self.forecasts],
            "classifications": [asdict(c) for c in self.classifications],
        }


# ---------------------------------------------------------------------------
# 1. 时序预测
# ---------------------------------------------------------------------------


def simple_moving_average(
    values: list[float], *, window: int = 3, forecast_periods: int = 1
) -> ForecastResult:
    """简单移动平均预测。

    Args:
        values: 历史值序列
        window: 移动窗口大小
        forecast_periods: 预测期数

    Returns:
        ForecastResult
    """
    if len(values) < window:
        return ForecastResult(
            metric_name="",
            historical_values=values,
            forecast_values=[sum(values) / len(values)] * forecast_periods if values else [],
            method="sma",
            confidence=0.3,
            next_value=sum(values) / len(values) if values else 0.0,
            trend="flat",
        )

    # 计算每个窗口的 SMA
    sma_values: list[float] = []
    for i in range(len(values) - window + 1):
        sma = sum(values[i:i + window]) / window
        sma_values.append(sma)

    # 用最后一个 SMA 作为下一期预测（朴素 SMA 预测）
    next_value = sma_values[-1]
    # 滚动预测多期
    forecast_values: list[float] = []
    history = list(values)
    for _ in range(forecast_periods):
        if len(history) >= window:
            next_v = sum(history[-window:]) / window
        else:
            next_v = sum(history) / len(history) if history else 0.0
        forecast_values.append(next_v)
        history.append(next_v)

    # 趋势判断
    if len(values) >= 2:
        recent_avg = sum(values[-min(window, len(values)):]) / min(window, len(values))
        earlier_avg = sum(values[:min(window, len(values))]) / min(window, len(values))
        if recent_avg > earlier_avg * 1.05:
            trend = "up"
        elif recent_avg < earlier_avg * 0.95:
            trend = "down"
        else:
            trend = "flat"
    else:
        trend = "flat"

    # 置信度：数据点越多 + window 越接近 1/3 数据量 → 置信度越高
    confidence = min(0.8, len(values) / 20 + 0.3)

    return ForecastResult(
        metric_name="",
        historical_values=values,
        forecast_values=forecast_values,
        method="sma",
        confidence=confidence,
        next_value=next_value,
        trend=trend,
    )


def exponential_smoothing(
    values: list[float], *, alpha: float = 0.3, forecast_periods: int = 1
) -> ForecastResult:
    """指数平滑预测（ETS 一次平滑）。

    Args:
        values: 历史值序列
        alpha: 平滑系数（0-1，越大越看重近期）
        forecast_periods: 预测期数

    Returns:
        ForecastResult
    """
    if not values:
        return ForecastResult(
            metric_name="",
            historical_values=[],
            forecast_values=[],
            method="ets",
            confidence=0.0,
            next_value=0.0,
            trend="flat",
        )

    # 一次指数平滑：s_t = alpha * x_t + (1-alpha) * s_{t-1}
    s = values[0]
    smoothed: list[float] = [s]
    for v in values[1:]:
        s = alpha * v + (1 - alpha) * s
        smoothed.append(s)

    # ETS 一次平滑的预测 = 最后一个平滑值
    next_value = s
    forecast_values = [next_value] * forecast_periods

    # 趋势判断
    if len(smoothed) >= 2:
        if smoothed[-1] > smoothed[0] * 1.05:
            trend = "up"
        elif smoothed[-1] < smoothed[0] * 0.95:
            trend = "down"
        else:
            trend = "flat"
    else:
        trend = "flat"

    confidence = min(0.85, len(values) / 15 + 0.4)

    return ForecastResult(
        metric_name="",
        historical_values=values,
        forecast_values=forecast_values,
        method="ets",
        confidence=confidence,
        next_value=next_value,
        trend=trend,
    )


def year_over_year(values: list[float], *, period: int = 4) -> list[float | None]:
    """计算同环比（YoY / QoQ）。

    Args:
        values: 时序数据
        period: 周期长度（季度=4，月度=12）

    Returns:
        同比增长率列表（前 period 个为 None）
    """
    if len(values) <= period:
        return [None] * len(values)
    yoy: list[float | None] = [None] * period
    for i in range(period, len(values)):
        prev = values[i - period]
        if prev == 0:
            yoy.append(None)
        else:
            yoy.append((values[i] - prev) / abs(prev))
    return yoy


# ---------------------------------------------------------------------------
# 2. 风险区间分类
# ---------------------------------------------------------------------------


@dataclass
class RiskThreshold:
    """风险阈值定义。"""
    metric_name: str
    high_threshold: float             # 高风险阈值（超过即高）
    low_threshold: float              # 低风险阈值（低于即低）
    direction: str = "above"          # "above"（高于阈值即高风险）/ "below"
    description: str = ""


# 财务指标默认风险阈值库（参考《企业财务通则》与业界惯例）
DEFAULT_THRESHOLDS: dict[str, RiskThreshold] = {
    "debt_ratio": RiskThreshold(
        metric_name="debt_ratio",
        high_threshold=0.7, low_threshold=0.4,
        direction="above",
        description="资产负债率，>70% 高风险，<40% 低风险",
    ),
    "current_ratio": RiskThreshold(
        metric_name="current_ratio",
        high_threshold=2.0, low_threshold=1.0,
        direction="below",  # 低于 1.0 高风险
        description="流动比率，<1.0 高风险（短期偿债能力不足），>2.0 低风险",
    ),
    "gross_margin": RiskThreshold(
        metric_name="gross_margin",
        high_threshold=0.4, low_threshold=0.15,
        direction="below",  # 低于 15% 高风险
        description="毛利率，<15% 高风险，>40% 低风险",
    ),
    "net_margin": RiskThreshold(
        metric_name="net_margin",
        high_threshold=0.2, low_threshold=0.05,
        direction="below",
        description="净利率，<5% 高风险，>20% 低风险",
    ),
    "ar_turnover_days": RiskThreshold(
        metric_name="ar_turnover_days",
        high_threshold=120, low_threshold=30,
        direction="above",  # 高于 120 天高风险
        description="应收账款周转天数，>120 天高风险",
    ),
    "inventory_turnover_days": RiskThreshold(
        metric_name="inventory_turnover_days",
        high_threshold=180, low_threshold=30,
        direction="above",
        description="存货周转天数，>180 天高风险",
    ),
    "ocf_to_revenue": RiskThreshold(
        metric_name="ocf_to_revenue",
        high_threshold=0.2, low_threshold=0.05,
        direction="below",  # 经营现金流/营收 <5% 高风险
        description="经营现金流/营收，<5% 高风险（盈余质量差）",
    ),
}


def classify_risk(
    metric_name: str,
    value: float,
    *,
    threshold: RiskThreshold | None = None,
) -> RiskClassification:
    """对单个指标值进行风险区间分类。"""
    if threshold is None:
        threshold = DEFAULT_THRESHOLDS.get(metric_name)
    if threshold is None:
        return RiskClassification(
            metric_name=metric_name,
            value=value,
            level="unknown",
            threshold_high=0.0,
            threshold_low=0.0,
            reason=f"指标 {metric_name} 未配置风险阈值",
        )

    if threshold.direction == "above":
        # 值越高越危险
        if value > threshold.high_threshold:
            level = "high"
            reason = f"{value} > 高风险阈值 {threshold.high_threshold}"
        elif value > threshold.low_threshold:
            level = "medium"
            reason = f"{threshold.low_threshold} ≤ {value} ≤ {threshold.high_threshold}"
        else:
            level = "low"
            reason = f"{value} < 低风险阈值 {threshold.low_threshold}"
    else:
        # 值越低越危险
        if value < threshold.high_threshold:
            level = "high"
            reason = f"{value} < 高风险阈值 {threshold.high_threshold}"
        elif value < threshold.low_threshold:
            level = "medium"
            reason = f"{threshold.high_threshold} ≤ {value} ≤ {threshold.low_threshold}"
        else:
            level = "low"
            reason = f"{value} > 低风险阈值 {threshold.low_threshold}"

    return RiskClassification(
        metric_name=metric_name,
        value=value,
        level=level,
        threshold_high=threshold.high_threshold,
        threshold_low=threshold.low_threshold,
        reason=reason + f"（{threshold.description}）",
    )


# ---------------------------------------------------------------------------
# 3. 财务舞弊识别
# ---------------------------------------------------------------------------


def detect_period_end_surge(
    monthly_revenue: list[dict[str, Any]],
    *,
    surge_threshold: float = 0.4,
) -> list[FraudSignal]:
    """期末突击确认收入识别。

    判定：12 月单月收入占全年 > 40% → P1 预警。

    Args:
        monthly_revenue: 月度收入列表，每项 {"month": 1-12, "revenue": float}
        surge_threshold: 末月占比阈值，默认 0.4
    """
    signals: list[FraudSignal] = []
    if len(monthly_revenue) < 12:
        return signals
    total = sum(m.get("revenue", 0) for m in monthly_revenue)
    if total <= 0:
        return signals
    dec_revenue = next(
        (m.get("revenue", 0) for m in monthly_revenue if m.get("month") == 12),
        0,
    )
    dec_ratio = dec_revenue / total
    if dec_ratio > surge_threshold:
        signals.append(FraudSignal(
            signal_type="period_end_surge",
            severity="P1",
            metric="december_revenue_ratio",
            evidence=f"12 月收入 {dec_revenue:.2f} 占全年 {dec_ratio:.0%}（阈值 {surge_threshold:.0%}）",
            suggestion="期末突击确认收入，可能存在收入提前确认或盈余管理，建议核查",
        ))
    # 末三月占比 > 60% 也预警
    last_quarter = sum(
        m.get("revenue", 0) for m in monthly_revenue if m.get("month", 0) >= 10
    )
    lq_ratio = last_quarter / total
    if lq_ratio > 0.6:
        signals.append(FraudSignal(
            signal_type="period_end_surge",
            severity="P2",
            metric="last_quarter_revenue_ratio",
            evidence=f"Q4 收入 {last_quarter:.2f} 占全年 {lq_ratio:.0%}",
            suggestion="Q4 收入占比偏高，关注是否存在期末集中确认",
        ))
    return signals


def detect_ar_revenue_divergence(
    revenue_growth: float, ar_growth: float
) -> list[FraudSignal]:
    """应收账款与收入增长背离识别。

    判定：应收账款增长率 > 收入增长率 * 1.5 且收入增长 > 10% → P1
    """
    signals: list[FraudSignal] = []
    if revenue_growth > 0.1 and ar_growth > revenue_growth * 1.5:
        signals.append(FraudSignal(
            signal_type="ar_revenue_divergence",
            severity="P1",
            metric="ar_growth_vs_revenue_growth",
            evidence=f"应收账款增长 {ar_growth:.0%} 显著高于收入增长 {revenue_growth:.0%}",
            suggestion="应收账款增长显著快于收入，可能存在放宽信用政策或虚假销售",
        ))
    return signals


def detect_cash_profit_divergence(
    net_profit: float, operating_cash_flow: float
) -> list[FraudSignal]:
    """现金流与利润背离识别（盈余质量）。

    判定：净利润 > 0 但经营现金流 < 净利润 * 0.5 → P1
    """
    signals: list[FraudSignal] = []
    if net_profit > 0 and operating_cash_flow < net_profit * 0.5:
        signals.append(FraudSignal(
            signal_type="cash_profit_divergence",
            severity="P1",
            metric="ocf_to_net_profit",
            evidence=f"净利润 {net_profit:.2f} 但经营现金流 {operating_cash_flow:.2f}（< 50% 净利）",
            suggestion="盈余质量差，利润未转化为现金，可能存在应收账款虚增或费用资本化",
        ))
    return signals


def detect_inventory_margin_anomaly(
    inventory_turnover_days_current: float,
    inventory_turnover_days_prev: float,
    gross_margin_current: float,
    gross_margin_prev: float,
) -> list[FraudSignal]:
    """存货周转与毛利率异常识别。

    判定：存货周转天数大幅增加 + 毛利率反而上升 → P1（可能虚增毛利率）
    """
    signals: list[FraudSignal] = []
    turnover_increase = inventory_turnover_days_current - inventory_turnover_days_prev
    margin_increase = gross_margin_current - gross_margin_prev
    if turnover_increase > 30 and margin_increase > 0.02:
        signals.append(FraudSignal(
            signal_type="inventory_margin_anomaly",
            severity="P1",
            metric="inventory_turnover_vs_margin",
            evidence=(
                f"存货周转天数从 {inventory_turnover_days_prev:.0f} 增至 "
                f"{inventory_turnover_days_current:.0f}（+{turnover_increase:.0f}天），"
                f"毛利率从 {gross_margin_prev:.0%} 升至 {gross_margin_current:.0%}"
            ),
            suggestion="存货周转放缓但毛利率上升，违背常理，可能存在少结转成本以虚增毛利",
        ))
    return signals


# ---------------------------------------------------------------------------
# 4. 预警规则引擎
# ---------------------------------------------------------------------------


@dataclass
class WarningRule:
    """预警规则。"""
    rule_id: str
    metric_name: str
    condition: Callable[[float], bool]
    level: str               # high / medium / low
    severity: str            # P0 / P1 / P2
    message: str
    suggestion: str


def _build_default_rules() -> list[WarningRule]:
    """构建默认预警规则集。"""
    return [
        WarningRule(
            rule_id="RW-001",
            metric_name="debt_ratio",
            condition=lambda v: v > 0.8,
            level="high", severity="P0",
            message="资产负债率超过 80%，财务风险极高",
            suggestion="立即优化资本结构，考虑引入股权融资或处置资产降杠杆",
        ),
        WarningRule(
            rule_id="RW-002",
            metric_name="current_ratio",
            condition=lambda v: v < 0.8,
            level="high", severity="P0",
            message="流动比率低于 0.8，短期偿债能力严重不足",
            suggestion="评估短期债务到期情况，考虑展期或新增流动资金贷款",
        ),
        WarningRule(
            rule_id="RW-003",
            metric_name="ocf_to_revenue",
            condition=lambda v: v < 0.0,
            level="high", severity="P0",
            message="经营现金流为负，主营业务无法产生现金",
            suggestion="核查应收账款回收与存货积压，必要时启动现金流量危机预案",
        ),
        WarningRule(
            rule_id="RW-004",
            metric_name="ar_turnover_days",
            condition=lambda v: v > 180,
            level="high", severity="P1",
            message="应收账款周转天数超 180 天，回款风险高",
            suggestion="加大催收力度，评估单项计提坏账准备",
        ),
        WarningRule(
            rule_id="RW-005",
            metric_name="gross_margin",
            condition=lambda v: 0 < v < 0.1,
            level="high", severity="P1",
            message="毛利率低于 10%，盈利能力承压",
            suggestion="分析成本结构，考虑提价或优化采购",
        ),
    ]


def evaluate_warning_rules(
    metrics: dict[str, float],
    *,
    rules: list[WarningRule] | None = None,
) -> list[RiskWarning]:
    """对一组指标评估预警规则。

    Args:
        metrics: 指标名 → 值
        rules: 自定义规则集，缺省取默认

    Returns:
        RiskWarning 列表
    """
    if rules is None:
        rules = _build_default_rules()

    warnings: list[RiskWarning] = []
    for rule in rules:
        value = metrics.get(rule.metric_name)
        if value is None:
            continue
        try:
            triggered = rule.condition(value)
        except Exception as exc:  # noqa: BLE001
            logger.warning("rule_eval_failed rule=%s err=%s", rule.rule_id, exc)
            continue
        if triggered:
            warnings.append(RiskWarning(
                warning_id=rule.rule_id,
                metric_name=rule.metric_name,
                level=rule.level,
                severity=rule.severity,
                current_value=value,
                threshold=0.0,  # 由 condition 内嵌
                message=rule.message,
                suggestion=rule.suggestion,
            ))
    return warnings


# ---------------------------------------------------------------------------
# 5. 统一入口
# ---------------------------------------------------------------------------


def assess_risk(
    *,
    metrics: dict[str, float] | None = None,
    monthly_revenue: list[dict[str, Any]] | None = None,
    revenue_growth: float | None = None,
    ar_growth: float | None = None,
    net_profit: float | None = None,
    operating_cash_flow: float | None = None,
    inventory_turnover_current: float | None = None,
    inventory_turnover_prev: float | None = None,
    gross_margin_current: float | None = None,
    gross_margin_prev: float | None = None,
    forecast_series: dict[str, list[float]] | None = None,
) -> RiskReport:
    """一站式风险评估入口。

    所有入参都是可选的，只对提供的入参跑评估。
    """
    report = RiskReport()

    # 1. 预警规则
    if metrics:
        report.warnings.extend(evaluate_warning_rules(metrics))

        # 2. 风险区间分类
        for name, value in metrics.items():
            if name in DEFAULT_THRESHOLDS:
                report.classifications.append(classify_risk(name, value))

    # 3. 舞弊信号
    if monthly_revenue:
        report.fraud_signals.extend(detect_period_end_surge(monthly_revenue))
    if revenue_growth is not None and ar_growth is not None:
        report.fraud_signals.extend(
            detect_ar_revenue_divergence(revenue_growth, ar_growth)
        )
    if net_profit is not None and operating_cash_flow is not None:
        report.fraud_signals.extend(
            detect_cash_profit_divergence(net_profit, operating_cash_flow)
        )
    if (
        inventory_turnover_current is not None
        and inventory_turnover_prev is not None
        and gross_margin_current is not None
        and gross_margin_prev is not None
    ):
        report.fraud_signals.extend(detect_inventory_margin_anomaly(
            inventory_turnover_current, inventory_turnover_prev,
            gross_margin_current, gross_margin_prev,
        ))

    # 4. 时序预测
    if forecast_series:
        for name, series in forecast_series.items():
            if len(series) >= 3:
                fc = exponential_smoothing(series, forecast_periods=1)
                fc.metric_name = name
                report.forecasts.append(fc)

    return report
