"""投资策略回测引擎 — 信号生成、交易模拟、绩效指标计算.

专业级回测功能：
- 交易成本：佣金（双向）/ 印花税（卖方）/ 滑点（买卖方向相反）
- 仓位管理：全仓 / Kelly / 固定比例 / 风险平价
- 止损止盈：按入场价的百分比止损 / 止盈
- 多资产组合回测：按权重独立运行后合并
- 严谨绩效指标：Sharpe（日频超额收益）/ Sortino / Calmar / Information Ratio / Profit Factor
- 基准对比：Alpha / Beta（基于日频收益回归）/ 超额收益
- 交易日历：跳过周末与基本中国节假日（元旦 / 春节 / 劳动节 / 国庆）
- 参数网格优化（walk-forward 友好的网格搜索）

支持策略：
- sma_cross: 均线交叉（金叉 / 死叉）
- momentum: 动量策略（动量为正买入）
- mean_reversion: 均值回归（布林带触线反转）

全部使用纯 Python 标准库实现，无外部依赖。
"""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, timedelta
from typing import Any

# 年化交易日数（向后兼容的默认值）
_TRADING_DAYS = 252
# 无风险利率（向后兼容的默认值）
_RISK_FREE_RATE = 0.03

# 农历春节（正月初一）对应公历日期映射，用于简化交易日历生成.
# 覆盖 2020-2030 年，超出范围则不跳过春节窗口.
_SPRING_FESTIVAL: dict[int, date] = {
    2020: date(2020, 1, 25),
    2021: date(2021, 2, 12),
    2022: date(2022, 2, 1),
    2023: date(2023, 1, 22),
    2024: date(2024, 2, 10),
    2025: date(2025, 1, 29),
    2026: date(2026, 2, 17),
    2027: date(2027, 2, 6),
    2028: date(2028, 1, 26),
    2029: date(2029, 2, 13),
    2030: date(2030, 2, 3),
}


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass
class BacktestConfig:
    """回测配置.

    Attributes:
        initial_capital: 初始资金
        strategy_type: 策略类型: sma_cross / momentum / mean_reversion
        period_days: 回测周期天数
        params: 策略参数
        commission_rate: 佣金费率（双向，万三默认）
        stamp_duty_rate: 印花税费率（仅卖方，千一默认）
        slippage_bps: 滑点（基点，5bps 默认）
        position_size_method: 仓位方法: full / kelly / fixed_fraction / risk_parity
        position_size_param: 仓位参数（固定比例 / Kelly 上限 / 风险平价目标波动倍数）
        stop_loss_pct: 止损百分比（相对入场价）
        take_profit_pct: 止盈百分比（相对入场价）
        risk_free_rate: 年无风险利率
        trading_days_per_year: 年化交易日数
    """

    initial_capital: float = 100000.0
    strategy_type: str = "sma_cross"
    period_days: int = 252
    params: dict[str, Any] = field(default_factory=dict)
    # 交易成本
    commission_rate: float = 0.0003
    stamp_duty_rate: float = 0.001
    slippage_bps: float = 5.0
    # 仓位管理
    position_size_method: str = "full"
    position_size_param: float = 1.0
    # 止损止盈
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    # 风险 / 年化参数
    risk_free_rate: float = 0.03
    trading_days_per_year: int = 252


@dataclass
class BacktestResult:
    """回测结果."""

    total_return: float = 0.0
    annual_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    alpha: float = 0.0
    beta: float = 0.0
    volatility: float = 0.0
    win_rate: float = 0.0
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    trade_log: list[dict[str, Any]] = field(default_factory=list)
    # 增强指标
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    information_ratio: float = 0.0
    total_trades: int = 0
    avg_trade_return: float = 0.0
    avg_holding_days: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    commission_paid: float = 0.0
    slippage_cost: float = 0.0
    benchmark_return: float = 0.0
    benchmark_annual_return: float = 0.0
    excess_return: float = 0.0
    # 额外字段：印花税（卖方）
    stamp_duty_paid: float = 0.0


# ---------------------------------------------------------------------------
# 策略实现 — 生成信号序列：1=买入, -1=卖出, 0=持有
# ---------------------------------------------------------------------------


def _sma(values: list[float], window: int) -> list[float | None]:
    """计算简单移动平均，窗口不足位置返回 None."""
    result: list[float | None] = []
    for i in range(len(values)):
        if i < window - 1:
            result.append(None)
        else:
            result.append(sum(values[i - window + 1 : i + 1]) / window)
    return result


