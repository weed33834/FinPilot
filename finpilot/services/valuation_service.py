"""估值模型服务 — DCF / WACC / DDM 确定性计算.

核心理念：
- 财务数字由纯 Python 计算，保证 100% 准确
- 不依赖 LLM，结果可复现可审计
- LLM 可在叙事层解读这些数字，但不参与计算
"""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class DcfResult:
    """DCF 估值结果."""

    enterprise_value: float
    equity_value: float
    value_per_share: float | None
    wacc: float
    terminal_value: float
    npv_fcf: float
    assumptions: dict[str, Any]


@dataclass
class WaccResult:
    """WACC 计算结果."""

    wacc: float
    cost_of_equity: float
    cost_of_debt: float
    after_tax_cost_of_debt: float
    weight_of_equity: float
    weight_of_debt: float


@dataclass
class DdmResult:
    """DDM 估值结果."""

    intrinsic_value: float
    dividend_per_share: float
    growth_rate: float
    discount_rate: float
    assumptions: dict[str, Any]


def calculate_wacc(
    market_cap: float,
    total_debt: float,
    cost_of_equity: float,
    cost_of_debt: float,
    tax_rate: float = 0.25,
) -> WaccResult:
    """计算加权平均资本成本 (WACC).

    公式: WACC = E/V × Re + D/V × Rd × (1 - T)

    Args:
        market_cap: 市值（权益价值）
        total_debt: 总债务
        cost_of_equity: 权益成本 (Re)，如 CAPM 计算结果
        cost_of_debt: 债务成本 (Rd)，如债券到期收益率
        tax_rate: 企业所得税率 (T)，默认 25%

    Returns:
        WaccResult
    """
    total_value = market_cap + total_debt
    if total_value <= 0:
        return WaccResult(
            wacc=cost_of_equity,
            cost_of_equity=cost_of_equity,
            cost_of_debt=cost_of_debt,
            after_tax_cost_of_debt=cost_of_debt * (1 - tax_rate),
            weight_of_equity=1.0,
            weight_of_debt=0.0,
        )

    weight_equity = market_cap / total_value
    weight_debt = total_debt / total_value
    after_tax_debt = cost_of_debt * (1 - tax_rate)
    wacc = weight_equity * cost_of_equity + weight_debt * after_tax_debt

    return WaccResult(
        wacc=round(wacc, 4),
        cost_of_equity=round(cost_of_equity, 4),
        cost_of_debt=round(cost_of_debt, 4),
        after_tax_cost_of_debt=round(after_tax_debt, 4),
        weight_of_equity=round(weight_equity, 4),
        weight_of_debt=round(weight_debt, 4),
    )


