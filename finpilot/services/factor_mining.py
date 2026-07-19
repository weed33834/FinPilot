"""因子挖掘服务 — 发现财务数据中的 alpha 因子.

专业级量化因子分析工具，覆盖因子计算、IC 评估、多期 IR、中性化、
衰减分析与因子相关性聚类。

支持的因子类型：
- 动量因子 (momentum): revenue_growth、profit_growth（由 prev_revenue/prev_net_profit 计算）
- 价值因子 (value): PE、PB、PS、EV/EBITDA
- 质量因子 (quality): ROE、ROA、gross_margin、net_margin、current_ratio
- 成长因子 (growth): asset_growth
- 波动因子 (volatility): price_volatility、earnings_volatility

评估指标：
- IC (Information Coefficient): 因子值与收益的 Spearman 秩相关系数（含 ties 处理）
- IC t-stat / p-value: 基于 t 分布的统计显著性检验
- IR (Information Ratio): 多期 IC 均值 / IC 标准差（真实 IR，仅在多期评估时有意义）
- IC 胜率: 单期为同向截面配对比例；多期为 IC>0 的周期占比

所有数学计算仅依赖 Python 标准库 (math / statistics)。
"""

from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class FactorResult:
    """因子评估结果."""

    name: str
    category: str
    values: dict[str, float] = field(default_factory=dict)
    ic: float = 0.0
    ir: float = 0.0
    ic_win_rate: float = 0.0
    ic_mean: float = 0.0
    ic_std: float = 0.0
    rank: int = 0
    description: str = ""
    # 新增统计字段（带默认值，保持向后兼容）
    ic_tstat: float = 0.0
    ic_pvalue: float = 1.0
    n: int = 0


# ---------------------------------------------------------------------------
# 纯数学工具：秩、Pearson、Spearman、t 分布 p-value
# ---------------------------------------------------------------------------


def _rank_average(values: list[float]) -> list[float]:
    """计算平均秩（ties 使用平均秩，与标准 Spearman 定义一致）.

    Args:
        values: 数值列表

    Returns:
        与输入等长的秩列表（1-based，ties 取平均）
    """
    n = len(values)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        # 找出所有与 values[order[i]] 相等的元素，区间 [i, j]
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        # 1-based 秩：位置 i..j 对应秩 i+1..j+1，平均秩 = (i+1 + j+1) / 2
        avg = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(x: list[float], y: list[float]) -> float:
    """计算 Pearson 相关系数.

    用于含 ties 时的 Spearman（对秩做 Pearson）以及因子间相关性。
    """
    n = len(x)
    if n == 0:
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    sxy = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    sxx = sum((x[i] - mx) ** 2 for i in range(n))
    syy = sum((y[i] - my) ** 2 for i in range(n))
    denom = math.sqrt(sxx * syy)
    if denom == 0.0:
        return 0.0
    return sxy / denom