def sma_cross_strategy(
    prices: list[float],
    short_window: int = 5,
    long_window: int = 20,
) -> list[int]:
    """均线交叉策略（金叉买入 / 死叉卖出）.

    Args:
        prices: 价格序列
        short_window: 短期均线窗口
        long_window: 长期均线窗口

    Returns:
        信号序列：1=买入, -1=卖出, 0=持有
    """
    n = len(prices)
    signals = [0] * n
    if n < long_window or short_window >= long_window:
        return signals

    short_sma = _sma(prices, short_window)
    long_sma = _sma(prices, long_window)

    for i in range(1, n):
        cur_short, cur_long = short_sma[i], long_sma[i]
        prev_short, prev_long = short_sma[i - 1], long_sma[i - 1]
        if None in (cur_short, cur_long, prev_short, prev_long):
            continue
        # 金叉：短期均线上穿长期均线
        if prev_short <= prev_long and cur_short > cur_long:  # type: ignore[operator]
            signals[i] = 1
        # 死叉：短期均线下穿长期均线
        elif prev_short >= prev_long and cur_short < cur_long:  # type: ignore[operator]
            signals[i] = -1
    return signals


def momentum_strategy(prices: list[float], lookback: int = 20) -> list[int]:
    """动量策略（过去 lookback 日收益为正买入，为负卖出）.

    Args:
        prices: 价格序列
        lookback: 动量回看窗口

    Returns:
        信号序列：1=买入, -1=卖出, 0=持有
    """
    n = len(prices)
    signals = [0] * n
    for i in range(lookback, n):
        prev_price = prices[i - lookback]
        if prev_price <= 0:
            continue
        momentum = prices[i] - prev_price
        if momentum > 0:
            signals[i] = 1
        elif momentum < 0:
            signals[i] = -1
    return signals


def mean_reversion_strategy(
    prices: list[float],
    lookback: int = 20,
    threshold: float = 2.0,
) -> list[int]:
    """均值回归策略（布林带触线反转）.

    价格跌破下轨（超卖）买入，突破上轨（超买）卖出。

    Args:
        prices: 价格序列
        lookback: 均值/标准差计算窗口
        threshold: 布林带宽度（标准差倍数）

    Returns:
        信号序列：1=买入, -1=卖出, 0=持有
    """
    n = len(prices)
    signals = [0] * n
    for i in range(lookback - 1, n):
        window = prices[i - lookback + 1 : i + 1]
        mean = sum(window) / lookback
        variance = sum((x - mean) ** 2 for x in window) / lookback
        std = math.sqrt(variance)
        upper = mean + threshold * std
        lower = mean - threshold * std
        if prices[i] < lower:
            signals[i] = 1  # 超卖买入
        elif prices[i] > upper:
            signals[i] = -1  # 超买卖出
    return signals


# ---------------------------------------------------------------------------
# 策略分发
# ---------------------------------------------------------------------------


_STRATEGY_DISPATCH: dict[str, Any] = {
    "sma_cross": sma_cross_strategy,
    "momentum": momentum_strategy,
    "mean_reversion": mean_reversion_strategy,
}


def generate_signals(config: BacktestConfig, prices: list[float]) -> list[int]:
    """根据配置分发到对应策略生成信号."""
    strategy_fn = _STRATEGY_DISPATCH.get(config.strategy_type)
    if strategy_fn is None:
        raise ValueError(
            f"不支持的策略类型: {config.strategy_type}，"
            f"可选: {', '.join(_STRATEGY_DISPATCH.keys())}"
        )
    params = config.params or {}
    # 只透传策略支持的参数，避免 TypeError
    if config.strategy_type == "sma_cross":
        return strategy_fn(
            prices,
            short_window=int(params.get("short_window", 5)),
            long_window=int(params.get("long_window", 20)),
        )
    if config.strategy_type == "momentum":
        return strategy_fn(
            prices,
            lookback=int(params.get("lookback", 20)),
        )
    return strategy_fn(
        prices,
        lookback=int(params.get("lookback", 20)),
        threshold=float(params.get("threshold", 2.0)),
    )


# ---------------------------------------------------------------------------
# 统计辅助
# ---------------------------------------------------------------------------


def _mean(values: list[float]) -> float:
    """算术均值（空序列返回 0）."""
    return sum(values) / len(values) if values else 0.0


def _pop_variance(values: list[float], mean_val: float | None = None) -> float:
    """总体方差."""
    if not values:
        return 0.0
    if mean_val is None:
        mean_val = _mean(values)
    return sum((x - mean_val) ** 2 for x in values) / len(values)


def _sample_std(values: list[float]) -> float:
    """样本标准差（ddof=1），数据少于 2 个返回 0."""
    n = len(values)
    if n < 2:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((x - m) ** 2 for x in values) / (n - 1))


def _covariance(x: list[float], y: list[float]) -> float:
    """协方差（总体）."""
    if not x or len(x) != len(y):
        return 0.0
    mean_x = _mean(x)
    mean_y = _mean(y)
    return sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y, strict=True)) / len(x)


def _daily_returns(series: list[float]) -> list[float]:
    """由价格/权益序列计算日收益率."""
    returns: list[float] = []
    for i in range(1, len(series)):
        prev = series[i - 1]
        if prev > 0:
            returns.append(series[i] / prev - 1.0)
        else:
            returns.append(0.0)
    return returns


