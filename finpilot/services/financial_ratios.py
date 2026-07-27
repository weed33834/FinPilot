# -*- coding: utf-8 -*-
"""财务比率计算引擎 — 4 大类 30+ 比率。

支持两种数据源：
1. JSON dict 传入（compute_from_dict）
2. Pandas DataFrame 批量计算（compute_all）
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from finpilot.shared.financial_utils import safe_div as _safe_div, safe_pct as _safe_pct


@dataclass
class RatioResult:
    name: str
    category: str
    value: Optional[float]
    formula: str
    interpretation: str = ""
    benchmark: Optional[float] = None
    unit: str = ""


# ── 辅助函数 ──────────────────────────────────────────────


def _avg(cur: Optional[float], prior: Optional[float]) -> Optional[float]:
    vals = [v for v in (cur, prior) if v is not None]
    return sum(vals) / len(vals) if vals else None


# ── 引擎 ──────────────────────────────────────────────────


class FinancialRatioEngine:
    """财务比率计算引擎。

    用法::

        engine = FinancialRatioEngine()
        ratios = engine.compute_from_dict({
            "revenue": 1_000_000,
            "cogs": 600_000,
            "net_income": 100_000,
            ...
        })
    """

    def compute_from_dict(self, data: dict) -> list[RatioResult]:
        """从字典数据计算全部比率。"""
        results: list[RatioResult] = []
        results.extend(self._profitability(data))
        results.extend(self._liquidity(data))
        results.extend(self._efficiency(data))
        results.extend(self._growth(data))
        results.extend(self._valuation(data))
        return results

    def compute_all(self, df: pd.DataFrame) -> list[RatioResult]:
        """从 DataFrame 批量计算（取最新行）。"""
        if df.empty:
            return []
        row = df.iloc[-1].to_dict()
        return self.compute_from_dict(row)

    # ── 盈利能力 (7 项) ──

    def _profitability(self, d: dict) -> list[RatioResult]:
        rev = d.get("revenue")
        cogs = d.get("cogs")
        ni = d.get("net_income")
        oi = d.get("operating_income")
        ebitda = d.get("ebitda")
        equity = d.get("total_equity") or d.get("equity")
        ta = d.get("total_assets")
        nopat = d.get("nopat") or (ni * (1 - d.get("tax_rate", 0.25)) if ni is not None else None)
        ic = d.get("invested_capital")

        gross_margin = _safe_pct(rev - cogs if rev is not None and cogs is not None else None, rev)
        op_margin = _safe_pct(oi, rev)
        net_margin = _safe_pct(ni, rev)
        ebitda_margin = _safe_pct(ebitda, rev)
        roe = _safe_pct(ni, equity)
        roa = _safe_pct(ni, ta)
        roic = _safe_pct(nopat, ic)

        return [
            RatioResult("毛利率", "盈利能力", gross_margin, "(Revenue - COGS) / Revenue", "衡量核心业务盈利能力", unit="%"),
            RatioResult("营业利润率", "盈利能力", op_margin, "OperatingIncome / Revenue", "衡量经营效率", unit="%"),
            RatioResult("净利率", "盈利能力", net_margin, "NetIncome / Revenue", "衡量最终盈利能力", unit="%"),
            RatioResult("EBITDA利润率", "盈利能力", ebitda_margin, "EBITDA / Revenue", "剔除折旧摊销的经营表现", unit="%"),
            RatioResult("ROE", "盈利能力", roe, "NetIncome / Equity", "净资产收益率", unit="%"),
            RatioResult("ROA", "盈利能力", roa, "NetIncome / TotalAssets", "总资产收益率", unit="%"),
            RatioResult("ROIC", "盈利能力", roic, "NOPAT / InvestedCapital", "投入资本回报率", unit="%"),
        ]

    # ── 流动性 / 偿债能力 (6 项) ──

    def _liquidity(self, d: dict) -> list[RatioResult]:
        ca = d.get("current_assets")
        cl = d.get("current_liabilities")
        inv = d.get("inventory")
        tl = d.get("total_liabilities")
        te = d.get("total_equity") or d.get("equity")
        ebit = d.get("ebit") or d.get("operating_income")
        ie = d.get("interest_expense")

        current = _safe_div(ca, cl)
        quick = _safe_div(ca - inv if ca is not None and inv is not None else None, cl)
        de = _safe_div(tl, te)
        ic = _safe_div(ebit, ie)
        debt_ratio = _safe_pct(tl, d.get("total_assets"))
        equity_mult = _safe_div(d.get("total_assets"), te)

        return [
            RatioResult("流动比率", "流动性", current, "CurrentAssets / CurrentLiabilities",
                        "短期偿债能力，>1 安全", unit="x"),
            RatioResult("速动比率", "流动性", quick, "(CurrentAssets - Inventory) / CurrentLiabilities",
                        "剔除存货后的短期偿债能力", unit="x"),
            RatioResult("负债权益比", "流动性", de, "TotalLiabilities / TotalEquity",
                        "杠杆水平，<1 健康", unit="x"),
            RatioResult("利息覆盖率", "流动性", ic, "EBIT / InterestExpense",
                        "经营利润覆盖利息支出的倍数", unit="x"),
            RatioResult("资产负债率", "流动性", debt_ratio, "TotalLiabilities / TotalAssets", unit="%"),
            RatioResult("权益乘数", "流动性", equity_mult, "TotalAssets / TotalEquity", unit="x"),
        ]

    # ── 运营效率 (7 项) ──

    def _efficiency(self, d: dict) -> list[RatioResult]:
        rev = d.get("revenue")
        cogs = d.get("cogs")
        inv = d.get("inventory")
        inv_prior = d.get("inventory_prior")
        ar = d.get("accounts_receivable")
        ar_prior = d.get("accounts_receivable_prior")
        ap = d.get("accounts_payable")
        ta = d.get("total_assets")
        ta_prior = d.get("total_assets_prior")

        avg_inv = _avg(inv, inv_prior) or inv
        avg_ar = _avg(ar, ar_prior) or ar
        avg_ta = _avg(ta, ta_prior) or ta

        inv_turn = _safe_div(cogs, avg_inv)
        ar_turn = _safe_div(rev, avg_ar)
        at = _safe_div(rev, avg_ta)
        dso = _safe_div(ar * 365 if ar is not None else None, rev)
        dio = _safe_div(inv * 365 if inv is not None else None, cogs)
        dpo = _safe_div(ap * 365 if ap is not None else None, cogs)
        ccc = dso + dio - dpo if all(v is not None for v in (dso, dio, dpo)) else None

        return [
            RatioResult("存货周转率", "运营效率", inv_turn, "COGS / AvgInventory", "存货变现速度", unit="次"),
            RatioResult("应收周转率", "运营效率", ar_turn, "Revenue / AvgAccountsReceivable", "回款速度", unit="次"),
            RatioResult("资产周转率", "运营效率", at, "Revenue / AvgTotalAssets", "单位资产创收能力", unit="次"),
            RatioResult("DSO", "运营效率", dso, "(AR / Revenue) * 365", "应收账款周转天数", unit="天"),
            RatioResult("DIO", "运营效率", dio, "(Inventory / COGS) * 365", "存货周转天数", unit="天"),
            RatioResult("DPO", "运营效率", dpo, "(AP / COGS) * 365", "应付账款周转天数", unit="天"),
            RatioResult("现金转换周期", "运营效率", ccc, "DSO + DIO - DPO", "资金被占用的天数", unit="天"),
        ]

    # ── 增长率 (2 项) ──

    def _growth(self, d: dict) -> list[RatioResult]:
        rev = d.get("revenue")
        rev_prior = d.get("revenue_prior")
        ni = d.get("net_income")
        ni_prior = d.get("net_income_prior")

        rev_growth = _safe_pct(rev - rev_prior if rev is not None and rev_prior is not None else None, rev_prior)
        ni_growth = _safe_pct(ni - ni_prior if ni is not None and ni_prior is not None else None, ni_prior)

        return [
            RatioResult("营收增长率", "增长率", rev_growth, "(Revenue - Prior) / Prior", unit="%"),
            RatioResult("盈利增长率", "增长率", ni_growth, "(NetIncome - Prior) / Prior", unit="%"),
        ]

    # ── 估值指标 (7 项) ──

    def _valuation(self, d: dict) -> list[RatioResult]:
        rev = d.get("revenue")
        ni = d.get("net_income")
        ocf = d.get("operating_cash_flow")
        capex = d.get("capex")
        equity = d.get("total_equity") or d.get("equity")
        ebitda = d.get("ebitda")
        shares = d.get("shares_outstanding")
        market_cap = d.get("market_cap")
        ev = d.get("enterprise_value")
        dividends = d.get("dividends")

        fcf = ocf - capex if ocf is not None and capex is not None else None
        fcf_yield = _safe_pct(fcf, market_cap)
        eps = _safe_div(ni, shares)
        pe = _safe_div(market_cap or (d.get("stock_price", 0) * shares if shares else None), ni)
        pb = _safe_div(market_cap, equity)
        ev_ebitda = _safe_div(ev, ebitda)
        div_yield = _safe_pct(dividends, market_cap)
        ocf_ratio = _safe_pct(ocf, rev)

        return [
            RatioResult("自由现金流", "估值", fcf, "OperatingCashFlow - CapEx", unit="元"),
            RatioResult("自由现金流收益率", "估值", fcf_yield, "FCF / MarketCap", unit="%"),
            RatioResult("EPS", "估值", eps, "NetIncome / SharesOutstanding", "每股收益", unit="元"),
            RatioResult("PE", "估值", pe, "MarketCap / NetIncome", "市盈率", unit="x"),
            RatioResult("PB", "估值", pb, "MarketCap / Equity", "市净率", unit="x"),
            RatioResult("EV/EBITDA", "估值", ev_ebitda, "EnterpriseValue / EBITDA", "企业价值倍数", unit="x"),
            RatioResult("股息率", "估值", div_yield, "Dividends / MarketCap", unit="%"),
            RatioResult("营业现金流比率", "估值", ocf_ratio, "OperatingCashFlow / Revenue", unit="%"),
        ]


# 便捷函数
engine = FinancialRatioEngine()
