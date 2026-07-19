"""回测路由 — 投资策略回测引擎.

端点：
- POST /run              单资产策略回测（含交易成本 / 仓位管理 / 止损止盈 / 基准对比）
- POST /run-portfolio    多资产组合回测
- POST /optimize         参数网格优化
- GET  /trading-calendar 生成真实交易日历
- GET  /strategies       可用策略列表
- POST /generate-mock-data 生成模拟价格数据
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

# TODO: FinPilot deps 暂未提供 get_current_user_or_api_key（带 API Key + scope 校验），
#       暂用 get_current_user；如需 API Key 鉴权与 scope 校验，需扩展 finpilot.api.deps。
# TODO: FinPilot 暂未直接引用 User ORM 模型作为依赖返回类型，认证依赖返回 dict。
from finpilot.api.deps import get_current_user

router = APIRouter(prefix="/backtesting", tags=["Backtesting"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class _BacktestOptions(BaseModel):
    """回测可选项（交易成本 / 仓位 / 止损止盈 / 风险参数）."""

    commission_rate: float = Field(default=0.0003, description="佣金费率（双向，万三）")
    stamp_duty_rate: float = Field(default=0.001, description="印花税费率（仅卖方，千一）")
    slippage_bps: float = Field(default=5.0, description="滑点（基点）")
    position_size_method: str = Field(
        default="full", description="仓位方法: full/kelly/fixed_fraction/risk_parity"
    )
    position_size_param: float = Field(default=1.0, description="仓位参数")
    stop_loss_pct: float | None = Field(default=None, description="止损百分比（相对入场价）")
    take_profit_pct: float | None = Field(default=None, description="止盈百分比（相对入场价）")
    risk_free_rate: float = Field(default=0.03, description="年无风险利率")
    trading_days_per_year: int = Field(default=252, description="年化交易日数")


class BacktestRequest(_BacktestOptions):
    """单资产回测请求（配置 + 价格 + 日期）."""

    initial_capital: float = Field(default=100000, description="初始资金")
    strategy_type: str = Field(..., description="策略类型: sma_cross/momentum/mean_reversion")
    period_days: int = Field(default=252, description="回测周期天数")
    params: dict[str, Any] = Field(default_factory=dict, description="策略参数")
    prices: list[float] = Field(..., description="价格序列")
    dates: list[str] = Field(..., description="日期序列（与 prices 等长）")
    benchmark_prices: list[float] | None = Field(default=None, description="基准价格序列")


class PortfolioBacktestRequest(_BacktestOptions):
    """多资产组合回测请求."""

    initial_capital: float = Field(default=100000, description="初始资金（组合总资金）")
    strategy_type: str = Field(default="sma_cross", description="策略类型")
    period_days: int = Field(default=252, description="回测周期天数")
    params: dict[str, Any] = Field(default_factory=dict, description="策略参数")
    assets: dict[str, list[float]] = Field(..., description="{symbol: 价格序列}")
    dates: list[str] = Field(..., description="日期序列")
    weights: dict[str, float] | None = Field(
        default=None, description="{symbol: 权重}，缺省等权"
    )


class OptimizeRequest(_BacktestOptions):
    """参数网格优化请求."""

    initial_capital: float = Field(default=100000, description="初始资金")
    strategy_type: str = Field(default="sma_cross", description="策略类型")
    period_days: int = Field(default=252, description="回测周期天数")
    params: dict[str, Any] = Field(default_factory=dict, description="基础策略参数")
    prices: list[float] = Field(..., description="价格序列")
    dates: list[str] = Field(..., description="日期序列")
    param_grid: dict[str, list[Any]] = Field(..., description="参数网格")


class TradingCalendarRequest(BaseModel):
    """交易日历生成请求."""

    start_date: str = Field(..., description="起始日期 YYYY-MM-DD")
    n_days: int = Field(default=252, description="需要的交易日数量")


class MockDataRequest(BaseModel):
    """模拟数据生成请求."""

    n_days: int = Field(default=252, description="生成天数")
    start_price: float = Field(default=100, description="起始价格")
    volatility: float = Field(default=0.02, description="日波动率")
    drift: float = Field(default=0.001, description="日漂移")


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _config_kwargs(body: Any) -> dict[str, Any]:
    """从请求体提取 BacktestConfig 所需字段（新字段缺失时用默认值）."""
    return {
        "initial_capital": body.initial_capital,
        "strategy_type": body.strategy_type,
        "period_days": body.period_days,
        "params": body.params,
        "commission_rate": getattr(body, "commission_rate", 0.0003),
        "stamp_duty_rate": getattr(body, "stamp_duty_rate", 0.001),
        "slippage_bps": getattr(body, "slippage_bps", 5.0),
        "position_size_method": getattr(body, "position_size_method", "full"),
        "position_size_param": getattr(body, "position_size_param", 1.0),
        "stop_loss_pct": getattr(body, "stop_loss_pct", None),
        "take_profit_pct": getattr(body, "take_profit_pct", None),
        "risk_free_rate": getattr(body, "risk_free_rate", 0.03),
        "trading_days_per_year": getattr(body, "trading_days_per_year", 252),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/run")
def run_backtest_endpoint(
    body: BacktestRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """执行策略回测并返回绩效指标.

    支持交易成本、仓位管理、止损止盈与基准对比。未提供基准时回退为标的自身的买入持有。
    """
    from finpilot.services.backtesting import BacktestConfig, result_to_dict, run_backtest

    config = BacktestConfig(**_config_kwargs(body))
    result = run_backtest(
        config=config,
        prices=body.prices,
        dates=body.dates,
        benchmark_prices=body.benchmark_prices,
    )
    return {"code": 0, "message": "ok", "data": result_to_dict(result)}


@router.post("/run-portfolio")
def run_portfolio_backtest_endpoint(
    body: PortfolioBacktestRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """多资产组合回测.

    对每个资产独立运行策略，按权重合并为组合权益曲线与统计指标。
    ``weights`` 为空时等权配置。
    """
    from finpilot.services.backtesting import (
        BacktestConfig,
        result_to_dict,
        run_portfolio_backtest,
    )

    config = BacktestConfig(**_config_kwargs(body))
    result = run_portfolio_backtest(
        config=config,
        assets=body.assets,
        dates=body.dates,
        weights=body.weights,
    )
    return {"code": 0, "message": "ok", "data": result_to_dict(result)}


@router.post("/optimize")
def optimize_endpoint(
    body: OptimizeRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """参数网格优化（按 Sharpe 排序）.

    对参数网格的所有组合分别回测，返回最优参数与全部结果。
    """
    from finpilot.services.backtesting import BacktestConfig, optimize_strategy_params

    config = BacktestConfig(**_config_kwargs(body))
    result = optimize_strategy_params(
        config=config,
        prices=body.prices,
        dates=body.dates,
        param_grid=body.param_grid,
    )
    return {"code": 0, "message": "ok", "data": result}


@router.get("/trading-calendar")
def trading_calendar_endpoint(
    start_date: str = Query(..., description="起始日期 YYYY-MM-DD"),
    n_days: int = Query(default=252, description="需要的交易日数量"),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """生成真实交易日历（跳过周末与基本中国节假日）."""
    from finpilot.services.backtesting import generate_trading_calendar

    dates = generate_trading_calendar(start_date, n_days)
    return {"code": 0, "message": "ok", "data": {"dates": dates}}


@router.post("/trading-calendar")
def trading_calendar_post_endpoint(
    body: TradingCalendarRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """生成真实交易日历（POST 版本，便于请求体传参）."""
    from finpilot.services.backtesting import generate_trading_calendar

    dates = generate_trading_calendar(body.start_date, body.n_days)
    return {"code": 0, "message": "ok", "data": {"dates": dates}}


@router.get("/strategies")
def list_strategies(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """返回可用策略类型及描述."""
    from finpilot.services.backtesting import list_strategies as _list_strategies

    return {"code": 0, "message": "ok", "data": _list_strategies()}


@router.post("/generate-mock-data")
def generate_mock_data(
    body: MockDataRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """生成模拟价格数据用于演示."""
    from finpilot.services.backtesting import generate_mock_dates, generate_mock_prices

    prices = generate_mock_prices(
        n_days=body.n_days,
        start_price=body.start_price,
        volatility=body.volatility,
        drift=body.drift,
    )
    dates = generate_mock_dates(body.n_days)
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "prices": [round(p, 4) for p in prices],
            "dates": dates,
        },
    }