def calculate_dcf(
    free_cash_flows: list[float],
    wacc: float,
    terminal_growth_rate: float = 0.03,
    shares_outstanding: float | None = None,
    total_debt: float = 0,
    cash_and_equivalents: float = 0,
    tax_rate: float = 0.25,
    cost_of_equity: float = 0.10,
    cost_of_debt: float = 0.06,
    market_cap: float | None = None,
) -> DcfResult:
    """计算折现现金流 (DCF) 估值.

    步骤：
    1. 计算各期 FCF 的现值
    2. 计算终值 (Terminal Value) 并折现
    3. 企业价值 = PV(FCF) + PV(TV)
    4. 股权价值 = 企业价值 - 净债务

    Args:
        free_cash_flows: 预测期各年自由现金流列表
        wacc: 加权平均资本成本（折现率）
        terminal_growth_rate: 永续增长率，默认 3%
        shares_outstanding: 总股本（用于计算每股价值）
        total_debt: 总债务
        cash_and_equivalents: 现金及等价物
        tax_rate, cost_of_equity, cost_of_debt, market_cap: 用于计算 WACC（如果 market_cap 提供）

    Returns:
        DcfResult
    """
    # 如果提供了 market_cap，自动计算 WACC
    if market_cap is not None and market_cap > 0:
        wacc_result = calculate_wacc(market_cap, total_debt, cost_of_equity, cost_of_debt, tax_rate)
        wacc = wacc_result.wacc

    # 1. 折现各期 FCF
    npv_fcf = sum(
        fcf / ((1 + wacc) ** (i + 1)) for i, fcf in enumerate(free_cash_flows)
    )

    # 2. 计算终值（Gordon 增长模型）
    last_fcf = free_cash_flows[-1] if free_cash_flows else 0
    if wacc > terminal_growth_rate:
        terminal_value = last_fcf * (1 + terminal_growth_rate) / (wacc - terminal_growth_rate)
    else:
        terminal_value = 0

    # 折现终值
    pv_terminal = terminal_value / ((1 + wacc) ** len(free_cash_flows))

    # 3. 企业价值
    enterprise_value = npv_fcf + pv_terminal

    # 4. 股权价值 = 企业价值 - 净债务
    net_debt = total_debt - cash_and_equivalents
    equity_value = enterprise_value - net_debt

    # 5. 每股价值
    value_per_share = None
    if shares_outstanding and shares_outstanding > 0:
        value_per_share = equity_value / shares_outstanding

    return DcfResult(
        enterprise_value=round(enterprise_value, 2),
        equity_value=round(equity_value, 2),
        value_per_share=round(value_per_share, 2) if value_per_share else None,
        wacc=round(wacc, 4),
        terminal_value=round(terminal_value, 2),
        npv_fcf=round(npv_fcf, 2),
        assumptions={
            "terminal_growth_rate": terminal_growth_rate,
            "shares_outstanding": shares_outstanding,
            "net_debt": round(net_debt, 2),
            "forecast_years": len(free_cash_flows),
        },
    )


def calculate_ddm(
    dividend_per_share: float,
    growth_rate: float,
    discount_rate: float,
    high_growth_years: int = 5,
    terminal_growth_rate: float = 0.03,
) -> DdmResult:
    """计算股息折现模型 (DDM) 估值.

    两阶段 DDM：
    1. 高增长阶段：各年股息按 high_growth_rate 增长，折现
    2. 永续阶段：终值按 terminal_growth_rate 增长

    Args:
        dividend_per_share: 当前每股股息
        growth_rate: 高增长期年增长率
        discount_rate: 折现率
        high_growth_years: 高增长期年数
        terminal_growth_rate: 永续增长率

    Returns:
        DdmResult
    """
    if discount_rate <= 0:
        return DdmResult(
            intrinsic_value=0,
            dividend_per_share=dividend_per_share,
            growth_rate=growth_rate,
            discount_rate=discount_rate,
            assumptions={"error": "折现率必须大于 0"},
        )

    # 1. 高增长阶段现值
    pv_high_growth = 0
    current_dividend = dividend_per_share
    for year in range(1, high_growth_years + 1):
        current_dividend *= (1 + growth_rate)
        pv_high_growth += current_dividend / ((1 + discount_rate) ** year)

    # 2. 永续阶段终值
    terminal_dividend = current_dividend * (1 + terminal_growth_rate)
    if discount_rate > terminal_growth_rate:
        terminal_value = terminal_dividend / (discount_rate - terminal_growth_rate)
        pv_terminal = terminal_value / ((1 + discount_rate) ** high_growth_years)
    else:
        pv_terminal = 0

    intrinsic_value = pv_high_growth + pv_terminal

    return DdmResult(
        intrinsic_value=round(intrinsic_value, 2),
        dividend_per_share=round(dividend_per_share, 4),
        growth_rate=round(growth_rate, 4),
        discount_rate=round(discount_rate, 4),
        assumptions={
            "high_growth_years": high_growth_years,
            "terminal_growth_rate": terminal_growth_rate,
            "pv_high_growth": round(pv_high_growth, 2),
            "pv_terminal": round(pv_terminal, 2),
        },
    )


def valuation_to_dict(result: DcfResult | WaccResult | DdmResult) -> dict[str, Any]:
    """将估值结果转为字典."""
    return asdict(result)


# ---------------------------------------------------------------------------
# 进阶估值分析：敏感性 / 情景 / 可比公司 / 蒙特卡洛
# ---------------------------------------------------------------------------


