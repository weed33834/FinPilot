# -*- coding: utf-8 -*-
"""Recharts 可视化数据 API — 前端图表直接消费的 JSON 端点。"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func

from finpilot.api.deps import get_current_user, get_db_session
from finpilot.database.models import JournalEntry, BalanceSheet, IncomeStatement, CashFlowStatement, Budget, Invoice

router = APIRouter(prefix="/charts", tags=["charts"])


@router.get("/revenue-trend")
async def revenue_trend(months: int = Query(default=12, ge=1, le=60), db=Depends(get_db_session), user=Depends(get_current_user)):
    tid = user.get("tenant_id")
    rows = db.execute(
        select(func.strftime("%Y-%m", JournalEntry.entry_date).label("month"),
               func.sum(JournalEntry.credit_amount).label("revenue"))
        .where(JournalEntry.tenant_id == tid, JournalEntry.debit_amount == 0)
        .group_by("month").order_by("month").limit(months)
    ).all()
    return {"code": 0, "data": {
        "labels": [r.month for r in rows],
        "series": [{"name": "Revenue", "data": [round(r.revenue or 0, 2) for r in rows]}],
    }}


@router.get("/expense-category")
async def expense_category(start_date: date = Query(...), end_date: date = Query(...),
                           db=Depends(get_db_session), user=Depends(get_current_user)):
    tid = user.get("tenant_id")
    rows = db.execute(
        select(JournalEntry.description, func.sum(JournalEntry.debit_amount).label("total"))
        .where(JournalEntry.tenant_id == tid,
               JournalEntry.entry_date >= start_date,
               JournalEntry.entry_date <= end_date,
               JournalEntry.debit_amount > 0)
        .group_by(JournalEntry.description).order_by(func.sum(JournalEntry.debit_amount).desc())
    ).all()
    return {"code": 0, "data": [
        {"name": r.description or "Other", "value": round(float(r.total or 0), 2)} for r in rows
    ]}


@router.get("/profit-margin")
async def profit_margin(months: int = Query(default=12, ge=1, le=60), db=Depends(get_db_session), user=Depends(get_current_user)):
    tid = user.get("tenant_id")
    rows = db.execute(
        select(IncomeStatement).where(IncomeStatement.tenant_id == tid)
        .order_by(IncomeStatement.period_end.desc()).limit(months)
    ).scalars().all()
    return {"code": 0, "data": {
        "labels": [r.period_end.strftime("%Y-%m") for r in reversed(rows)],
        "series": [
            {"name": "Net Income", "data": [r.net_income for r in reversed(rows)]},
            {"name": "Revenue", "data": [r.revenue for r in reversed(rows)]},
        ],
    }}


@router.get("/cash-flow")
async def cash_flow(months: int = Query(default=12, ge=1, le=60), db=Depends(get_db_session), user=Depends(get_current_user)):
    tid = user.get("tenant_id")
    rows = db.execute(
        select(CashFlowStatement).where(CashFlowStatement.tenant_id == tid)
        .order_by(CashFlowStatement.period_end.desc()).limit(months)
    ).scalars().all()
    return {"code": 0, "data": {
        "labels": [r.period_end.strftime("%Y-%m") for r in reversed(rows)],
        "series": [
            {"name": "Operating", "data": [r.operating_activities for r in reversed(rows)]},
            {"name": "Investing", "data": [r.investing_activities for r in reversed(rows)]},
            {"name": "Financing", "data": [r.financing_activities for r in reversed(rows)]},
        ],
    }}


@router.get("/budget-vs-actual")
async def budget_vs_actual(year: int = Query(...), db=Depends(get_db_session), user=Depends(get_current_user)):
    tid = user.get("tenant_id")
    budgets = db.execute(
        select(Budget).where(Budget.tenant_id == tid, Budget.year == year, Budget.status == "approved")
    ).scalars().all()
    if not budgets:
        return {"code": 0, "data": {"labels": [], "series": []}}
    categories = sorted(set(it.category for b in budgets for it in (b.items or [])))
    budget_totals = {c: sum(it.amount for b in budgets for it in (b.items or []) if it.category == c) for c in categories}
    return {"code": 0, "data": {
        "labels": categories,
        "series": [{"name": "Budget", "data": [round(budget_totals.get(c, 0), 2) for c in categories]}],
    }}


@router.get("/balance-sheet-structure")
async def balance_sheet_structure(as_of: date = Query(...), db=Depends(get_db_session), user=Depends(get_current_user)):
    tid = user.get("tenant_id")
    bs = db.execute(
        select(BalanceSheet).where(BalanceSheet.tenant_id == tid, BalanceSheet.period_end <= as_of)
        .order_by(BalanceSheet.period_end.desc())
    ).scalars().first()
    if not bs:
        return {"code": 0, "data": []}
    return {"code": 0, "data": [
        {"name": "Current Assets", "value": bs.current_assets},
        {"name": "Non-Current Assets", "value": bs.non_current_assets},
        {"name": "Current Liabilities", "value": bs.current_liabilities},
        {"name": "Non-Current Liabilities", "value": bs.non_current_liabilities},
        {"name": "Equity", "value": bs.total_equity},
    ]}


@router.get("/dashboard-kpi")
async def dashboard_kpi(db=Depends(get_db_session), user=Depends(get_current_user)):
    tid = user.get("tenant_id")
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    revenue = db.execute(
        select(func.sum(JournalEntry.credit_amount))
        .where(JournalEntry.tenant_id == tid, JournalEntry.entry_date >= month_start)
    ).scalar() or 0.0

    expense = db.execute(
        select(func.sum(JournalEntry.debit_amount))
        .where(JournalEntry.tenant_id == tid, JournalEntry.entry_date >= month_start)
    ).scalar() or 0.0

    receivable = db.execute(
        select(func.sum(Invoice.total_amount))
        .where(Invoice.tenant_id == tid, Invoice.invoice_type == "receivable", Invoice.status == "pending")
    ).scalar() or 0.0

    payable = db.execute(
        select(func.sum(Invoice.total_amount))
        .where(Invoice.tenant_id == tid, Invoice.invoice_type == "payable", Invoice.status == "pending")
    ).scalar() or 0.0

    return {"code": 0, "data": {
        "monthly_revenue": round(float(revenue), 2),
        "monthly_expense": round(float(expense), 2),
        "monthly_profit": round(float(revenue) - float(expense), 2),
        "accounts_receivable": round(float(receivable), 2),
        "accounts_payable": round(float(payable), 2),
    }}
