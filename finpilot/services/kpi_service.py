"""KPI 数据可视化服务.

基于 ``financial_reports`` 表计算原始指标与派生指标，提供 KPI 概览、
趋势、多期对比、明细钻取四类聚合查询。所有函数纯查询，不修改数据。
"""

# TODO: requires finpilot.cache module (caching decorator) — current fallback is no-op
# TODO: requires finpilot.database.models.FinancialReport (already present in FinPilot)

from __future__ import annotations

from typing import Any, cast

from sqlalchemy.orm import Session

from finpilot.database.models import FinancialReport

# 缓存装饰器：FinPilot 暂无独立 cache 模块，降级为 no-op，保证函数可用.
try:
    from finpilot.cache import cached  # type: ignore[import-not-found]
except ImportError:
    def cached(*_args, **_kwargs):  # type: ignore[misc]
        """No-op fallback when finpilot.cache is unavailable."""
        def decorator(func):
            return func
        return decorator

# period 显示顺序，环比逻辑以此为准
PERIOD_ORDER: list[str] = ["Q1", "Q2", "Q3", "Q4", "H1", "H2", "annual"]

# 13 个指标的元数据：8 原始 + 5 派生
METRIC_DEFINITIONS: list[dict[str, Any]] = [
    {"key": "revenue", "label": "营收", "unit": "元", "is_derived": False},
    {"key": "operating_cost", "label": "营业成本", "unit": "元", "is_derived": False},
    {"key": "operating_profit", "label": "营业利润", "unit": "元", "is_derived": False},
    {"key": "net_profit", "label": "净利润", "unit": "元", "is_derived": False},
    {"key": "total_assets", "label": "总资产", "unit": "元", "is_derived": False},
    {"key": "total_liabilities", "label": "总负债", "unit": "元", "is_derived": False},
    {"key": "owner_equity", "label": "所有者权益", "unit": "元", "is_derived": False},
    {"key": "cash_flow_operating", "label": "经营现金流", "unit": "元", "is_derived": False},
    {"key": "gross_profit", "label": "毛利润", "unit": "元", "is_derived": True},
    {"key": "operating_margin", "label": "营业利润率", "unit": "%", "is_derived": True},
    {"key": "net_margin", "label": "净利率", "unit": "%", "is_derived": True},
    {"key": "debt_ratio", "label": "资产负债率", "unit": "%", "is_derived": True},
    {"key": "cash_flow_margin", "label": "现金流利润比", "unit": "%", "is_derived": True},
]

_RAW_METRICS: set[str] = {m["key"] for m in METRIC_DEFINITIONS if not m["is_derived"]}
_DERIVED_METRICS: set[str] = {m["key"] for m in METRIC_DEFINITIONS if m["is_derived"]}
_ALL_METRICS: set[str] = _RAW_METRICS | _DERIVED_METRICS

# 环比上一期映射：period -> (上一期 period, 年份偏移)
_PREVIOUS_PERIOD: dict[str, tuple[str, int]] = {
    "Q1": ("annual", -1),
    "Q2": ("Q1", 0),
    "Q3": ("Q2", 0),
    "Q4": ("Q3", 0),
    "H1": ("Q1", 0),
    "H2": ("H1", 0),
    "annual": ("H2", 0),
}


def get_metric_label(metric: str) -> str:
    """根据指标 key 返回中文标签，未命中返回 key 本身."""
    for item in METRIC_DEFINITIONS:
        if item["key"] == metric:
            return cast(str, item["label"])
    return metric


def _metric_meta(metric: str) -> dict[str, Any]:
    """取指标元数据，未命中抛 KeyError."""
    for item in METRIC_DEFINITIONS:
        if item["key"] == metric:
            return item
    raise KeyError(f"未知指标: {metric}")


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    """安全除法：任一参数为 None 或分母为 0 时返回 None."""
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _compute_metric_value(report: FinancialReport | None, metric: str) -> float | None:
    """从财报行计算指标值，派生指标按公式推导.

    除法分母为 0 或 None 返回 None；参与计算的任一原始字段为 None 返回 None。
    """
    if report is None:
        return None

    if metric in _RAW_METRICS:
        return cast(float | None, getattr(report, metric))

    if metric == "gross_profit":
        if report.revenue is None or report.operating_cost is None:
            return None
        return report.revenue - report.operating_cost

    if metric == "operating_margin":
        return _safe_div(report.operating_profit, report.revenue)

    if metric == "net_margin":
        return _safe_div(report.net_profit, report.revenue)

    if metric == "debt_ratio":
        return _safe_div(report.total_liabilities, report.total_assets)

    if metric == "cash_flow_margin":
        return _safe_div(report.cash_flow_operating, report.revenue)

    return None


def _build_change(current: float | None, previous: float | None) -> dict[str, Any]:
    """构造同比/环比三元组，缺数据时 change/change_pct 为 None."""
    change: float | None
    change_pct: float | None
    if current is None or previous is None:
        change = None
        change_pct = None
    else:
        change = current - previous
        change_pct = (change / previous * 100) if previous != 0 else None
    return {"value": current, "change": change, "change_pct": change_pct}


def _fetch_report(
    db: Session, tenant_id: str, year: int, period: str
) -> FinancialReport | None:
    """按租户+年份+周期取单条财报."""
    return (
        db.query(FinancialReport)
        .filter(
            FinancialReport.tenant_id == tenant_id,
            FinancialReport.year == year,
            FinancialReport.period == period,
        )
        .first()
    )