def _dcf_value_from_params(params: dict[str, Any]) -> float:
    """从参数字典计算 DCF 股权价值（纯 Python，确定性计算）.

    支持两种 FCF 来源：
    1. ``fcf_list`` / ``free_cash_flows``：直接给出各年自由现金流
    2. ``revenue`` + ``revenue_growth`` + ``operating_margin``：从营收推算 FCF

    Args:
        params: 参数字典，常用键：
            - fcf_list / free_cash_flows: list[float]
            - revenue: 基期营收
            - revenue_growth / growth_rate: 营收年增长率
            - operating_margin / fcf_margin: FCF / 营收 利润率
            - forecast_years: 预测年数（默认 5）
            - wacc: 折现率
            - terminal_growth / terminal_growth_rate: 永续增长率
            - total_debt, cash_and_equivalents / cash: 用于净债务调整

    Returns:
        股权价值（float）
    """
    fcf_list: list[float] = list(params.get("fcf_list") or params.get("free_cash_flows") or [])

    if not fcf_list:
        revenue = float(params.get("revenue", 0) or 0)
        growth = float(params.get("revenue_growth", params.get("growth_rate", 0.0)) or 0.0)
        margin = float(params.get("operating_margin", params.get("fcf_margin", 0.1)) or 0.0)
        years = int(params.get("forecast_years", 5) or 5)
        current = revenue
        for _ in range(max(years, 1)):
            current *= (1 + growth)
            fcf_list.append(current * margin)

    if not fcf_list:
        return 0.0

    wacc = float(params.get("wacc", 0.10) or 0.10)
    terminal_growth = float(
        params.get("terminal_growth", params.get("terminal_growth_rate", 0.03)) or 0.03
    )
    total_debt = float(params.get("total_debt", 0) or 0)
    cash = float(params.get("cash_and_equivalents", params.get("cash", 0)) or 0)

    result = calculate_dcf(
        free_cash_flows=fcf_list,
        wacc=wacc,
        terminal_growth_rate=terminal_growth,
        total_debt=total_debt,
        cash_and_equivalents=cash,
    )
    return result.equity_value


def _median(values: list[float]) -> float | None:
    """计算中位数（纯 Python）."""
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2


def _mean(values: list[float]) -> float | None:
    """计算平均值（纯 Python）."""
    if not values:
        return None
    return sum(values) / len(values)


def _std_dev(values: list[float]) -> float | None:
    """计算总体标准差（纯 Python）."""
    if not values:
        return None
    m = sum(values) / len(values)
    var = sum((v - m) ** 2 for v in values) / len(values)
    return math.sqrt(var)


def _percentile(sorted_values: list[float], pct: float) -> float | None:
    """计算百分位数（线性插值，纯 Python）.

    Args:
        sorted_values: 已排序的数值列表
        pct: 百分位（0-100）
    """
    if not sorted_values:
        return None
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    rank = (pct / 100) * (n - 1)
    lower = int(math.floor(rank))
    upper = int(math.ceil(rank))
    if lower == upper:
        return sorted_values[lower]
    frac = rank - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * frac