def _max_drawdown(equity_values: list[float]) -> float:
    """由权益序列计算最大回撤."""
    if not equity_values:
        return 0.0
    max_dd = 0.0
    peak = equity_values[0]
    for v in equity_values:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak
            if dd > max_dd:
                max_dd = dd
    return max_dd


# ---------------------------------------------------------------------------
# 交易日历
# ---------------------------------------------------------------------------


def _chinese_holidays(year: int) -> set[date]:
    """返回某年的简化中国节假日集合（仅工作日落入节假日才会被跳过）.

    包含：元旦、春节（除夕至初七窗口）、劳动节（5/1-5/5）、国庆节（10/1-10/7）.
    """
    holidays: set[date] = set()
    # 元旦
    holidays.add(date(year, 1, 1))
    # 春节：正月初一前后 8 天窗口（除夕至初七）
    sf = _SPRING_FESTIVAL.get(year)
    if sf is not None:
        for offset in range(-1, 7):
            holidays.add(sf + timedelta(days=offset))
    # 劳动节 5/1-5/5
    for d in range(1, 6):
        holidays.add(date(year, 5, d))
    # 国庆节 10/1-10/7
    for d in range(1, 8):
        holidays.add(date(year, 10, d))
    return holidays


def generate_trading_calendar(start_date: str, n_days: int) -> list[str]:
    """生成真实交易日历（跳过周末与基本中国节假日）.

    Args:
        start_date: 起始日期 ``YYYY-MM-DD``（含，若为非交易日则从下一个交易日开始）
        n_days: 需要的交易日数量

    Returns:
        长度为 ``n_days`` 的日期字符串列表 ``YYYY-MM-DD``
    """
    if n_days <= 0:
        return []
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    holidays: set[date] = set()
    seen_years: set[int] = set()

    def _ensure_year(y: int) -> None:
        if y not in seen_years:
            seen_years.add(y)
            holidays.update(_chinese_holidays(y))

    _ensure_year(start.year)
    out: list[str] = []
    cur = start
    while len(out) < n_days:
        _ensure_year(cur.year)
        # weekday(): 周一=0 ... 周日=6
        if cur.weekday() < 5 and cur not in holidays:
            out.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return out


# ---------------------------------------------------------------------------
# 仓位管理
# ---------------------------------------------------------------------------


def _position_fraction(
    config: BacktestConfig,
    prices: list[float],
    index: int,
    closed_trades: list[dict[str, Any]],
) -> float:
    """根据仓位方法计算本次买入使用的资金比例（0-1）.

    - ``full``: 100% 全仓
    - ``fixed_fraction``: 使用 ``position_size_param`` 比例的资金
    - ``kelly``: 简化 Kelly 准则，``f* = win_rate - (1-win_rate)/avg_win_loss_ratio``，
      历史交易不足时回退到 ``position_size_param``，并以上限 ``position_size_param`` 截断
    - ``risk_parity``: 按近期波动率反比配置，目标日波动 = ``position_size_param * 2%``
    """
    method = config.position_size_method
    cap = max(0.0, float(config.position_size_param))

    if method == "fixed_fraction":
        return max(0.0, min(1.0, cap))

    if method == "kelly":
        if len(closed_trades) >= 5:
            wins = [t["pnl"] for t in closed_trades if t["pnl"] > 0]
            losses = [t["pnl"] for t in closed_trades if t["pnl"] < 0]
            n = len(closed_trades)
            win_rate = len(wins) / n
            avg_win = _mean(wins)
            avg_loss = -_mean(losses)  # 转为正数
            if avg_loss > 0:
                ratio = avg_win / avg_loss
                kelly = win_rate - (1.0 - win_rate) / ratio
            else:
                # 无亏损样本，倾向加大仓位
                kelly = win_rate
        else:
            kelly = cap
        kelly = max(0.0, min(cap, kelly))
        return kelly

    if method == "risk_parity":
        lookback = 20
        if index >= lookback:
            window = [float(p) for p in prices[index - lookback : index]]
            vol = _sample_std(_daily_returns(window))
        else:
            vol = 0.0
        target_vol = cap * 0.02
        if vol > 0:
            frac = target_vol / vol
        else:
            frac = cap
        return max(0.0, min(1.0, frac))

    # full 或未知方法
    return 1.0


# ---------------------------------------------------------------------------
# 指标计算
# ---------------------------------------------------------------------------