@cached(ttl=600, key_prefix="kpi_overview")
def get_kpi_overview(
    db: Session, tenant_id: str, year: int, period: str
) -> dict[str, Any]:
    """返回指定期 KPI 卡片数据，含 13 个指标及同比/环比."""
    current = _fetch_report(db, tenant_id, year, period)

    prev_period, year_offset = _PREVIOUS_PERIOD.get(period, ("annual", -1))
    yoy_report = _fetch_report(db, tenant_id, year - 1, period)
    qoq_report = _fetch_report(db, tenant_id, year + year_offset, prev_period)

    cards: list[dict[str, Any]] = []
    for meta in METRIC_DEFINITIONS:
        key = meta["key"]
        value = _compute_metric_value(current, key)
        yoy: dict[str, Any] | None = None
        if yoy_report is not None:
            yoy = _build_change(value, _compute_metric_value(yoy_report, key))
        qoq: dict[str, Any] | None = None
        if qoq_report is not None:
            qoq = _build_change(value, _compute_metric_value(qoq_report, key))
        cards.append(
            {
                "metric": key,
                "label": meta["label"],
                "value": value,
                "unit": meta["unit"],
                "yoy": yoy,
                "qoq": qoq,
            }
        )
    return {"year": year, "period": period, "cards": cards}


def _pick_representative(reports: list[FinancialReport]) -> FinancialReport | None:
    """从同年多条财报中取 annual，缺失则按 PERIOD_ORDER 取最后一个有数据的."""
    if not reports:
        return None
    for rpt in reports:
        if rpt.period == "annual":
            return rpt
    ordered = sorted(
        reports,
        key=lambda r: PERIOD_ORDER.index(r.period) if r.period in PERIOD_ORDER else 0,
    )
    return ordered[-1]


@cached(ttl=600, key_prefix="kpi_trend")
def get_metric_trend(
    db: Session, tenant_id: str, metric: str, years: list[int]
) -> dict[str, Any]:
    """返回某指标在指定年份列表的年度趋势.

    每年取 annual period 的值，annual 缺失则取该年最后一个有数据的 period。
    优化：单次查询取回所有年份的全部 period 行，再在内存按年分组取代表值，
    避免 N 年 N 次查询的 N+1 问题。
    """
    meta = _metric_meta(metric)
    series: list[dict[str, Any]] = []

    if not years:
        return {
            "metric": metric,
            "label": meta["label"],
            "unit": meta["unit"],
            "series": series,
        }

    rows = (
        db.query(FinancialReport)
        .filter(
            FinancialReport.tenant_id == tenant_id,
            FinancialReport.year.in_(years),
        )
        .all()
    )
    by_year: dict[int, list[FinancialReport]] = {}
    for rpt in rows:
        by_year.setdefault(rpt.year, []).append(rpt)

    for year in years:
        picked = _pick_representative(by_year.get(year, []))
        series.append({"year": year, "value": _compute_metric_value(picked, metric)})
    return {
        "metric": metric,
        "label": meta["label"],
        "unit": meta["unit"],
        "series": series,
    }


@cached(ttl=600, key_prefix="kpi_comparison")
def get_metric_comparison(
    db: Session, tenant_id: str, year: int, periods: list[str]
) -> dict[str, Any]:
    """返回某年指定 periods 的 13 指标对比.

    优化：单次查询取回该年所有指定 period 的行，避免 M period M 次查询的 N+1 问题。
    """
    period_reports: dict[str, FinancialReport | None] = dict.fromkeys(periods)
    if periods:
        rows = (
            db.query(FinancialReport)
            .filter(
                FinancialReport.tenant_id == tenant_id,
                FinancialReport.year == year,
                FinancialReport.period.in_(periods),
            )
            .all()
        )
        for rpt in rows:
            period_reports[rpt.period] = rpt

    metrics: list[dict[str, Any]] = []
    for meta in METRIC_DEFINITIONS:
        key = meta["key"]
        values: dict[str, float | None] = {}
        for period in periods:
            values[period] = _compute_metric_value(period_reports.get(period), key)
        metrics.append(
            {
                "metric": key,
                "label": meta["label"],
                "unit": meta["unit"],
                "values": values,
            }
        )
    return {"year": year, "periods": list(periods), "metrics": metrics}


@cached(ttl=600, key_prefix="kpi_drilldown")
def get_drill_down(
    db: Session,
    tenant_id: str,
    metric: str,
    year: int,
    period: str | None = None,
) -> dict[str, Any]:
    """返回某指标在某年的明细钻取，含各 period 值及占该年总和比例."""
    meta = _metric_meta(metric)
    reports = (
        db.query(FinancialReport)
        .filter(
            FinancialReport.tenant_id == tenant_id,
            FinancialReport.year == year,
        )
        .all()
    )
    ordered = sorted(
        reports,
        key=lambda r: PERIOD_ORDER.index(r.period) if r.period in PERIOD_ORDER else 0,
    )

    all_values: list[tuple[str, float | None]] = [
        (rpt.period, _compute_metric_value(rpt, metric)) for rpt in ordered
    ]
    total = sum(v for _, v in all_values if v is not None) or None

    items: list[dict[str, Any]] = []
    for p, value in all_values:
        if period is not None and p != period:
            continue
        ratio = None if value is None or total is None or total == 0 else value / total
        items.append({"period": p, "value": value, "ratio": ratio})

    return {
        "metric": metric,
        "label": meta["label"],
        "year": year,
        "total": total,
        "items": items,
    }


def is_valid_metric(metric: str) -> bool:
    """判断指标 key 是否合法."""
    return metric in _ALL_METRICS