def sensitivity_analysis(base_params: dict[str, Any], param_ranges: dict[str, list]) -> dict[str, Any]:
    """敏感性分析 — 逐参数变动 DCF 估值，生成龙卷风图数据.

    采用一次一因子法（OAT）：每次只变动一个参数，其余保持基准值，
    观察估值结果的变化幅度。龙卷风图按各参数影响幅度（max-min）降序排列。

    Args:
        base_params: 基准参数，如 ``{"wacc": 0.10, "terminal_growth": 0.03, "fcf_list": [100, 110, 120]}``
        param_ranges: 各参数的取值范围，如
            ``{"wacc": [0.08, 0.09, 0.10, 0.11, 0.12], "terminal_growth": [0.01, 0.02, 0.03, 0.04, 0.05]}``

    Returns:
        ``{base_value, sensitivity_table, tornado_chart_data}``
    """
    base_value = _dcf_value_from_params(base_params)

    sensitivity_table: dict[str, list[dict[str, Any]]] = {}
    tornado_chart_data: list[dict[str, Any]] = []

    for param_name, values in (param_ranges or {}).items():
        entries: list[dict[str, Any]] = []
        results: list[float] = []
        for v in values:
            params = dict(base_params)
            params[param_name] = v
            try:
                val = _dcf_value_from_params(params)
            except Exception:  # noqa: BLE001
                val = 0.0
            change_pct = (val - base_value) / base_value * 100 if base_value else 0.0
            entries.append(
                {"value": v, "result": round(val, 2), "result_change_pct": round(change_pct, 2)}
            )
            results.append(val)
        sensitivity_table[param_name] = entries

        if results:
            low = min(results)
            high = max(results)
            impact = high - low
            low_change = (low - base_value) / base_value * 100 if base_value else 0.0
            high_change = (high - base_value) / base_value * 100 if base_value else 0.0
            tornado_chart_data.append(
                {
                    "param": param_name,
                    "low": round(low, 2),
                    "high": round(high, 2),
                    "impact": round(impact, 2),
                    "low_change_pct": round(low_change, 2),
                    "high_change_pct": round(high_change, 2),
                }
            )

    tornado_chart_data.sort(key=lambda x: x["impact"], reverse=True)

    return {
        "base_value": round(base_value, 2),
        "sensitivity_table": sensitivity_table,
        "tornado_chart_data": tornado_chart_data,
    }