def _equity_metrics(
    equity_values: list[float],
    config: BacktestConfig,
    benchmark_series: list[float] | None,
) -> dict[str, float]:
    """由权益序列计算收益与风险类指标.

    Returns:
        包含 total_return / annual_return / sharpe_ratio / sortino_ratio /
        calmar_ratio / volatility / max_drawdown / alpha / beta /
        information_ratio / benchmark_return / benchmark_annual_return / excess_return 的字典
    """
    n = len(equity_values)
    initial = float(config.initial_capital)
    tdy = config.trading_days_per_year
    rf = config.risk_free_rate
    rf_daily = rf / tdy

    final = equity_values[-1] if equity_values else initial

    # ---- 收益 ----
    total_return = (final - initial) / initial if initial > 0 else 0.0
    years = n / tdy if n > 0 else 1.0
    if initial > 0 and final > 0 and years > 0:
        annual_return = (final / initial) ** (1.0 / years) - 1.0
    elif final <= 0:
        annual_return = -1.0
    else:
        annual_return = 0.0

    # ---- 日频收益与超额收益 ----
    daily = _daily_returns(equity_values)
    excess = [r - rf_daily for r in daily]

    # ---- 波动率（年化，样本标准差）----
    volatility = _sample_std(daily) * math.sqrt(tdy)

    # ---- Sharpe（日频超额收益，严谨版本）----
    std_excess = _sample_std(excess)
    sharpe_ratio = (
        _mean(excess) / std_excess * math.sqrt(tdy)
        if len(excess) >= 2 and std_excess > 0
        else 0.0
    )

    # ---- Sortino（仅下行偏差）----
    if daily:
        downside_sum = sum((rf_daily - r) ** 2 for r in daily if r < rf_daily)
        downside_dev = math.sqrt(downside_sum / len(daily))
    else:
        downside_dev = 0.0
    sortino_ratio = (
        _mean(excess) / downside_dev * math.sqrt(tdy) if downside_dev > 0 else 0.0
    )

    # ---- 最大回撤 ----
    max_drawdown = _max_drawdown(equity_values)

    # ---- Calmar ----
    calmar_ratio = annual_return / max_drawdown if max_drawdown > 1e-9 else 0.0

    # ---- 基准对比 ----
    bench_return = 0.0
    bench_annual = 0.0
    alpha = 0.0
    beta = 0.0
    information_ratio = 0.0

    bench = [float(b) for b in benchmark_series] if benchmark_series else []
    if bench and len(bench) >= 2 and bench[0] > 0:
        bench_return = bench[-1] / bench[0] - 1.0
        if bench[-1] > 0 and years > 0:
            bench_annual = (bench[-1] / bench[0]) ** (1.0 / years) - 1.0
        bench_daily = _daily_returns(bench)
        m = min(len(daily), len(bench_daily))
        strat_aligned = daily[:m]
        bench_aligned = bench_daily[:m]
        if m >= 2:
            bench_var = _pop_variance(bench_aligned)
            # 防止基准收益近恒定（方差极小）导致 beta 数值爆炸
            beta = _covariance(strat_aligned, bench_aligned) / bench_var if bench_var > 1e-12 else 0.0
            # Jensen's Alpha（日频回归，年化）
            strat_ex = [x - rf_daily for x in strat_aligned]
            bench_ex = [x - rf_daily for x in bench_aligned]
            alpha = (_mean(strat_ex) - beta * _mean(bench_ex)) * tdy
            # Information Ratio（主动收益年化）
            active = [s - b for s, b in zip(strat_aligned, bench_aligned, strict=True)]
            te = _sample_std(active)
            information_ratio = (
                _mean(active) / te * math.sqrt(tdy) if te > 1e-12 else 0.0
            )

    excess_return = total_return - bench_return

    return {
        "total_return": total_return,
        "annual_return": annual_return,
        "sharpe_ratio": sharpe_ratio,
        "sortino_ratio": sortino_ratio,
        "calmar_ratio": calmar_ratio,
        "volatility": volatility,
        "max_drawdown": max_drawdown,
        "alpha": alpha,
        "beta": beta,
        "information_ratio": information_ratio,
        "benchmark_return": bench_return,
        "benchmark_annual_return": bench_annual,
        "excess_return": excess_return,
    }