def _betacf(a: float, b: float, x: float) -> float:
    """不完全 Beta 函数的连分式展开（Numerical Recipes 实现）."""
    MAXIT = 200
    EPS = 3.0e-7
    FPMIN = 1.0e-30
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    """正则化不完全 Beta 函数 I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    bt = math.exp(a * math.log(x) + b * math.log(1.0 - x) - lbeta)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def _t_sf_two_tailed(t: float, df: float) -> float:
    """Student t 分布的双尾 p-value.

    p = I_x(df/2, 1/2)，其中 x = df / (df + t^2)。
    df <= 0 时返回 1.0（自由度不足，不拒绝原假设）。
    """
    if df <= 0:
        return 1.0
    if t == 0:
        return 1.0
    x = df / (df + t * t)
    return _betai(df / 2.0, 0.5, x)


def _spearman_from_lists(fvals: list[float], rvals: list[float]) -> float:
    """对两个等长数值列表计算 Spearman 秩相关（含 ties 处理）.

    - 无 ties 时使用经典公式：ic = 1 - 6*Σd² / (n*(n²-1))
    - 存在 ties 时退化为对秩做 Pearson 相关（更准确）
    """
    n = len(fvals)
    franks = _rank_average(fvals)
    rranks = _rank_average(rvals)
    has_ties = len(set(fvals)) < n or len(set(rvals)) < n
    if has_ties:
        return _pearson(franks, rranks)
    d_squared = sum((franks[i] - rranks[i]) ** 2 for i in range(n))
    return 1.0 - (6.0 * d_squared) / (n * (n * n - 1))


# ---------------------------------------------------------------------------
# 因子计算
# ---------------------------------------------------------------------------


def _safe_float(value: Any, default: float = 0.0) -> float:
    """安全转换为 float，None / 空值 / 异常返回 default."""
    if value is None:
        return default
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(f) or math.isinf(f):
        return default
    return f


def calculate_factors(financial_data: list[dict[str, Any]]) -> list[FactorResult]:
    """从财务数据列表中计算所有因子.

    修复历史问题：移除原先只计算动量但从未存储的死代码循环；
    扩充因子类型至动量 / 价值 / 质量 / 成长 / 波动五大类。

    Args:
        financial_data: 财务数据列表，每个元素是一家公司的财务指标字典。
            识别的字段（均为可选，缺失则对应因子跳过）：
            symbol, revenue, prev_revenue, net_profit, prev_net_profit,
            total_assets, prev_total_assets, total_liabilities, owner_equity,
            operating_cost, current_assets, current_liabilities,
            pe_ratio, pb_ratio, ps_ratio, enterprise_value, ebitda,
            price_volatility, earnings_history

    Returns:
        因子结果列表，每个因子包含所有公司的因子值
    """
    # 用 name -> FactorResult 的字典聚合，避免重复因子合并错误
    factors: dict[str, FactorResult] = {}

    def _set(name: str, category: str, symbol: str, value: float, desc: str) -> None:
        if math.isnan(value) or math.isinf(value):
            return
        fr = factors.get(name)
        if fr is None:
            fr = FactorResult(name=name, category=category, values={}, description=desc)
            factors[name] = fr
        fr.values[symbol] = round(value, 6)

    for company in financial_data:
        symbol = company.get("symbol") or company.get("name") or ""
        if not symbol:
            continue

        # ---- 基础财务项 ----
        revenue = _safe_float(company.get("revenue"))
        prev_revenue = _safe_float(company.get("prev_revenue"))
        net_profit = _safe_float(company.get("net_profit"))
        prev_net_profit = _safe_float(company.get("prev_net_profit"))
        total_assets = _safe_float(company.get("total_assets"))
        prev_total_assets = _safe_float(company.get("prev_total_assets"))
        total_liabilities = _safe_float(company.get("total_liabilities"))
        owner_equity = _safe_float(company.get("owner_equity"))
        operating_cost = _safe_float(company.get("operating_cost"))
        current_assets = _safe_float(company.get("current_assets"))
        current_liabilities = _safe_float(company.get("current_liabilities"))

        # ---- 动量因子（基本面动量：同比变化率）----
        if prev_revenue > 0:
            _set("revenue_growth", "momentum", symbol,
                 (revenue - prev_revenue) / prev_revenue, "营收同比增长率")
        if prev_net_profit != 0:
            _set("profit_growth", "momentum", symbol,
                 (net_profit - prev_net_profit) / abs(prev_net_profit), "净利润同比增长率")

        # ---- 价值因子 ----
        pe = _safe_float(company.get("pe_ratio"))
        pb = _safe_float(company.get("pb_ratio"))
        ps = _safe_float(company.get("ps_ratio"))
        ev = _safe_float(company.get("enterprise_value"))
        ebitda = _safe_float(company.get("ebitda"))
        if pe > 0:
            _set("PE", "value", symbol, pe, "市盈率")
        if pb > 0:
            _set("PB", "value", symbol, pb, "市净率")
        if ps > 0:
            _set("PS", "value", symbol, ps, "市销率")
        if ev > 0 and ebitda > 0:
            _set("EV/EBITDA", "value", symbol, ev / ebitda, "企业价值倍数")

        # ---- 质量因子 ----
        if owner_equity > 0:
            _set("ROE", "quality", symbol, net_profit / owner_equity, "净资产收益率")
        if total_assets > 0:
            _set("ROA", "quality", symbol, net_profit / total_assets, "总资产收益率")
        if revenue > 0:
            _set("gross_margin", "quality", symbol,
                 (revenue - operating_cost) / revenue, "毛利率")
            _set("net_margin", "quality", symbol, net_profit / revenue, "净利率")
        if current_liabilities > 0:
            _set("current_ratio", "quality", symbol,
                 current_assets / current_liabilities, "流动比率")

        # ---- 成长因子 ----
        if prev_total_assets > 0:
            _set("asset_growth", "growth", symbol,
                 (total_assets - prev_total_assets) / prev_total_assets, "总资产同比增长")

        # ---- 波动因子 ----
        price_vol = _safe_float(company.get("price_volatility"))
        if price_vol > 0:
            _set("price_volatility", "volatility", symbol, price_vol, "价格波动率")
        earnings_history = company.get("earnings_history")
        if isinstance(earnings_history, (list, tuple)) and len(earnings_history) >= 2:
            eh = [_safe_float(v) for v in earnings_history]
            eh = [v for v in eh if not (math.isnan(v) or math.isinf(v))]
            if len(eh) >= 2:
                mean_e = sum(eh) / len(eh)
                if mean_e != 0:
                    std_e = statistics.pstdev(eh) if len(eh) > 1 else 0.0
                    _set("earnings_volatility", "volatility", symbol,
                         std_e / abs(mean_e), "盈利波动率（变异系数）")

    return list(factors.values())


# ---------------------------------------------------------------------------
# IC 评估
# ---------------------------------------------------------------------------


def evaluate_factor_ic(
    factor_values: dict[str, float],
    forward_returns: dict[str, float],
) -> dict[str, float]:
    """计算因子的 IC (Information Coefficient) 及统计显著性.

    IC = Spearman 秩相关(因子值, 前瞻收益)，含 ties 处理。
    同时返回 t 统计量与双尾 p-value，用于检验 IC 是否显著异于 0。

    Args:
        factor_values: {symbol: factor_value}
        forward_returns: {symbol: forward_return}

    Returns:
        {"ic": float, "ic_rank": float, "ic_pvalue": float, "ic_tstat": float, "n": int}
        - ic_rank: 兼容旧接口，等于 ic
        - n: 有效样本数
        样本不足 (n<3) 或方差为 0 时返回 ic=0, tstat=0, pvalue=1
    """
    common_symbols = sorted(set(factor_values.keys()) & set(forward_returns.keys()))
    n = len(common_symbols)
    if n < 3:
        return {"ic": 0.0, "ic_rank": 0.0, "ic_pvalue": 1.0, "ic_tstat": 0.0, "n": n}

    fvals = [float(factor_values[s]) for s in common_symbols]
    rvals = [float(forward_returns[s]) for s in common_symbols]

    # 全相同值无法排序/相关
    if len(set(fvals)) < 2 or len(set(rvals)) < 2:
        return {"ic": 0.0, "ic_rank": 0.0, "ic_pvalue": 1.0, "ic_tstat": 0.0, "n": n}

    ic = _spearman_from_lists(fvals, rvals)

    # t 统计量：t = ic * sqrt((n-2)/(1-ic^2))，自由度 df = n-2
    denom = 1.0 - ic * ic
    if denom <= 1e-12:
        # |ic| 极接近 1（完全相关），t 趋向无穷，p 趋向 0
        ic_tstat = math.copysign(1e6, ic)
        ic_pvalue = 0.0
    else:
        ic_tstat = ic * math.sqrt((n - 2) / denom)
        ic_pvalue = _t_sf_two_tailed(ic_tstat, n - 2)

    return {
        "ic": round(ic, 6),
        "ic_rank": round(ic, 6),
        "ic_pvalue": ic_pvalue,
        "ic_tstat": ic_tstat,
        "n": n,
    }


def _cross_sectional_win_rate(
    factor_values: dict[str, float],
    forward_returns: dict[str, float],
) -> float:
    """单期 IC 胜率：截面配对中因子方向与收益方向一致的比例.

    对所有股票对 (i, j)，若 sign(f_i - f_j) == sign(r_i - r_j) 记为同向；
    忽略因子或收益相等的配对（ties）。胜率 = 同向配对 / (同向 + 反向配对)。
    """
    common_symbols = sorted(set(factor_values.keys()) & set(forward_returns.keys()))
    n = len(common_symbols)
    if n < 2:
        return 0.0
    fv = [float(factor_values[s]) for s in common_symbols]
    rv = [float(forward_returns[s]) for s in common_symbols]
    concordant = 0
    discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            df = fv[i] - fv[j]
            dr = rv[i] - rv[j]
            if df == 0 or dr == 0:
                continue  # 忽略 ties
            if (df > 0 and dr > 0) or (df < 0 and dr < 0):
                concordant += 1
            else:
                discordant += 1
    total = concordant + discordant
    if total == 0:
        return 0.0
    return concordant / total


def evaluate_factors(
    factors: list[FactorResult],
    forward_returns: dict[str, float],
) -> list[FactorResult]:
    """单期评估因子列表的 IC / 显著性 / 胜率.

    单期场景下无法得到有意义的 IC 时间序列标准差，因此 ic_std 置 0、
    ir 置 0（真实 IR 请使用 evaluate_factors_multiperiod）。
    显著性由 ic_tstat / ic_pvalue 衡量。

    Args:
        factors: 因子结果列表
        forward_returns: {symbol: forward_return}

    Returns:
        按 |IC| 降序排列并赋予 rank 的因子列表
    """
    for factor in factors:
        ic_result = evaluate_factor_ic(factor.values, forward_returns)
        factor.ic = ic_result["ic"]
        factor.ic_mean = ic_result["ic"]
        # 单期无时间序列，IC 标准差无定义 → ir=0（避免虚假 IR）
        factor.ic_std = 0.0
        factor.ir = 0.0
        factor.ic_tstat = ic_result["ic_tstat"]
        factor.ic_pvalue = ic_result["ic_pvalue"]
        factor.n = ic_result["n"]
        factor.ic_win_rate = _cross_sectional_win_rate(factor.values, forward_returns)

    factors.sort(key=lambda f: abs(f.ic), reverse=True)
    for i, f in enumerate(factors):
        f.rank = i + 1
    return factors


# ---------------------------------------------------------------------------
# 多期评估（真实 IR）
# ---------------------------------------------------------------------------


def evaluate_factors_multiperiod(
    factors: list[FactorResult],
    period_returns: list[dict[str, float]],
) -> list[FactorResult]:
    """多期因子评估，计算真实的 IR (Information Ratio).

    对每个因子，在每个截面周期上计算 IC，得到 IC 时间序列：
    - ic_mean = IC 序列均值
    - ic_std = IC 序列标准差（真实标准差，非伪造）
    - ir = ic_mean / ic_std
    - ic_win_rate = IC > 0 的周期占比
    - ic_tstat = ic_mean / (ic_std / sqrt(n_periods))，IC 均值的 t 统计量
    - ic_pvalue = 对应双尾 p-value

    Args:
        factors: 因子结果列表（values 为截面因子值，跨周期固定）
        period_returns: 每个元素是一个周期的 {symbol: return}

    Returns:
        按 |ic_mean| 降序排列并赋予 rank 的因子列表
    """
    n_periods = len(period_returns)

    for factor in factors:
        if n_periods == 0:
            factor.ic = 0.0
            factor.ic_mean = 0.0
            factor.ic_std = 0.0
            factor.ir = 0.0
            factor.ic_win_rate = 0.0
            factor.ic_tstat = 0.0
            factor.ic_pvalue = 1.0
            factor.n = 0
            continue

        ic_series: list[float] = []
        for period in period_returns:
            ic_series.append(evaluate_factor_ic(factor.values, period)["ic"])

        ic_mean = statistics.fmean(ic_series)
        ic_std = statistics.stdev(ic_series) if n_periods > 1 else 0.0
        ir = ic_mean / ic_std if ic_std > 0 else 0.0
        win_rate = sum(1 for x in ic_series if x > 0) / n_periods

        if ic_std > 0 and n_periods > 1:
            ic_tstat = ic_mean / (ic_std / math.sqrt(n_periods))
            ic_pvalue = _t_sf_two_tailed(ic_tstat, n_periods - 1)
        else:
            ic_tstat = 0.0
            ic_pvalue = 1.0

        factor.ic = ic_mean
        factor.ic_mean = ic_mean
        factor.ic_std = ic_std
        factor.ir = ir
        factor.ic_win_rate = win_rate
        factor.ic_tstat = ic_tstat
        factor.ic_pvalue = ic_pvalue
        factor.n = n_periods

    factors.sort(key=lambda f: abs(f.ic_mean), reverse=True)
    for i, f in enumerate(factors):
        f.rank = i + 1
    return factors


# ---------------------------------------------------------------------------
# 因子中性化
# ---------------------------------------------------------------------------


def neutralize_factor(
    factor_values: dict[str, float],
    neutralization_data: dict[str, dict],
    method: str = "industry",
) -> dict[str, float]:
    """对因子值进行中性化处理，剔除行业 / 市值敞口。

    Args:
        factor_values: {symbol: factor_value}
        neutralization_data: {symbol: {"industry": str, "market_cap": float}}
        method: 中性化方式
            - "industry": 行业中性（各组减去行业均值）
            - "market_cap": 市值中性（对 log(market_cap) 回归取残差）
            - "both": 先行业中性，再对残差做市值中性

    Returns:
        中性化后的因子值 {symbol: value}。
        未提供中性化数据的 symbol 保留原值。
    """
    result: dict[str, float] = dict(factor_values)
    method = (method or "industry").lower()

    # ---- 行业中性 ----
    if method in ("industry", "both"):
        groups: dict[str, list[str]] = {}
        for sym in factor_values:
            info = neutralization_data.get(sym)
            if not isinstance(info, dict):
                continue
            industry = info.get("industry")
            if not industry:
                continue
            groups.setdefault(str(industry), []).append(sym)
        for industry, syms in groups.items():
            vals = [float(factor_values[s]) for s in syms]
            mean = sum(vals) / len(vals)
            for s in syms:
                result[s] = float(factor_values[s]) - mean

    # ---- 市值中性 ----
    if method in ("market_cap", "both"):
        candidates = [
            s for s in result
            if s in neutralization_data
            and isinstance(neutralization_data[s], dict)
            and _safe_float(neutralization_data[s].get("market_cap")) > 0
        ]
        if len(candidates) >= 2:
            xs = [math.log(_safe_float(neutralization_data[s].get("market_cap"))) for s in candidates]
            ys = [result[s] for s in candidates]
            mx = sum(xs) / len(xs)
            my = sum(ys) / len(ys)
            sxx = sum((x - mx) ** 2 for x in xs)
            sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(len(xs)))
            slope = sxy / sxx if sxx > 0 else 0.0
            intercept = my - slope * mx
            for s in candidates:
                mcap = _safe_float(neutralization_data[s].get("market_cap"))
                result[s] = result[s] - (intercept + slope * math.log(mcap))

    return result


# ---------------------------------------------------------------------------
# 因子衰减分析
# ---------------------------------------------------------------------------


def analyze_factor_decay(
    factor_values: dict[str, float],
    period_returns: list[dict[str, float]],
    max_lag: int = 12,
) -> dict[str, Any]:
    """分析因子预测能力的衰减（half-life）.

    将因子值（截面固定）与未来第 lag 期的收益计算 IC，观察 IC 随 lag 的变化。

    Args:
        factor_values: {symbol: factor_value}（基期截面）
        period_returns: 每个元素为一个未来周期的 {symbol: return}
        max_lag: 最大考察期数

    Returns:
        {
            "lag_results": [{"lag", "ic", "tstat", "pvalue", "n"}, ...],
            "half_life": int,
            "decay_summary": str,
        }
        half_life: |IC| 衰减至峰值一半时的期数；若始终未跌破则取最后一期。
    """
    n_periods = len(period_returns)
    lag_results: list[dict[str, Any]] = []
    for lag in range(1, max_lag + 1):
        if lag - 1 >= n_periods:
            break
        ret = period_returns[lag - 1]
        res = evaluate_factor_ic(factor_values, ret)
        lag_results.append({
            "lag": lag,
            "ic": res["ic"],
            "tstat": res["ic_tstat"],
            "pvalue": res["ic_pvalue"],
            "n": res["n"],
        })

    # 半衰期：|IC| 跌破峰值绝对值一半的首个 lag
    half_life = 0
    if lag_results:
        peak_abs = max(abs(r["ic"]) for r in lag_results)
        if peak_abs > 0:
            half_threshold = 0.5 * peak_abs
            peak_idx = max(range(len(lag_results)), key=lambda i: abs(lag_results[i]["ic"]))
            half_life = lag_results[-1]["lag"]  # 默认：从未衰减到一半
            for i in range(peak_idx, len(lag_results)):
                if abs(lag_results[i]["ic"]) <= half_threshold:
                    half_life = lag_results[i]["lag"]
                    break

    # 衰减描述
    if not lag_results:
        decay_summary = "无可用周期数据，无法分析衰减。"
    else:
        peak_ic = max(lag_results, key=lambda r: abs(r["ic"]))["ic"]
        final_ic = lag_results[-1]["ic"]
        if half_life <= 2:
            speed = "极快"
        elif half_life <= 4:
            speed = "较快"
        elif half_life <= 8:
            speed = "中等"
        else:
            speed = "较慢"
        decay_summary = (
            f"因子预测能力衰减{speed}：峰值 IC={peak_ic:.4f}，"
            f"半衰期约 {half_life} 期，期末(lag={lag_results[-1]['lag']}) IC={final_ic:.4f}。"
        )

    return {
        "lag_results": lag_results,
        "half_life": half_life,
        "decay_summary": decay_summary,
    }


# ---------------------------------------------------------------------------
# 因子相关性 / 聚类
# ---------------------------------------------------------------------------


def analyze_factor_correlation(factors: list[FactorResult]) -> dict[str, Any]:
    """计算因子间两两相关性并做简单聚类。

    Args:
        factors: 因子结果列表

    Returns:
        {
            "correlation_matrix": {factor_name: {factor_name: corr}},
            "correlated_pairs": [{"factor1", "factor2", "correlation"}],
            "clusters": [[factor_name, ...], ...],
        }
        高相关阈值默认 |corr| > 0.7。
    """
    threshold = 0.7
    names = [f.name for f in factors]

    # 相关性矩阵（对共同 symbol 取 Pearson）
    corr: dict[str, dict[str, float]] = {name: {name: 1.0} for name in names}
    for i, fi in enumerate(factors):
        for j in range(i, len(factors)):
            fj = factors[j]
            common = set(fi.values.keys()) & set(fj.values.keys())
            if len(common) < 3:
                c = 0.0
            else:
                syms = sorted(common)
                xs = [float(fi.values[s]) for s in syms]
                ys = [float(fj.values[s]) for s in syms]
                if len(set(xs)) < 2 or len(set(ys)) < 2:
                    c = 0.0
                else:
                    c = round(_pearson(xs, ys), 4)
            corr[fi.name][fj.name] = c
            corr[fj.name][fi.name] = c

    # 高相关对
    correlated_pairs: list[dict[str, Any]] = []
    for i in range(len(factors)):
        for j in range(i + 1, len(factors)):
            c = corr[factors[i].name][factors[j].name]
            if abs(c) > threshold:
                correlated_pairs.append({
                    "factor1": factors[i].name,
                    "factor2": factors[j].name,
                    "correlation": c,
                })

    # 并查集聚类
    parent = {name: name for name in names}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(len(factors)):
        for j in range(i + 1, len(factors)):
            if abs(corr[factors[i].name][factors[j].name]) > threshold:
                union(factors[i].name, factors[j].name)

    groups: dict[str, list[str]] = {}
    for name in names:
        groups.setdefault(find(name), []).append(name)
    clusters = list(groups.values())

    return {
        "correlation_matrix": corr,
        "correlated_pairs": correlated_pairs,
        "clusters": clusters,
    }


# ---------------------------------------------------------------------------
# 深度因子挖掘流水线
# ---------------------------------------------------------------------------


def mine_factors_deep(
    financial_data: list[dict[str, Any]],
    forward_returns: dict[str, float] | None = None,
    period_returns: list[dict[str, float]] | None = None,
    neutralization_data: dict[str, dict] | None = None,
    max_decay_lag: int = 12,
) -> dict[str, Any]:
    """完整深度因子挖掘流水线.

    依次执行：
    1. 计算全部因子
    2. 若提供 neutralization_data：中性化（含市值则 both，否则 industry）
    3. 若提供 period_returns：多期评估（真实 IR）
    4. 若提供 forward_returns：单期评估
    5. 若提供 period_returns：逐因子衰减分析
    6. 因子相关性 / 聚类分析
    7. 汇总报告

    Args:
        financial_data: 公司财务数据列表
        forward_returns: 单期前瞻收益 {symbol: return}（可选）
        period_returns: 多期收益序列，每个元素为 {symbol: return}（可选）
        neutralization_data: 中性化数据 {symbol: {"industry", "market_cap"}}（可选）
        max_decay_lag: 衰减分析最大期数

    Returns:
        综合报告字典，包含 factors / multiperiod_evaluation /
        single_period_evaluation / neutralization_applied /
        decay_analysis / correlation_analysis / summary。
    """
    # 1. 计算因子
    factors = calculate_factors(financial_data)

    # 2. 中性化
    neutralization_applied = False
    neutralization_method = None
    if neutralization_data:
        has_mcap = any(
            isinstance(v, dict) and _safe_float(v.get("market_cap")) > 0
            for v in neutralization_data.values()
        )
        neutralization_method = "both" if has_mcap else "industry"
        for f in factors:
            f.values = neutralize_factor(f.values, neutralization_data, method=neutralization_method)
        neutralization_applied = True

    # 3. 多期评估（真实 IR）
    multiperiod_evaluation: list[dict[str, Any]] | None = None
    if period_returns:
        factors = evaluate_factors_multiperiod(factors, period_returns)
        multiperiod_evaluation = [asdict(f) for f in factors]

    # 4. 单期评估
    single_period_evaluation: list[dict[str, Any]] | None = None
    if forward_returns:
        factors = evaluate_factors(factors, forward_returns)
        single_period_evaluation = [asdict(f) for f in factors]

    # 5. 衰减分析
    decay_analysis: dict[str, Any] | None = None
    if period_returns:
        decay_analysis = {}
        for f in factors:
            decay_analysis[f.name] = analyze_factor_decay(
                f.values, period_returns, max_lag=max_decay_lag
            )

    # 6. 相关性分析
    correlation_analysis = analyze_factor_correlation(factors)

    # 7. 汇总
    summary_parts = [f"共计算 {len(factors)} 个因子"]
    if neutralization_applied:
        summary_parts.append(f"已应用中性化({neutralization_method})")
    if multiperiod_evaluation is not None:
        sig_multi = [
            f for f in factors
            if abs(f.ic_mean) > 0.03 and f.ic_pvalue < 0.05
        ]
        summary_parts.append(
            f"多期评估: {len(sig_multi)} 个因子显著(|IC均值|>0.03 且 p<0.05)"
        )
        if factors:
            best_ir = max(factors, key=lambda f: abs(f.ir))
            summary_parts.append(
                f"最强 IR 因子: {best_ir.name}(IR={best_ir.ir:.4f})"
            )
    if single_period_evaluation is not None:
        sig_single = [
            f for f in factors
            if abs(f.ic) > 0.03 and f.ic_pvalue < 0.05
        ]
        summary_parts.append(
            f"单期评估: {len(sig_single)} 个因子显著(|IC|>0.03 且 p<0.05)"
        )
        if factors:
            best_ic = max(factors, key=lambda f: abs(f.ic))
            summary_parts.append(
                f"最强 IC 因子: {best_ic.name}(IC={best_ic.ic:.4f})"
            )
    if correlation_analysis["correlated_pairs"]:
        summary_parts.append(
            f"高相关因子对(|r|>0.7): {len(correlation_analysis['correlated_pairs'])} 对, "
            f"聚类数: {len(correlation_analysis['clusters'])}"
        )

    return {
        "factors": [asdict(f) for f in factors],
        "multiperiod_evaluation": multiperiod_evaluation,
        "single_period_evaluation": single_period_evaluation,
        "neutralization_applied": neutralization_applied,
        "neutralization_method": neutralization_method,
        "decay_analysis": decay_analysis,
        "correlation_analysis": correlation_analysis,
        "summary": "；".join(summary_parts) + "。",
    }


# ---------------------------------------------------------------------------
# 向后兼容：旧版完整流程
# ---------------------------------------------------------------------------


def mine_factors(
    financial_data: list[dict[str, Any]],
    forward_returns: dict[str, float] | None = None,
) -> dict[str, Any]:
    """完整因子挖掘流程（旧版接口，保持向后兼容）.

    Args:
        financial_data: 公司财务数据列表
        forward_returns: 前瞻收益 {symbol: return}，可选

    Returns:
        {"factors": [...], "best_factors": [...], "summary": "..."}
    """
    factors = calculate_factors(financial_data)

    if forward_returns:
        factors = evaluate_factors(factors, forward_returns)
        best_factors = [asdict(f) for f in factors[:5]]
    else:
        for f in factors:
            f.ic = 0.0
            f.ir = 0.0
        best_factors = [asdict(f) for f in factors[:5]]

    summary = f"共计算 {len(factors)} 个因子"
    if forward_returns:
        significant = [f for f in factors if abs(f.ic) > 0.03]
        summary += f"，其中 {len(significant)} 个显著 (|IC|>0.03)"
        if significant:
            best = significant[0]
            summary += f"，最强因子: {best.name} (IC={best.ic:.4f})"

    return {
        "factors": [asdict(f) for f in factors],
        "best_factors": best_factors,
        "summary": summary,
    }
