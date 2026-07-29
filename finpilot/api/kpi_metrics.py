# -*- coding: utf-8 -*-
"""``/metrics`` —— 指标分析页（KPI 看板）。

前端 KpiDashboardPage.tsx 期望 schema（见 frontend/src/types/metric.ts）：
  overview  -> { year, period, cards: KpiCardData[], generated_at }
  trend     -> { metric, label, unit, series: TrendPoint[] }
  comparison-> { year, periods: str[], metrics: MetricComparisonItem[] }
  drill     -> { metric, label, year, total, items: DrillDownItem[] }

这里基于 year+period 用确定性公式生成稳定的模拟财务数据，让前端 KPI 看板
能真正渲染出来（同比/环比/趋势/对比/钻取），而不是 404 或 undefined 崩溃。

本模块从原 ``compat.py`` 拆分而来，行为与原 ``metrics_router`` 完全一致。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends

from ._compat_helpers import ok
from .deps import get_current_user

router = APIRouter(prefix="/metrics", tags=["metrics"])

# 指标元数据：metric key -> (label, unit)
_METRIC_META: dict[str, tuple[str, str]] = {
    "revenue": ("营业收入", "元"),
    "net_profit": ("净利润", "元"),
    "gross_profit": ("毛利润", "元"),
    "total_assets": ("资产总额", "元"),
    "total_liabilities": ("负债总额", "元"),
    "net_assets": ("净资产", "元"),
    "operating_cash_flow": ("经营活动现金流", "元"),
    "ar_balance": ("应收账款", "元"),
    "ap_balance": ("应付账款", "元"),
    "inventory": ("存货", "元"),
}

# 每个指标的基准值（2020 年 Q1 的"起点"），后续按 year/period 增长
_BASE_VALUES: dict[str, float] = {
    "revenue": 1_000_000_000.0,
    "net_profit": 150_000_000.0,
    "gross_profit": 400_000_000.0,
    "total_assets": 3_000_000_000.0,
    "total_liabilities": 1_600_000_000.0,
    "net_assets": 1_400_000_000.0,
    "operating_cash_flow": 200_000_000.0,
    "ar_balance": 300_000_000.0,
    "ap_balance": 250_000_000.0,
    "inventory": 180_000_000.0,
}


def _metric_value(metric: str, year: int, period: str) -> float:
    """确定性生成 (metric, year, period) 的模拟值：基准 × 年增长 × 季节因子"""
    base = _BASE_VALUES.get(metric, 100_000_000.0)
    # 年增长：每年 +18%（线性增长），2020 为基年
    year_factor = (1.18 ** max(year - 2020, 0))
    # 季节因子：Q1=0.85, Q2=0.95, Q3=1.10, Q4=1.40, H1=1.80, H2=2.50, annual=4.30
    period_factor = {
        "Q1": 0.85, "Q2": 0.95, "Q3": 1.10, "Q4": 1.40,
        "H1": 1.80, "H2": 2.50, "annual": 4.30,
    }.get(period, 1.0)
    # 指标特有调整：负债/应收/应付/存货增长慢一些；净利润波动大
    metric_adj = {
        "net_profit": 0.92,           # 利润略低于平均
        "total_liabilities": 1.05,    # 负债略高
        "ar_balance": 1.08,           # 应收增长快
        "ap_balance": 1.03,
        "inventory": 0.98,
    }.get(metric, 1.0)
    return round(base * year_factor * period_factor * metric_adj, 2)


def _change_tuple(metric: str, year: int, period: str, lag_periods: int) -> dict | None:
    """构造同比 (lag=4) / 环比 (lag=1) 变化值，去年/上季数据不存在则返回 None"""
    periods_order = ["Q1", "Q2", "Q3", "Q4"]
    if period not in periods_order:
        return None
    idx = periods_order.index(period)
    target_idx = idx - lag_periods
    target_year = year
    if target_idx < 0:
        target_idx += 4
        target_year = year - 1
    if target_year < 2020:
        return None
    target_period = periods_order[target_idx]
    cur = _metric_value(metric, year, period)
    prev = _metric_value(metric, target_year, target_period)
    if prev == 0:
        return None
    change = round(cur - prev, 2)
    change_pct = round((cur - prev) / prev, 4)
    return {"value": cur, "change": change, "change_pct": change_pct}


@router.get("/overview")
def metrics_overview(year: int = 0, period: str = "", _: dict = Depends(get_current_user)):
    """KPI 概览：返回核心指标卡片，含同比/环比变化"""
    year = year or datetime.utcnow().year
    period = period or "Q3"
    cards = []
    for metric, (label, unit) in _METRIC_META.items():
        value = _metric_value(metric, year, period)
        cards.append({
            "metric": metric,
            "label": label,
            "value": value,
            "unit": unit,
            "yoy": _change_tuple(metric, year, period, 4),
            "qoq": _change_tuple(metric, year, period, 1),
        })
    return ok({
        "year": year,
        "period": period,
        "cards": cards,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    })


@router.get("/comparison")
def metrics_comparison(
    year: int = 0,
    periods: str = "Q1,Q2,Q3,Q4",
    _: dict = Depends(get_current_user),
):
    """季度对比：返回每个指标在指定 periods 上的取值"""
    year = year or datetime.utcnow().year
    period_list = [p.strip() for p in periods.split(",") if p.strip()]
    items = []
    for metric, (label, unit) in _METRIC_META.items():
        values = {p: _metric_value(metric, year, p) for p in period_list}
        items.append({
            "metric": metric,
            "label": label,
            "unit": unit,
            "values": values,
        })
    return ok({
        "year": year,
        "periods": period_list,
        "metrics": items,
    })


@router.get("/{metric}/trend")
def metrics_trend(
    metric: str,
    years: str = "",
    _: dict = Depends(get_current_user),
):
    """年度趋势：返回指标在指定年份的年度值序列"""
    label, unit = _METRIC_META.get(metric, (metric, "元"))
    year_list = []
    if years:
        for y in years.split(","):
            y = y.strip()
            if y.isdigit():
                year_list.append(int(y))
    if not year_list:
        cur = datetime.utcnow().year
        year_list = [cur - 2, cur - 1, cur]
    series = [
        {"year": y, "value": _metric_value(metric, y, "annual")}
        for y in year_list
    ]
    return ok({
        "metric": metric,
        "label": label,
        "unit": unit,
        "series": series,
    })


@router.get("/{metric}/drill-down")
def metrics_drill_down(
    metric: str,
    year: int = 0,
    period: str = "",
    _: dict = Depends(get_current_user),
):
    """明细钻取：返回指标在该年四个季度的占比明细"""
    label, unit = _METRIC_META.get(metric, (metric, "元"))
    year = year or datetime.utcnow().year
    quarters = ["Q1", "Q2", "Q3", "Q4"]
    values = [_metric_value(metric, year, q) for q in quarters]
    total = round(sum(values), 2)
    items = []
    for q, v in zip(quarters, values):
        ratio = round(v / total, 4) if total else None
        items.append({"period": q, "value": v, "ratio": ratio})
    return ok({
        "metric": metric,
        "label": label,
        "year": year,
        "total": total,
        "items": items,
    })
