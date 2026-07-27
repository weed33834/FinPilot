# -*- coding: utf-8 -*-
"""三表审计关系 — 资产负债表/利润表/现金流量表勾稽验证 + 试算平衡。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select, func

from finpilot.database.models import BalanceSheet, IncomeStatement, CashFlowStatement, JournalEntry


async def reconcile_net_income(session, tenant_id: str, period_end: datetime) -> dict[str, Any]:
    """资产负债表留存收益变动 = 利润表净利润 → 现金流量表经营利润调整一致性。"""
    bs = session.execute(
        select(BalanceSheet).where(
            BalanceSheet.tenant_id == tenant_id,
            BalanceSheet.period_end <= period_end,
        ).order_by(BalanceSheet.period_end.desc()).limit(1)
    ).scalar_one_or_none()

    prev_bs = session.execute(
        select(BalanceSheet).where(
            BalanceSheet.tenant_id == tenant_id,
            BalanceSheet.period_end < period_end,
        ).order_by(BalanceSheet.period_end.desc()).limit(1)
    ).scalar_one_or_none()

    ist = session.execute(
        select(IncomeStatement).where(
            IncomeStatement.tenant_id == tenant_id,
            IncomeStatement.period_end <= period_end,
        ).order_by(IncomeStatement.period_end.desc()).limit(1)
    ).scalar_one_or_none()

    cfs = session.execute(
        select(CashFlowStatement).where(
            CashFlowStatement.tenant_id == tenant_id,
            CashFlowStatement.period_end <= period_end,
        ).order_by(CashFlowStatement.period_end.desc()).limit(1)
    ).scalar_one_or_none()

    bs_re = bs.retained_earnings if bs else 0.0
    prev_re = prev_bs.retained_earnings if prev_bs else 0.0
    re_change = bs_re - prev_re
    net_income = ist.net_income if ist else 0.0
    diff = abs(re_change - net_income)

    return {
        "check": "net_income_reconciliation",
        "balanced": diff < 0.01,
        "bs_retained_earnings": bs_re,
        "prev_retained_earnings": prev_re,
        "retained_earnings_change": re_change,
        "is_net_income": net_income,
        "cf_operating": cfs.operating_activities if cfs else 0.0,
        "difference": round(diff, 2),
        "period_end": period_end.isoformat() if period_end else None,
    }


async def reconcile_cash(session, tenant_id: str, period_end: datetime) -> dict[str, Any]:
    """期末现金 = 期初现金 + 现金净增减。"""
    cfs = session.execute(
        select(CashFlowStatement).where(
            CashFlowStatement.tenant_id == tenant_id,
            CashFlowStatement.period_end <= period_end,
        ).order_by(CashFlowStatement.period_end.desc()).limit(1)
    ).scalar_one_or_none()

    if not cfs:
        return {"check": "cash_reconciliation", "balanced": True, "message": "No cash flow data"}

    expected_ending = cfs.beginning_cash + cfs.net_cash_change
    diff = abs(cfs.ending_cash - expected_ending)

    return {
        "check": "cash_reconciliation",
        "balanced": diff < 0.01,
        "beginning_cash": cfs.beginning_cash,
        "net_cash_change": cfs.net_cash_change,
        "expected_ending": round(expected_ending, 2),
        "actual_ending": cfs.ending_cash,
        "difference": round(diff, 2),
        "period_end": period_end.isoformat() if period_end else None,
    }


def get_trial_balance(db_session, tenant_id: str, as_of_date: datetime) -> dict[str, Any]:
    """从 JournalEntry 汇总 → 试算平衡表。"""
    rows = db_session.execute(
        select(
            JournalEntry.account_id,
            func.sum(JournalEntry.debit_amount).label("total_debit"),
            func.sum(JournalEntry.credit_amount).label("total_credit"),
        ).where(
            JournalEntry.tenant_id == tenant_id,
            JournalEntry.entry_date <= as_of_date,
        ).group_by(JournalEntry.account_id)
    ).all()

    accounts = []
    total_debit = 0.0
    total_credit = 0.0
    for row in rows:
        d, c = round(float(row.total_debit or 0), 2), round(float(row.total_credit or 0), 2)
        total_debit += d
        total_credit += c
        accounts.append({"account_id": row.account_id, "debit": d, "credit": c, "net": round(d - c, 2)})

    diff = abs(total_debit - total_credit)
    return {
        "as_of": as_of_date.isoformat() if as_of_date else None,
        "accounts": accounts,
        "total_debit": round(total_debit, 2),
        "total_credit": round(total_credit, 2),
        "difference": round(diff, 2),
        "balanced": diff < 0.01,
    }


async def check_double_entry(session, tenant_id: str, period_start: datetime, period_end: datetime) -> list[dict]:
    """按月份分组检查借贷平衡。"""
    rows = session.execute(
        select(
            func.strftime("%Y-%m", JournalEntry.entry_date).label("month"),
            func.sum(JournalEntry.debit_amount).label("total_debit"),
            func.sum(JournalEntry.credit_amount).label("total_credit"),
        ).where(
            JournalEntry.tenant_id == tenant_id,
            JournalEntry.entry_date >= period_start,
            JournalEntry.entry_date <= period_end,
        ).group_by("month").order_by("month")
    ).all()

    unbalanced = []
    for row in rows:
        d, c = round(float(row.total_debit or 0), 2), round(float(row.total_credit or 0), 2)
        diff = round(abs(d - c), 2)
        if diff >= 0.01:
            unbalanced.append({"period": row.month, "debits": d, "credits": c, "difference": diff})

    return unbalanced


async def run_full_audit(session, tenant_id: str, period_end: datetime) -> dict[str, Any]:
    """执行全部 4 项审计检查。"""
    return {
        "net_income": await reconcile_net_income(session, tenant_id, period_end),
        "cash": await reconcile_cash(session, tenant_id, period_end),
        "trial_balance": get_trial_balance(session, tenant_id, period_end),
        "double_entry": await check_double_entry(session, tenant_id, period_end - (period_end - period_end.replace(day=1)), period_end),
    }
