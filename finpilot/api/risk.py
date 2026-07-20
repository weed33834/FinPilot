# -*- coding: utf-8 -*-
"""风险预警引擎路由 — 时序预测 + 风险分类 + 舞弊识别 + 预警规则 API 入口。

POST /api/v1/risk/assess     一站式风险评估
GET  /api/v1/risk/thresholds 返回 7 个指标的风险区间阈值
GET  /api/v1/risk/warning-rules 返回 5 条默认预警规则
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from finpilot.api.deps import get_current_user

router = APIRouter(prefix="/risk", tags=["Risk"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AssessRequest(BaseModel):
    """风险评估请求：所有字段可选，只对提供的字段跑评估。"""

    metrics: dict[str, float] | None = Field(
        default=None,
        description="风险指标字典，键可为 debt_ratio/current_ratio/gross_margin/"
        "net_margin/ar_turnover_days/inventory_turnover_days/ocf_to_revenue",
    )
    monthly_revenue: list[dict[str, Any]] | None = Field(
        default=None,
        description="月度营收序列，用于期末激增舞弊识别，每个元素含 month/revenue",
    )
    revenue_growth: float | None = Field(default=None, description="营收增长率")
    ar_growth: float | None = Field(default=None, description="应收账款增长率")
    net_profit: float | None = Field(default=None, description="净利润")
    operating_cash_flow: float | None = Field(default=None, description="经营现金流")
    inventory_turnover_current: float | None = Field(default=None, description="本期存货周转率")
    inventory_turnover_prev: float | None = Field(default=None, description="上期存货周转率")
    gross_margin_current: float | None = Field(default=None, description="本期毛利率")
    gross_margin_prev: float | None = Field(default=None, description="上期毛利率")
    forecast_series: dict[str, list[float]] | None = Field(
        default=None,
        description="时序预测数据 {metric_name: [v1, v2, ...]}，长度 >= 3 才会预测",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/assess")
def assess_endpoint(
    body: AssessRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """一站式风险评估，返回 RiskReport。"""
    from finpilot.risk import assess_risk

    kwargs: dict[str, Any] = body.model_dump(exclude_none=True)
    try:
        report = assess_risk(**kwargs)
    except TypeError as exc:
        return {"code": 1, "message": f"参数格式错误: {exc}", "data": None}
    return {"code": 0, "message": "ok", "data": report.to_dict()}


@router.get("/thresholds")
def list_thresholds(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """返回 7 个指标的默认风险区间阈值。"""
    from finpilot.risk import DEFAULT_THRESHOLDS

    data = [
        {
            "metric_name": name,
            "high_threshold": t.high_threshold,
            "low_threshold": t.low_threshold,
            "direction": t.direction,
            "description": t.description,
        }
        for name, t in DEFAULT_THRESHOLDS.items()
    ]
    return {"code": 0, "message": "ok", "data": data}


@router.get("/warning-rules")
def list_warning_rules(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """返回默认预警规则。"""
    from finpilot.risk.engine import _build_default_rules

    rules = [
        {
            "rule_id": r.rule_id,
            "metric_name": r.metric_name,
            "level": r.level,
            "severity": r.severity,
            "message": r.message,
            "suggestion": r.suggestion,
        }
        for r in _build_default_rules()
    ]
    return {"code": 0, "message": "ok", "data": rules}