def scenario_analysis(base_params: dict[str, Any], scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    """情景分析 — 在多套假设下分别计算 DCF 估值.

    Args:
        base_params: 基准参数（用于计算 base_case）
        scenarios: 情景列表，每项形如
            ``{"name": "乐观", "params": {"wacc": 0.08, "terminal_growth": 0.05}, "probability": 0.3}``
            未提供 ``probability`` 时按等权重分配。

    Returns:
        ``{base_case, scenarios, probability_weighted_value}``
    """
    base_value = _dcf_value_from_params(base_params)

    n = len(scenarios) if scenarios else 0
    scenario_results: list[dict[str, Any]] = []
    for sc in (scenarios or []):
        params = dict(base_params)
        params.update(sc.get("params", {}))
        try:
            val = _dcf_value_from_params(params)
        except Exception:  # noqa: BLE001
            val = 0.0
        change_pct = (val - base_value) / base_value * 100 if base_value else 0.0
        probability = float(sc.get("probability", (1.0 / n) if n else 0.0) or 0.0)
        scenario_results.append(
            {
                "name": sc.get("name", "未命名情景"),
                "value": round(val, 2),
                "change_pct": round(change_pct, 2),
                "assumptions": sc.get("params", {}),
                "probability": round(probability, 4),
            }
        )

    probability_weighted = sum(r["value"] * r["probability"] for r in scenario_results)

    return {
        "base_case": {"value": round(base_value, 2), "assumptions": base_params},
        "scenarios": scenario_results,
        "probability_weighted_value": round(probability_weighted, 2),
    }


def comparable_company_analysis(target_metrics: dict[str, Any], peers: list[dict[str, Any]]) -> dict[str, Any]:
    """可比公司分析 — 基于同业乘数推算目标公司估值区间.

    计算的同业乘数：PE、PB、PS、EV/EBITDA（EBITDA 缺失时跳过）。
    使用中位数乘数应用于目标公司相应指标，得到隐含估值；
    估值区间取各乘数隐含估值的最低/最高/平均。

    Args:
        target_metrics: 目标公司指标，如
            ``{"revenue": 1000, "net_profit": 200, "total_assets": 5000, "market_cap": 3000}``
        peers: 可比公司列表，每项含 name/revenue/net_profit/total_assets/market_cap，
            可选 ebitda/total_debt/cash。

    Returns:
        ``{peer_multiples, target_implied_values, valuation_range}``
    """

    def _safe_div(a: float | None, b: float | None) -> float | None:
        if a is None or b is None or b == 0:
            return None
        return a / b

    peer_multiples: list[dict[str, Any]] = []
    pe_list: list[float] = []
    pb_list: list[float] = []
    ps_list: list[float] = []
    ev_ebitda_list: list[float] = []

    for peer in (peers or []):
        revenue = float(peer.get("revenue", 0) or 0)
        net_profit = float(peer.get("net_profit", 0) or 0)
        total_assets = float(peer.get("total_assets", peer.get("book_value", 0)) or 0)
        market_cap = float(peer.get("market_cap", 0) or 0)
        ebitda = peer.get("ebitda")
        total_debt = float(peer.get("total_debt", 0) or 0)
        cash = float(peer.get("cash", 0) or 0)

        pe = _safe_div(market_cap, net_profit)
        pb = _safe_div(market_cap, total_assets)
        ps = _safe_div(market_cap, revenue)
        ev_ebitda = None
        if ebitda is not None and float(ebitda) != 0:
            ev = market_cap + total_debt - cash
            ev_ebitda = ev / float(ebitda)

        peer_multiples.append(
            {
                "name": peer.get("name", "Peer"),
                "pe": round(pe, 2) if pe is not None else None,
                "pb": round(pb, 2) if pb is not None else None,
                "ps": round(ps, 2) if ps is not None else None,
                "ev_ebitda": round(ev_ebitda, 2) if ev_ebitda is not None else None,
            }
        )
        if pe is not None:
            pe_list.append(pe)
        if pb is not None:
            pb_list.append(pb)
        if ps is not None:
            ps_list.append(ps)
        if ev_ebitda is not None:
            ev_ebitda_list.append(ev_ebitda)

    med_pe = _median(pe_list)
    med_pb = _median(pb_list)
    med_ps = _median(ps_list)
    med_ev_ebitda = _median(ev_ebitda_list)

    avg_pe = _mean(pe_list)
    avg_pb = _mean(pb_list)
    avg_ps = _mean(ps_list)

    target_revenue = float(target_metrics.get("revenue", 0) or 0)
    target_net_profit = float(target_metrics.get("net_profit", 0) or 0)
    target_total_assets = float(target_metrics.get("total_assets", 0) or 0)
    target_ebitda = target_metrics.get("ebitda")
    target_total_debt = float(target_metrics.get("total_debt", 0) or 0)
    target_cash = float(target_metrics.get("cash", 0) or 0)

    pe_based = _safe_div(med_pe, 1) * target_net_profit if med_pe is not None else None
    pb_based = _safe_div(med_pb, 1) * target_total_assets if med_pb is not None else None
    ps_based = _safe_div(med_ps, 1) * target_revenue if med_ps is not None else None
    ev_ebitda_based = None
    if med_ev_ebitda is not None and target_ebitda is not None:
        ev = med_ev_ebitda * float(target_ebitda)
        ev_ebitda_based = ev - target_total_debt + target_cash

    implied = {
        "pe_based": round(pe_based, 2) if pe_based is not None else None,
        "pb_based": round(pb_based, 2) if pb_based is not None else None,
        "ps_based": round(ps_based, 2) if ps_based is not None else None,
        "ev_ebitda_based": round(ev_ebitda_based, 2) if ev_ebitda_based is not None else None,
    }

    valid_implied = [v for v in implied.values() if v is not None]
    if valid_implied:
        low = min(valid_implied)
        high = max(valid_implied)
        mid = sum(valid_implied) / len(valid_implied)
    else:
        low = high = mid = 0.0

    return {
        "peer_multiples": peer_multiples,
        "median_multiples": {
            "pe": round(med_pe, 2) if med_pe is not None else None,
            "pb": round(med_pb, 2) if med_pb is not None else None,
            "ps": round(med_ps, 2) if med_ps is not None else None,
            "ev_ebitda": round(med_ev_ebitda, 2) if med_ev_ebitda is not None else None,
        },
        "average_multiples": {
            "pe": round(avg_pe, 2) if avg_pe is not None else None,
            "pb": round(avg_pb, 2) if avg_pb is not None else None,
            "ps": round(avg_ps, 2) if avg_ps is not None else None,
        },
        "target_implied_values": implied,
        "valuation_range": {
            "low": round(low, 2),
            "mid": round(mid, 2),
            "high": round(high, 2),
        },
    }


def monte_carlo_valuation(base_params: dict[str, Any], n_simulations: int = 10000) -> dict[str, Any]:
    """蒙特卡洛估值 — 随机扰动关键参数，模拟 DCF 估值分布.

    使用正态分布随机扰动营收增长率、WACC、运营利润率，对每次模拟重新计算 DCF，
    汇总估值分布的均值、中位数、标准差及分位数。纯 Python 实现，不依赖 numpy/scipy。

    Args:
        base_params: 基准参数，额外支持以下分布参数：
            - revenue_growth / revenue_growth_std（默认 std=0.03）
            - wacc / wacc_std（默认 std=0.01）
            - operating_margin / operating_margin_std（默认 std=0.02）
            - seed: 随机种子（默认 42，保证可复现）
        n_simulations: 模拟次数，默认 10000

    Returns:
        ``{mean_value, median_value, std_dev, percentile_5, percentile_25,
        percentile_75, percentile_95, histogram, n_simulations}``
    """
    seed = base_params.get("seed", 42)
    rng = random.Random(seed)

    growth_mean = float(base_params.get("revenue_growth", base_params.get("growth_rate", 0.05)) or 0.05)
    growth_std = float(base_params.get("revenue_growth_std", 0.03) or 0.03)
    wacc_mean = float(base_params.get("wacc", 0.10) or 0.10)
    wacc_std = float(base_params.get("wacc_std", 0.01) or 0.01)
    margin_mean = float(
        base_params.get("operating_margin", base_params.get("fcf_margin", 0.10)) or 0.10
    )
    margin_std = float(base_params.get("operating_margin_std", 0.02) or 0.02)

    n = max(int(n_simulations), 1)
    values: list[float] = []

    for _ in range(n):
        params = dict(base_params)
        params["revenue_growth"] = rng.gauss(growth_mean, growth_std)
        params["operating_margin"] = rng.gauss(margin_mean, margin_std)
        w = rng.gauss(wacc_mean, wacc_std)
        params["wacc"] = max(w, 0.005)  # 折现率下限保护
        try:
            val = _dcf_value_from_params(params)
            if val == val and abs(val) != float("inf"):  # 排除 NaN/Inf
                values.append(val)
        except Exception:  # noqa: BLE001
            continue

    if not values:
        return {
            "mean_value": 0.0,
            "median_value": 0.0,
            "std_dev": 0.0,
            "percentile_5": 0.0,
            "percentile_25": 0.0,
            "percentile_75": 0.0,
            "percentile_95": 0.0,
            "histogram": [],
            "n_simulations": n,
            "n_valid": 0,
        }

    sorted_values = sorted(values)
    mean_value = sum(values) / len(values)
    median_value = _percentile(sorted_values, 50)
    std = _std_dev(values)

    # 直方图：Sturges 规则确定桶数
    n_valid = len(values)
    n_bins = max(int(math.log2(n_valid) + 1), 5) if n_valid > 1 else 1
    vmin = sorted_values[0]
    vmax = sorted_values[-1]
    span = (vmax - vmin) or 1.0
    bin_width = span / n_bins

    buckets: list[int] = [0] * n_bins
    for v in values:
        idx = int((v - vmin) / bin_width)
        if idx >= n_bins:
            idx = n_bins - 1
        buckets[idx] += 1

    histogram = [
        {
            "bucket": round(vmin + i * bin_width, 2),
            "bucket_end": round(vmin + (i + 1) * bin_width, 2),
            "count": buckets[i],
        }
        for i in range(n_bins)
    ]

    return {
        "mean_value": round(mean_value, 2),
        "median_value": round(median_value, 2) if median_value is not None else 0.0,
        "std_dev": round(std, 2) if std is not None else 0.0,
        "percentile_5": round(_percentile(sorted_values, 5) or 0.0, 2),
        "percentile_25": round(_percentile(sorted_values, 25) or 0.0, 2),
        "percentile_75": round(_percentile(sorted_values, 75) or 0.0, 2),
        "percentile_95": round(_percentile(sorted_values, 95) or 0.0, 2),
        "histogram": histogram,
        "n_simulations": n,
        "n_valid": n_valid,
    }
