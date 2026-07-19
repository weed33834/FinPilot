"""因子挖掘路由 — 发现财务数据中的 alpha 因子."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

# TODO: FinPilot deps 暂未提供 get_current_user_or_api_key（带 API Key + scope 校验），
#       暂用 get_current_user；如需 API Key 鉴权与 scope 校验，需扩展 finpilot.api.deps。
# TODO: FinPilot 暂未直接引用 User ORM 模型作为依赖返回类型，认证依赖返回 dict。
from finpilot.api.deps import get_current_user

router = APIRouter(prefix="/factor-mining", tags=["Factor Mining"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class MineRequest(BaseModel):
    """因子挖掘请求（计算因子 + IC 评估）."""

    financial_data: list[dict[str, Any]] = Field(
        ..., description="公司财务数据列表，每个元素为一家公司的财务指标"
    )
    forward_returns: dict[str, float] | None = Field(
        default=None, description="前瞻收益 {symbol: return}，提供后用于 IC 评估"
    )


class CalculateRequest(BaseModel):
    """因子计算请求（仅计算因子值，不做 IC 评估）."""

    financial_data: list[dict[str, Any]] = Field(
        ..., description="公司财务数据列表，每个元素为一家公司的财务指标"
    )


class MineDeepRequest(BaseModel):
    """深度因子挖掘请求（中性化 + 多期 IR + 衰减 + 相关性）."""

    financial_data: list[dict[str, Any]] = Field(
        ..., description="公司财务数据列表，每个元素为一家公司的财务指标"
    )
    forward_returns: dict[str, float] | None = Field(
        default=None, description="单期前瞻收益 {symbol: return}，提供后用于单期 IC 评估"
    )
    period_returns: list[dict[str, float]] | None = Field(
        default=None, description="多期收益序列，每个元素为一周期的 {symbol: return}，用于真实 IR 与衰减分析"
    )
    neutralization_data: dict[str, dict[str, Any]] | None = Field(
        default=None,
        description="中性化数据 {symbol: {'industry': str, 'market_cap': float}}，"
        "提供后自动中性化（含市值则 both，否则 industry）",
    )
    max_decay_lag: int = Field(default=12, description="衰减分析最大期数")


class NeutralizeRequest(BaseModel):
    """因子中性化请求."""

    factor_values: dict[str, float] = Field(
        ..., description="待中性化的因子值 {symbol: value}"
    )
    neutralization_data: dict[str, dict[str, Any]] = Field(
        ..., description="中性化数据 {symbol: {'industry': str, 'market_cap': float}}"
    )
    method: str = Field(
        default="industry",
        description="中性化方式: industry / market_cap / both",
    )


class DecayAnalysisRequest(BaseModel):
    """因子衰减分析请求."""

    factor_values: dict[str, float] = Field(
        ..., description="基期截面因子值 {symbol: value}"
    )
    period_returns: list[dict[str, float]] = Field(
        ..., description="未来各期收益序列，每个元素为 {symbol: return}"
    )
    max_lag: int = Field(default=12, description="最大考察期数")


class CorrelationRequest(BaseModel):
    """因子相关性分析请求."""

    factors: list[dict[str, Any]] = Field(
        ...,
        description="因子列表，每个元素需含 name 与 values({symbol: value})，"
        "可由 /calculate 或 /mine 返回的 FactorResult 直接传入",
    )


# ---------------------------------------------------------------------------
# Endpoints（向后兼容）
# ---------------------------------------------------------------------------


@router.post("/mine")
def mine_factors_endpoint(
    body: MineRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """执行完整因子挖掘流程（计算因子 + 可选 IC 评估）."""
    from finpilot.services.factor_mining import mine_factors

    result = mine_factors(
        financial_data=body.financial_data,
        forward_returns=body.forward_returns,
    )
    return {"code": 0, "message": "ok", "data": result}


@router.post("/calculate")
def calculate_factors_endpoint(
    body: CalculateRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """仅计算因子值（不做 IC 评估）."""
    from finpilot.services.factor_mining import calculate_factors

    factors = calculate_factors(financial_data=body.financial_data)
    return {"code": 0, "message": "ok", "data": [asdict(f) for f in factors]}


@router.get("/factor-categories")
def list_factor_categories(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """返回可用因子分类."""
    categories = [
        {
            "value": "momentum",
            "label": "动量因子",
            "description": "营收增长率、利润增长率等基本面动量因子",
        },
        {
            "value": "value",
            "label": "价值因子",
            "description": "PE、PB、PS、EV/EBITDA 等估值类因子",
        },
        {
            "value": "quality",
            "label": "质量因子",
            "description": "ROE、ROA、毛利率、净利率、流动比率等盈利能力因子",
        },
        {
            "value": "growth",
            "label": "成长因子",
            "description": "资产增长等成长性因子",
        },
        {
            "value": "volatility",
            "label": "波动因子",
            "description": "价格波动率、盈利波动率等风险类因子",
        },
    ]
    return {"code": 0, "message": "ok", "data": categories}


# ---------------------------------------------------------------------------
# 新增端点：深度分析
# ---------------------------------------------------------------------------


@router.post("/mine-deep")
def mine_factors_deep_endpoint(
    body: MineDeepRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """执行深度因子挖掘流水线（中性化 + 多期 IR + 单期 IC + 衰减 + 相关性）."""
    from finpilot.services.factor_mining import mine_factors_deep

    result = mine_factors_deep(
        financial_data=body.financial_data,
        forward_returns=body.forward_returns,
        period_returns=body.period_returns,
        neutralization_data=body.neutralization_data,
        max_decay_lag=body.max_decay_lag,
    )
    return {"code": 0, "message": "ok", "data": result}


@router.post("/neutralize")
def neutralize_factor_endpoint(
    body: NeutralizeRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """对单个因子执行行业 / 市值中性化."""
    from finpilot.services.factor_mining import neutralize_factor

    neutralized = neutralize_factor(
        factor_values=body.factor_values,
        neutralization_data=body.neutralization_data,
        method=body.method,
    )
    return {"code": 0, "message": "ok", "data": {"neutralized_values": neutralized}}


@router.post("/decay-analysis")
def decay_analysis_endpoint(
    body: DecayAnalysisRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """分析因子预测能力的衰减（half-life）."""
    from finpilot.services.factor_mining import analyze_factor_decay

    result = analyze_factor_decay(
        factor_values=body.factor_values,
        period_returns=body.period_returns,
        max_lag=body.max_lag,
    )
    return {"code": 0, "message": "ok", "data": result}


@router.post("/correlation")
def correlation_endpoint(
    body: CorrelationRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """计算因子间相关性矩阵与聚类."""
    from finpilot.services.factor_mining import FactorResult, analyze_factor_correlation

    factors: list[FactorResult] = []
    for item in body.factors:
        name = item.get("name", "")
        category = item.get("category", "")
        values = item.get("values", {}) or {}
        factors.append(
            FactorResult(
                name=name,
                category=category,
                values={k: float(v) for k, v in values.items()},
            )
        )
    result = analyze_factor_correlation(factors)
    return {"code": 0, "message": "ok", "data": result}
