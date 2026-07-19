"""估值分析路由 — DCF/WACC/DDM 计算 + 辩论分析."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

# TODO: FinPilot deps 暂未提供 get_current_user_or_api_key（带 API Key + scope 校验），
#       暂用 get_current_user；如需 API Key 鉴权与 scope 校验，需扩展 finpilot.api.deps。
# TODO: FinPilot 暂未引入多租户(tenant_id)概念，user.tenant_id 暂以 user_id 字符串替代。
from finpilot.api.deps import get_current_user, get_db_session

router = APIRouter(prefix="/valuation", tags=["Valuation"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class DcfRequest(BaseModel):
    """DCF 估值请求."""
    free_cash_flows: list[float] = Field(..., description="预测期各年自由现金流")
    wacc: float = Field(default=0.10, description="加权平均资本成本")
    terminal_growth_rate: float = Field(default=0.03, description="永续增长率")
    shares_outstanding: float | None = Field(default=None, description="总股本")
    total_debt: float = Field(default=0, description="总债务")
    cash_and_equivalents: float = Field(default=0, description="现金及等价物")


class WaccRequest(BaseModel):
    """WACC 计算请求."""
    market_cap: float = Field(..., description="市值")
    total_debt: float = Field(default=0, description="总债务")
    cost_of_equity: float = Field(default=0.10, description="权益成本")
    cost_of_debt: float = Field(default=0.06, description="债务成本")
    tax_rate: float = Field(default=0.25, description="所得税率")


class DdmRequest(BaseModel):
    """DDM 估值请求."""
    dividend_per_share: float = Field(..., description="当前每股股息")
    growth_rate: float = Field(default=0.05, description="高增长期年增长率")
    discount_rate: float = Field(default=0.08, description="折现率")
    high_growth_years: int = Field(default=5, description="高增长期年数")
    terminal_growth_rate: float = Field(default=0.03, description="永续增长率")


class DebateRequest(BaseModel):
    """辩论分析请求."""

    question: str = Field(..., description="分析问题")
    financial_data: dict[str, Any] = Field(default_factory=dict, description="财务数据")


class MultiRoundDebateRequest(BaseModel):
    """多轮对抗式辩论请求."""

    question: str = Field(..., description="分析问题")
    financial_data: dict[str, Any] = Field(default_factory=dict, description="财务数据")
    rounds: int = Field(default=3, description="辩论轮数")


class ArgumentItem(BaseModel):
    """单个辩论论点."""

    point: str = Field(default="", description="论点观点")
    supporting_data: list[str] = Field(default_factory=list, description="数据支撑")
    confidence: float = Field(default=0.5, description="置信度 0-1")
    side: str = Field(default="", description="看涨/看跌 (bull/bear)")


class ScoreArgumentsRequest(BaseModel):
    """论点评分请求."""

    arguments: list[ArgumentItem] = Field(..., description="待评分论点列表")
    question: str = Field(default="", description="原始分析问题")
    financial_data: dict[str, Any] = Field(default_factory=dict, description="财务数据")


class FactCheckRequest(BaseModel):
    """论点事实核查请求."""

    arguments: list[ArgumentItem] = Field(..., description="待核查论点列表")
    financial_data: dict[str, Any] = Field(default_factory=dict, description="实际财务数据")


class SensitivityRequest(BaseModel):
    """敏感性分析请求."""

    base_params: dict[str, Any] = Field(..., description="基准参数")
    param_ranges: dict[str, list] = Field(..., description="各参数取值范围")


class ScenarioRequest(BaseModel):
    """情景分析请求."""

    base_params: dict[str, Any] = Field(..., description="基准参数")
    scenarios: list[dict[str, Any]] = Field(..., description="情景列表")


class CompsRequest(BaseModel):
    """可比公司分析请求."""

    target_metrics: dict[str, Any] = Field(..., description="目标公司指标")
    peers: list[dict[str, Any]] = Field(..., description="可比公司列表")


class MonteCarloRequest(BaseModel):
    """蒙特卡洛估值请求."""

    base_params: dict[str, Any] = Field(..., description="基准参数")
    n_simulations: int = Field(default=10000, description="模拟次数")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/dcf")
def calculate_dcf(
    body: DcfRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """计算 DCF 估值."""
    from finpilot.services.valuation_service import calculate_dcf, valuation_to_dict

    result = calculate_dcf(
        free_cash_flows=body.free_cash_flows,
        wacc=body.wacc,
        terminal_growth_rate=body.terminal_growth_rate,
        shares_outstanding=body.shares_outstanding,
        total_debt=body.total_debt,
        cash_and_equivalents=body.cash_and_equivalents,
    )
    return {"code": 0, "message": "ok", "data": valuation_to_dict(result)}


@router.post("/wacc")
def calculate_wacc(
    body: WaccRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """计算 WACC."""
    from finpilot.services.valuation_service import calculate_wacc, valuation_to_dict

    result = calculate_wacc(
        market_cap=body.market_cap,
        total_debt=body.total_debt,
        cost_of_equity=body.cost_of_equity,
        cost_of_debt=body.cost_of_debt,
        tax_rate=body.tax_rate,
    )
    return {"code": 0, "message": "ok", "data": valuation_to_dict(result)}


@router.post("/ddm")
def calculate_ddm(
    body: DdmRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """计算 DDM 估值."""
    from finpilot.services.valuation_service import calculate_ddm, valuation_to_dict

    result = calculate_ddm(
        dividend_per_share=body.dividend_per_share,
        growth_rate=body.growth_rate,
        discount_rate=body.discount_rate,
        high_growth_years=body.high_growth_years,
        terminal_growth_rate=body.terminal_growth_rate,
    )
    return {"code": 0, "message": "ok", "data": valuation_to_dict(result)}


@router.post("/debate")
def run_debate(
    body: DebateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """执行看涨/看跌辩论分析."""
    from dataclasses import asdict

    from finpilot.services.debate_service import run_debate

    # TODO: FinPilot 暂无 tenant_id，暂以 user_id 字符串作为租户标识。
    result = run_debate(
        question=body.question,
        financial_data=body.financial_data,
        tenant_id=str(current_user.get("user_id", "default")),
    )
    return {"code": 0, "message": "ok", "data": asdict(result)}


# ---------------------------------------------------------------------------
# 多轮辩论 / 论点评分 / 事实核查
# ---------------------------------------------------------------------------


def _argument_items_to_objects(items: list[ArgumentItem]) -> list:
    """将请求中的 ArgumentItem 转为 DebateArgument 对象."""
    from finpilot.services.debate_service import DebateArgument

    return [
        DebateArgument(
            point=item.point,
            supporting_data=item.supporting_data,
            confidence=item.confidence,
            side=item.side,
        )
        for item in items
    ]


@router.post("/debate/multi-round")
def multi_round_debate(
    body: MultiRoundDebateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """执行多轮对抗式辩论分析."""
    from finpilot.services.debate_service import run_multi_round_debate

    result = run_multi_round_debate(
        question=body.question,
        financial_data=body.financial_data,
        tenant_id=str(current_user.get("user_id", "default")),
        db=db,
        rounds=body.rounds,
    )
    return {"code": 0, "message": "ok", "data": result}


@router.post("/debate/score")
def score_arguments(
    body: ScoreArgumentsRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """对辩论论点进行多维度评分."""
    from finpilot.services.debate_service import score_arguments as _score_arguments

    arguments = _argument_items_to_objects(body.arguments)
    result = _score_arguments(
        arguments=arguments,
        question=body.question,
        financial_data=body.financial_data,
    )
    return {"code": 0, "message": "ok", "data": result}


@router.post("/debate/fact-check")
def fact_check(
    body: FactCheckRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """对辩论论点引用的数据进行事实核查."""
    from finpilot.services.debate_service import check_argument_facts

    arguments = _argument_items_to_objects(body.arguments)
    result = check_argument_facts(
        arguments=arguments,
        financial_data=body.financial_data,
    )
    return {"code": 0, "message": "ok", "data": result}


# ---------------------------------------------------------------------------
# 进阶估值分析：敏感性 / 情景 / 可比公司 / 蒙特卡洛
# ---------------------------------------------------------------------------


@router.post("/sensitivity")
def sensitivity(
    body: SensitivityRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """敏感性分析（龙卷风图）."""
    from finpilot.services.valuation_service import sensitivity_analysis

    result = sensitivity_analysis(
        base_params=body.base_params,
        param_ranges=body.param_ranges,
    )
    return {"code": 0, "message": "ok", "data": result}


@router.post("/scenario")
def scenario(
    body: ScenarioRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """情景分析."""
    from finpilot.services.valuation_service import scenario_analysis

    result = scenario_analysis(
        base_params=body.base_params,
        scenarios=body.scenarios,
    )
    return {"code": 0, "message": "ok", "data": result}


@router.post("/comps")
def comps(
    body: CompsRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """可比公司分析."""
    from finpilot.services.valuation_service import comparable_company_analysis

    result = comparable_company_analysis(
        target_metrics=body.target_metrics,
        peers=body.peers,
    )
    return {"code": 0, "message": "ok", "data": result}


@router.post("/monte-carlo")
def monte_carlo(
    body: MonteCarloRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """蒙特卡洛估值模拟."""
    from finpilot.services.valuation_service import monte_carlo_valuation

    result = monte_carlo_valuation(
        base_params=body.base_params,
        n_simulations=body.n_simulations,
    )
    return {"code": 0, "message": "ok", "data": result}