def _trade_metrics(closed_trades: list[dict[str, Any]]) -> dict[str, Any]:
    """由已平仓交易列表计算交易类统计指标.

    每个元素应包含: ``pnl`` / ``return_pct`` / ``holding_bars``.
    """
    total_trades = len(closed_trades)
    if total_trades == 0:
        return {
            "win_rate": 0.0,
            "total_trades": 0,
            "avg_trade_return": 0.0,
            "avg_holding_days": 0.0,
            "max_consecutive_wins": 0,
            "max_consecutive_losses": 0,
            "profit_factor": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
        }

    pnls = [t["pnl"] for t in closed_trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    win_rate = len(wins) / total_trades
    gross_profit = sum(wins)
    gross_loss = -sum(losses)  # 正数
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0

    avg_win = _mean(wins)
    avg_loss = _mean(losses)  # 负数
    avg_trade_return = _mean([t["return_pct"] for t in closed_trades])
    avg_holding_days = _mean([t["holding_bars"] for t in closed_trades])

    # 最大连续盈亏次数
    max_cw = max_cl = cur_w = cur_l = 0
    for p in pnls:
        if p > 0:
            cur_w += 1
            cur_l = 0
            max_cw = max(max_cw, cur_w)
        elif p < 0:
            cur_l += 1
            cur_w = 0
            max_cl = max(max_cl, cur_l)
        else:
            cur_w = 0
            cur_l = 0

    return {
        "win_rate": win_rate,
        "total_trades": total_trades,
        "avg_trade_return": avg_trade_return,
        "avg_holding_days": avg_holding_days,
        "max_consecutive_wins": max_cw,
        "max_consecutive_losses": max_cl,
        "profit_factor": profit_factor,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
    }


# ---------------------------------------------------------------------------
# 回测主流程
# ---------------------------------------------------------------------------


def _execute_sell(
    price: float,
    slip_factor: float,
    comm_rate: float,
    stamp_rate: float,
    shares: float,
    entry_cost_basis: float,
    entry_index: int,
    cur_index: int,
    date_str: str,
    reason: str,
    trade_log: list[dict[str, Any]],
    closed_trades: list[dict[str, Any]],
) -> tuple[float, float, float, float, float]:
    """执行卖出（含滑点 / 佣金 / 印花税），记录交易日志与已平仓交易.

    Returns:
        (net_proceeds, commission, stamp_duty, slippage, pnl)
    """
    exec_price = price * (1.0 - slip_factor)
    proceeds = shares * exec_price
    comm = proceeds * comm_rate
    stamp = proceeds * stamp_rate
    slip = shares * price * slip_factor
    net = proceeds - comm - stamp
    pnl = net - entry_cost_basis
    holding = cur_index - entry_index
    ret_pct = pnl / entry_cost_basis if entry_cost_basis > 0 else 0.0
    trade_log.append({
        "date": date_str,
        "action": "sell",
        "reason": reason,
        "price": round(price, 4),
        "exec_price": round(exec_price, 4),
        "shares": round(shares, 6),
        "pnl": round(pnl, 4),
        "return_pct": round(ret_pct, 6),
        "holding_bars": holding,
        "commission": round(comm, 4),
        "stamp_duty": round(stamp, 4),
        "slippage": round(slip, 4),
    })
    closed_trades.append({"pnl": pnl, "return_pct": ret_pct, "holding_bars": holding})
    return net, comm, stamp, slip, pnl


def run_backtest(
    config: BacktestConfig,
    prices: list[float],
    dates: list[str],
    benchmark_prices: list[float] | None = None,
) -> BacktestResult:
    """执行回测并计算绩效指标.

    交易模型：
    - 信号 1 且空仓时，按仓位方法买入
    - 信号 -1 且持仓时，清仓卖出
    - 持仓时逐 bar 检查止损 / 止盈
    - 每笔交易扣除佣金（双向）、印花税（卖方）、滑点（买卖方向相反）
    - 权益 = 现金 + 持仓股数 * 价格

    Args:
        config: 回测配置
        prices: 价格序列
        dates: 日期序列（与 prices 等长）
        benchmark_prices: 基准价格序列；为 None 时回退为标的本身的买入持有

    Returns:
        BacktestResult
    """
    n = len(prices)
    if n == 0:
        return BacktestResult()

    signals = generate_signals(config, prices)

    cash = float(config.initial_capital)
    shares = 0.0
    entry_price = 0.0
    entry_index = -1
    entry_cost_basis = 0.0  # 入场总花费（含佣金）

    commission_paid = 0.0
    slippage_cost = 0.0
    stamp_duty_paid = 0.0

    equity_curve: list[dict[str, Any]] = []
    trade_log: list[dict[str, Any]] = []
    closed_trades: list[dict[str, Any]] = []

    slip_factor = config.slippage_bps / 10000.0
    comm_rate = config.commission_rate
    stamp_rate = config.stamp_duty_rate

    for i in range(n):
        price = float(prices[i])
        sig = signals[i] if i < len(signals) else 0
        date_str = dates[i] if i < len(dates) else f"day_{i}"

        if price <= 0:
            # 价格异常，仅记录权益不交易
            pos_val = shares * price
            equity = cash + pos_val
            equity_curve.append({
                "date": date_str,
                "value": round(equity, 2),
                "position_value": round(pos_val, 2),
                "cash": round(cash, 2),
                "position_pct": round(pos_val / equity, 4) if equity > 0 else 0.0,
            })
            continue

        exited_this_bar = False

        # 1) 止损 / 止盈检查（持仓时逐 bar 检查）
        if shares > 0 and (config.stop_loss_pct is not None or config.take_profit_pct is not None):
            reason = None
            if config.stop_loss_pct is not None and price <= entry_price * (1.0 - config.stop_loss_pct):
                reason = "stop_loss"
            elif config.take_profit_pct is not None and price >= entry_price * (1.0 + config.take_profit_pct):
                reason = "take_profit"
            if reason is not None:
                net, comm, stamp, slip, _ = _execute_sell(
                    price=price,
                    slip_factor=slip_factor,
                    comm_rate=comm_rate,
                    stamp_rate=stamp_rate,
                    shares=shares,
                    entry_cost_basis=entry_cost_basis,
                    entry_index=entry_index,
                    cur_index=i,
                    date_str=date_str,
                    reason=reason,
                    trade_log=trade_log,
                    closed_trades=closed_trades,
                )
                cash += net
                commission_paid += comm
                stamp_duty_paid += stamp
                slippage_cost += slip
                shares = 0.0
                entry_price = 0.0
                entry_cost_basis = 0.0
                exited_this_bar = True

        # 2) 信号驱动交易（同一 bar 若已止损 / 止盈则不再进场）
        if not exited_this_bar:
            if sig == 1 and shares == 0:
                frac = _position_fraction(config, prices, i, closed_trades)
                allocated = cash * frac
                if allocated > 0:
                    exec_price = price * (1.0 + slip_factor)
                    # 使得 shares*exec_price*(1+comm) == allocated
                    shares = allocated / (exec_price * (1.0 + comm_rate))
                    cost = shares * exec_price
                    comm = cost * comm_rate
                    slip = shares * price * slip_factor
                    cash -= cost + comm
                    entry_price = exec_price
                    entry_index = i
                    entry_cost_basis = cost + comm
                    commission_paid += comm
                    slippage_cost += slip
                    trade_log.append({
                        "date": date_str,
                        "action": "buy",
                        "price": round(price, 4),
                        "exec_price": round(exec_price, 4),
                        "shares": round(shares, 6),
                        "cost_basis": round(entry_cost_basis, 4),
                        "commission": round(comm, 4),
                        "slippage": round(slip, 4),
                        "position_fraction": round(frac, 4),
                    })
            elif sig == -1 and shares > 0:
                net, comm, stamp, slip, _ = _execute_sell(
                    price=price,
                    slip_factor=slip_factor,
                    comm_rate=comm_rate,
                    stamp_rate=stamp_rate,
                    shares=shares,
                    entry_cost_basis=entry_cost_basis,
                    entry_index=entry_index,
                    cur_index=i,
                    date_str=date_str,
                    reason="signal",
                    trade_log=trade_log,
                    closed_trades=closed_trades,
                )
                cash += net
                commission_paid += comm
                stamp_duty_paid += stamp
                slippage_cost += slip
                shares = 0.0
                entry_price = 0.0
                entry_cost_basis = 0.0

        # 记录 bar 末权益
        pos_val = shares * price
        equity = cash + pos_val
        equity_curve.append({
            "date": date_str,
            "value": round(equity, 2),
            "position_value": round(pos_val, 2),
            "cash": round(cash, 2),
            "position_pct": round(pos_val / equity, 4) if equity > 0 else 0.0,
        })

    # ---- 指标计算 ----
    equity_values = [e["value"] for e in equity_curve]
    bench_series = (
        [float(p) for p in benchmark_prices]
        if benchmark_prices is not None
        else [float(p) for p in prices]
    )
    em = _equity_metrics(equity_values, config, bench_series)
    tm = _trade_metrics(closed_trades)

    return BacktestResult(
        total_return=round(em["total_return"], 4),
        annual_return=round(em["annual_return"], 4),
        sharpe_ratio=round(em["sharpe_ratio"], 4),
        max_drawdown=round(em["max_drawdown"], 4),
        alpha=round(em["alpha"], 4),
        beta=round(em["beta"], 4),
        volatility=round(em["volatility"], 4),
        win_rate=round(tm["win_rate"], 4),
        equity_curve=equity_curve,
        trade_log=trade_log,
        sortino_ratio=round(em["sortino_ratio"], 4),
        calmar_ratio=round(em["calmar_ratio"], 4),
        information_ratio=round(em["information_ratio"], 4),
        total_trades=tm["total_trades"],
        avg_trade_return=round(tm["avg_trade_return"], 6),
        avg_holding_days=round(tm["avg_holding_days"], 2),
        max_consecutive_wins=tm["max_consecutive_wins"],
        max_consecutive_losses=tm["max_consecutive_losses"],
        profit_factor=tm["profit_factor"],
        avg_win=round(tm["avg_win"], 4),
        avg_loss=round(tm["avg_loss"], 4),
        commission_paid=round(commission_paid, 4),
        slippage_cost=round(slippage_cost, 4),
        benchmark_return=round(em["benchmark_return"], 4),
        benchmark_annual_return=round(em["benchmark_annual_return"], 4),
        excess_return=round(em["excess_return"], 4),
        stamp_duty_paid=round(stamp_duty_paid, 4),
    )


# ---------------------------------------------------------------------------
# 模拟数据生成
# ---------------------------------------------------------------------------


def generate_mock_prices(
    n_days: int = 252,
    start_price: float = 100.0,
    volatility: float = 0.02,
    drift: float = 0.001,
) -> list[float]:
    """生成模拟价格序列（几何布朗运动），用于演示/测试.

    Args:
        n_days: 生成天数
        start_price: 起始价格
        volatility: 日波动率（标准差）
        drift: 日漂移（均值收益）

    Returns:
        长度为 n_days 的价格序列
    """
    if n_days <= 0:
        return []
    prices: list[float] = [start_price]
    for _ in range(n_days - 1):
        shock = random.gauss(0.0, 1.0)
        daily_return = drift + volatility * shock
        prices.append(prices[-1] * (1.0 + daily_return))
    return prices


def generate_mock_dates(n_days: int = 252) -> list[str]:
    """生成长度为 n_days 的简化日期标签（day_0, day_1, ...）.

    与 generate_mock_prices 配合使用，确保日期序列与价格序列等长。
    如需真实交易日历请使用 :func:`generate_trading_calendar`。
    """
    return [f"day_{i}" for i in range(n_days)]


def list_strategies() -> list[dict[str, Any]]:
    """返回可用策略列表及其描述."""
    return [
        {
            "value": "sma_cross",
            "label": "均线交叉",
            "description": "短期均线上穿长期均线（金叉）买入，下穿（死叉）卖出",
            "params": {"short_window": 5, "long_window": 20},
        },
        {
            "value": "momentum",
            "label": "动量策略",
            "description": "过去 N 日收益为正买入，为负卖出",
            "params": {"lookback": 20},
        },
        {
            "value": "mean_reversion",
            "label": "均值回归",
            "description": "布林带触线反转：跌破下轨买入，突破上轨卖出",
            "params": {"lookback": 20, "threshold": 2.0},
        },
    ]


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _json_safe(obj: Any) -> Any:
    """递归将 inf / -inf / nan 转为 None，保证 JSON 可序列化."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return obj


def result_to_dict(result: BacktestResult) -> dict[str, Any]:
    """将 BacktestResult 转换为 JSON 安全的字典."""
    return _json_safe(asdict(result))


# ---------------------------------------------------------------------------
# 参数网格优化
# ---------------------------------------------------------------------------


def _param_combos(param_grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """生成参数网格的笛卡尔积（纯 Python 递归实现，避免 itertools）."""
    keys = list(param_grid.keys())
    values_lists = [list(param_grid[k]) for k in keys]
    combos: list[dict[str, Any]] = []

    def _rec(idx: int, current: dict[str, Any]) -> None:
        if idx == len(keys):
            combos.append(dict(current))
            return
        for v in values_lists[idx]:
            current[keys[idx]] = v
            _rec(idx + 1, current)

    _rec(0, {})
    return combos


def optimize_strategy_params(
    config: BacktestConfig,
    prices: list[float],
    dates: list[str],
    param_grid: dict[str, list[Any]],
) -> dict[str, Any]:
    """参数网格优化（按 Sharpe 排序）.

    对 ``param_grid`` 的所有参数组合分别回测，记录关键指标并按 Sharpe 降序排列.

    Args:
        config: 回测配置（``params`` 中的同名键会被网格值覆盖）
        prices: 价格序列
        dates: 日期序列
        param_grid: 例如 ``{"short_window": [5, 10], "long_window": [20, 50]}``

    Returns:
        ``{"best_params": dict, "best_sharpe": float, "all_results": list[dict]}``
        其中每个 all_results 元素含 ``params / sharpe / return / max_dd / sortino / calmar / win_rate / total_trades``.
    """
    combos = _param_combos(param_grid or {})
    all_results: list[dict[str, Any]] = []
    best_sharpe = float("-inf")
    best_params: dict[str, Any] = dict(config.params or {})

    for combo in combos:
        sub_config = replace(config, params={**(config.params or {}), **combo})
        res = run_backtest(sub_config, prices, dates)
        entry = {
            "params": combo,
            "sharpe": res.sharpe_ratio,
            "return": res.total_return,
            "max_dd": res.max_drawdown,
            "sortino": res.sortino_ratio,
            "calmar": res.calmar_ratio,
            "win_rate": res.win_rate,
            "total_trades": res.total_trades,
        }
        all_results.append(entry)
        if res.sharpe_ratio > best_sharpe:
            best_sharpe = res.sharpe_ratio
            best_params = combo

    all_results.sort(key=lambda x: x["sharpe"], reverse=True)
    if not all_results:
        best_sharpe = 0.0
    return {
        "best_params": best_params,
        "best_sharpe": best_sharpe if best_sharpe != float("-inf") else 0.0,
        "all_results": all_results,
    }


# ---------------------------------------------------------------------------
# 多资产组合回测
# ---------------------------------------------------------------------------


def run_portfolio_backtest(
    config: BacktestConfig,
    assets: dict[str, list[float]],
    dates: list[str],
    weights: dict[str, float] | None = None,
) -> BacktestResult:
    """多资产组合回测.

    对每个资产独立运行策略（按权重分配子资金），再按权重合并为组合权益曲线与统计指标.

    Args:
        config: 回测配置（``initial_capital`` 为组合总资金）
        assets: ``{symbol: price_list}``
        dates: 日期序列
        weights: ``{symbol: weight}``，为 None 时等权

    Returns:
        BacktestResult（合并后的组合结果，交易日志带 ``symbol`` 字段）
    """
    symbols = list(assets.keys())
    if not symbols:
        return BacktestResult()

    if weights is None:
        w = {s: 1.0 / len(symbols) for s in symbols}
    else:
        total = sum(float(weights.get(s, 0.0)) for s in symbols) or 1.0
        w = {s: float(weights.get(s, 0.0)) / total for s in symbols}

    per_asset_curves: list[list[dict[str, Any]]] = []
    combined_trade_log: list[dict[str, Any]] = []
    closed_trades: list[dict[str, Any]] = []
    commission_paid = 0.0
    slippage_cost = 0.0
    stamp_duty_paid = 0.0

    for sym in symbols:
        sub_config = replace(config, initial_capital=float(config.initial_capital) * w[sym])
        prices = list(assets[sym])
        res = run_backtest(sub_config, prices, dates)
        per_asset_curves.append(res.equity_curve)
        commission_paid += res.commission_paid
        slippage_cost += res.slippage_cost
        stamp_duty_paid += res.stamp_duty_paid
        for t in res.trade_log:
            tt = dict(t)
            tt["symbol"] = sym
            combined_trade_log.append(tt)
            if t.get("action") == "sell":
                closed_trades.append({
                    "pnl": t.get("pnl", 0.0),
                    "return_pct": t.get("return_pct", 0.0),
                    "holding_bars": t.get("holding_bars", 0),
                })

    # 组合权益曲线（按最小长度对齐）
    m = min((len(c) for c in per_asset_curves), default=0)
    combined_curve: list[dict[str, Any]] = []
    combined_values: list[float] = []
    for i in range(m):
        date_str = dates[i] if i < len(dates) else f"day_{i}"
        value = sum(c[i]["value"] for c in per_asset_curves)
        pos = sum(c[i].get("position_value", 0.0) for c in per_asset_curves)
        cash = sum(c[i].get("cash", 0.0) for c in per_asset_curves)
        combined_curve.append({
            "date": date_str,
            "value": round(value, 2),
            "position_value": round(pos, 2),
            "cash": round(cash, 2),
            "position_pct": round(pos / value, 4) if value > 0 else 0.0,
        })
        combined_values.append(value)

    # 基准：加权买入持有
    bench_series: list[float] = []
    for i in range(m):
        bv = 0.0
        for sym in symbols:
            ps = list(assets[sym])
            if i < len(ps) and ps[0] > 0:
                bv += float(config.initial_capital) * w[sym] * (ps[i] / ps[0])
        bench_series.append(bv)

    em = _equity_metrics(combined_values, config, bench_series)
    tm = _trade_metrics(closed_trades)

    return BacktestResult(
        total_return=round(em["total_return"], 4),
        annual_return=round(em["annual_return"], 4),
        sharpe_ratio=round(em["sharpe_ratio"], 4),
        max_drawdown=round(em["max_drawdown"], 4),
        alpha=round(em["alpha"], 4),
        beta=round(em["beta"], 4),
        volatility=round(em["volatility"], 4),
        win_rate=round(tm["win_rate"], 4),
        equity_curve=combined_curve,
        trade_log=combined_trade_log,
        sortino_ratio=round(em["sortino_ratio"], 4),
        calmar_ratio=round(em["calmar_ratio"], 4),
        information_ratio=round(em["information_ratio"], 4),
        total_trades=tm["total_trades"],
        avg_trade_return=round(tm["avg_trade_return"], 6),
        avg_holding_days=round(tm["avg_holding_days"], 2),
        max_consecutive_wins=tm["max_consecutive_wins"],
        max_consecutive_losses=tm["max_consecutive_losses"],
        profit_factor=tm["profit_factor"],
        avg_win=round(tm["avg_win"], 4),
        avg_loss=round(tm["avg_loss"], 4),
        commission_paid=round(commission_paid, 4),
        slippage_cost=round(slippage_cost, 4),
        benchmark_return=round(em["benchmark_return"], 4),
        benchmark_annual_return=round(em["benchmark_annual_return"], 4),
        excess_return=round(em["excess_return"], 4),
        stamp_duty_paid=round(stamp_duty_paid, 4),
    )