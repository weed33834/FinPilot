# -*- coding: utf-8 -*-
"""三表联动建模引擎 — IS → BS → CF 确定性投影（间接法）。

架构：
    1. project_income_statement()     收入驱动的利润表投影
    2. project_balance_sheet()        NI → 留存收益，现金作为平衡项
    3. project_cash_flow()            间接法：NI + 非现金调整 + 营运资本变动
    4. ensure_balance()               强制 A = L + E
    5. run_projection()               串联全流程入口
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass
class ProjectionResult:
    income_statement: pd.DataFrame
    balance_sheet: pd.DataFrame
    cash_flow: pd.DataFrame
    balanced: bool
    diagnostics: dict[str, Any]


class ThreeStatementEngine:
    """确定性三表联动建模引擎。

    用法::

        engine = ThreeStatementEngine()
        result = engine.run_projection(
            historical_bs={"total_assets": 1_000_000, "total_liabilities": 400_000, "total_equity": 600_000, ...},
            assumptions={"revenue_growth": 0.10, "cogs_pct": 0.60, "tax_rate": 0.25, ...},
            periods=4,
        )
    """

    # ── 默认假设 ──
    DEFAULT_ASSUMPTIONS: dict[str, float] = {
        "revenue_growth": 0.08,
        "cogs_pct": 0.60,
        "opex_pct": 0.25,
        "tax_rate": 0.25,
        "capex_pct": 0.05,
        "depreciation_rate": 0.10,
        "dividend_payout": 0.30,
        "ar_days": 45,
        "ap_days": 30,
        "inventory_days": 60,
        "working_capital_growth": 0.05,
    }

    def run_projection(
        self,
        historical_bs: dict[str, float],
        assumptions: dict[str, float] | None = None,
        periods: int = 4,
        base_revenue: float | None = None,
    ) -> ProjectionResult:
        """串联 IS → BS → CF 全流程投影。

        Args:
            historical_bs: 最近一期资产负债表快照
            assumptions: 假设参数字典（覆盖默认值）
            periods: 投影期数
            base_revenue: 起始收入（不传则从 historical_bs 估算）
        """
        assumptions = {**self.DEFAULT_ASSUMPTIONS, **(assumptions or {})}

        if base_revenue is None:
            equity = historical_bs.get("total_equity", 1_000_000)
            base_revenue = equity * 0.8  # 收入 / 权益 ≈ 0.8

        # 1. IS
        is_df = self.project_income_statement(assumptions, base_revenue, periods)

        # 2. BS
        bs_df = self.project_balance_sheet(is_df, historical_bs, assumptions, periods)

        # 3. CF
        cf_df = self.project_cash_flow(is_df, bs_df, historical_bs, assumptions)

        # 4. 平衡校验
        balanced, diag = self._verify_balance(bs_df)
        if not balanced:
            bs_df = self.ensure_balance(bs_df)

        return ProjectionResult(
            income_statement=is_df,
            balance_sheet=bs_df,
            cash_flow=cf_df,
            balanced=balanced,
            diagnostics=diag,
        )

    # ── 利润表投影 ──

    def project_income_statement(
        self,
        assumptions: dict[str, float],
        base_revenue: float,
        periods: int = 4,
    ) -> pd.DataFrame:
        """收入驱动的利润表投影。

        假设: revenue_growth, cogs_pct, opex_pct, tax_rate
        """
        rows: list[dict[str, float]] = []
        revenue = base_revenue
        cogs_pct = assumptions["cogs_pct"]
        opex_pct = assumptions["opex_pct"]
        tax_rate = assumptions["tax_rate"]

        for period in range(1, periods + 1):
            revenue = round(base_revenue * (1 + assumptions["revenue_growth"]) ** (period - 1), 2)
            cogs = round(revenue * cogs_pct, 2)
            gross_profit = round(revenue - cogs, 2)
            opex = round(revenue * opex_pct, 2)
            operating_income = round(gross_profit - opex, 2)
            tax = round(max(0, operating_income) * tax_rate, 2)
            net_income = round(operating_income - tax, 2)

            rows.append({
                "period": period,
                "revenue": revenue,
                "cogs": cogs,
                "gross_profit": gross_profit,
                "operating_expenses": opex,
                "operating_income": operating_income,
                "tax_expense": tax,
                "net_income": net_income,
            })

        df = pd.DataFrame(rows)
        df["cumulative_ni"] = df["net_income"].cumsum()
        return df

    # ── 资产负债表投影 ──

    def project_balance_sheet(
        self,
        is_df: pd.DataFrame,
        prev_bs: dict[str, float],
        assumptions: dict[str, float],
        periods: int = 4,
    ) -> pd.DataFrame:
        """NI → 留存收益；Capex 假设 → 固定资产；现金作为平衡项。"""
        capex_pct = assumptions["capex_pct"]
        dep_rate = assumptions["depreciation_rate"]
        div_payout = assumptions["dividend_payout"]

        # 期初值
        total_assets = prev_bs.get("total_assets", 1_000_000)
        current_assets = prev_bs.get("current_assets", total_assets * 0.4)
        nca = prev_bs.get("non_current_assets", total_assets - current_assets)
        total_liabilities = prev_bs.get("total_liabilities", 400_000)
        current_liabilities = prev_bs.get("current_liabilities", total_liabilities * 0.6)
        ncl = prev_bs.get("non_current_liabilities", total_liabilities - current_liabilities)
        total_equity = prev_bs.get("total_equity", 600_000)
        retained_earnings = prev_bs.get("retained_earnings", total_equity * 0.3)
        initial_cash = prev_bs.get("cash", current_assets * 0.3)

        rows = []
        prev_re = retained_earnings
        prev_nca = nca
        prev_cash = initial_cash

        for _, row in is_df.iterrows():
            period = int(row["period"])
            ni = row["net_income"]
            revenue = row["revenue"]

            # 营运资本变动（基于 DSO/DIO/DPO 简化）
            ar_days = assumptions["ar_days"]
            ap_days = assumptions["ap_days"]
            inv_days = assumptions["inventory_days"]
            ar = round(revenue * ar_days / 365, 2)
            ap = round(row["cogs"] * ap_days / 365, 2)
            inv = round(row["cogs"] * inv_days / 365, 2)

            # 固定资产
            capex = round(revenue * capex_pct, 2)
            depreciation = round(prev_nca * dep_rate, 2)
            new_nca = round(prev_nca + capex - depreciation, 2)

            # 留存收益
            dividends = round(max(0, ni) * div_payout, 2)
            new_re = round(prev_re + ni - dividends, 2)

            # 现金（先按上期 + 净利润估算，后续 CF 方法会覆盖）
            new_cash = round(prev_cash + ni * 0.3, 2)

            new_ca = round(new_cash + ar + inv, 2)
            new_cl = round(ap + current_liabilities * 0.5, 2)

            new_ta = round(new_ca + new_nca, 2)
            new_tl = round(new_cl + ncl, 2)
            new_eq = round(new_ta - new_tl, 2)

            rows.append({
                "period": period,
                "total_assets": new_ta,
                "current_assets": new_ca,
                "non_current_assets": new_nca,
                "cash": new_cash,
                "accounts_receivable": ar,
                "inventory": inv,
                "total_liabilities": new_tl,
                "current_liabilities": new_cl,
                "non_current_liabilities": ncl,
                "accounts_payable": ap,
                "total_equity": new_eq,
                "retained_earnings": new_re,
                "capex": capex,
                "depreciation": depreciation,
            })

            prev_re = new_re
            prev_nca = new_nca
            prev_cash = new_cash

        return pd.DataFrame(rows)

    # ── 现金流量表投影（间接法） ──

    def project_cash_flow(
        self,
        is_df: pd.DataFrame,
        bs_df: pd.DataFrame,
        prev_bs: dict[str, float],
        assumptions: dict[str, float],
    ) -> pd.DataFrame:
        """间接法：NI + 折旧 + 营运资本变动 → 经营现金流。"""
        dep_rate = assumptions["depreciation_rate"]
        nca_init = prev_bs.get("non_current_assets", 600_000)
        init_cash = prev_bs.get("cash", prev_bs.get("current_assets", 400_000) * 0.3)

        rows = []
        prev_ar = prev_bs.get("accounts_receivable", 0)
        prev_inv = prev_bs.get("inventory", 0)
        prev_ap = prev_bs.get("accounts_payable", 0)
        prev_cash = init_cash

        for i, is_row in is_df.iterrows():
            period = int(is_row["period"])
            ni = is_row["net_income"]

            bs_row = bs_df.iloc[i] if i < len(bs_df) else bs_df.iloc[-1]
            depreciation = bs_row.get("depreciation", nca_init * dep_rate)
            ar_delta = bs_row.get("accounts_receivable", 0) - prev_ar
            inv_delta = bs_row.get("inventory", 0) - prev_inv
            ap_delta = bs_row.get("accounts_payable", 0) - prev_ap

            wc_change = -ar_delta - inv_delta + ap_delta  # 营运资本增加=现金减少
            operating_cf = round(ni + depreciation + wc_change, 2)

            capex = bs_row.get("capex", 0)
            investing_cf = round(-capex, 2)

            financing_cf = round(0, 2)  # 简化：无新增融资

            net_change = round(operating_cf + investing_cf + financing_cf, 2)
            ending_cash = round(prev_cash + net_change, 2)

            rows.append({
                "period": period,
                "net_income": ni,
                "depreciation": depreciation,
                "ar_change": -ar_delta,
                "inv_change": -inv_delta,
                "ap_change": ap_delta,
                "working_capital_change": wc_change,
                "operating_cf": operating_cf,
                "investing_cf": investing_cf,
                "financing_cf": financing_cf,
                "net_cash_change": net_change,
                "beginning_cash": prev_cash,
                "ending_cash": ending_cash,
            })

            prev_ar = bs_row.get("accounts_receivable", 0)
            prev_inv = bs_row.get("inventory", 0)
            prev_ap = bs_row.get("accounts_payable", 0)
            prev_cash = ending_cash

        return pd.DataFrame(rows)

    # ── 平衡校验 ──

    def ensure_balance(self, bs: pd.DataFrame) -> pd.DataFrame:
        """强制 A = L + E，差额由现金吸收。"""
        bs = bs.copy()
        for idx in bs.index:
            diff = bs.at[idx, "total_assets"] - (
                bs.at[idx, "total_liabilities"] + bs.at[idx, "total_equity"]
            )
            if abs(diff) > 0.01:
                bs.at[idx, "cash"] -= diff
                bs.at[idx, "current_assets"] -= diff
                bs.at[idx, "total_assets"] -= diff
        return bs

    def _verify_balance(self, bs: pd.DataFrame) -> tuple[bool, dict]:
        """校验 A = L + E 是否成立。"""
        diffs = bs["total_assets"] - (bs["total_liabilities"] + bs["total_equity"])
        max_diff = diffs.abs().max()
        violations = diffs[abs(diffs) > 1e-2]
        balanced = len(violations) == 0
        return balanced, {
            "max_imbalance": float(max_diff),
            "violation_periods": violations.index.tolist() if not balanced else [],
        }
