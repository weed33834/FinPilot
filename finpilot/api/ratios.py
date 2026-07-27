# -*- coding: utf-8 -*-
"""财务比率 API 路由 — 暴露 FinancialRatioEngine 为 REST 端点。

端点：
- POST /api/v1/ratios/compute  传入财务数据 JSON，返回全部比率
- GET  /api/v1/ratios/compute  从数据库最新财务数据计算比率
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from finpilot.services.financial_ratios import engine, RatioResult

router = APIRouter(prefix="/ratios", tags=["ratios"])


class FinancialDataInput(BaseModel):
    """财务报表数据输入 — 按需提供字段，缺失字段对应比率返回 null。"""
    revenue: float | None = None
    revenue_prior: float | None = None
    cogs: float | None = None
    net_income: float | None = None
    net_income_prior: float | None = None
    operating_income: float | None = None
    ebitda: float | None = None
    total_assets: float | None = None
    total_assets_prior: float | None = None
    total_liabilities: float | None = None
    total_equity: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    inventory: float | None = None
    inventory_prior: float | None = None
    accounts_receivable: float | None = None
    accounts_receivable_prior: float | None = None
    accounts_payable: float | None = None
    accounts_payable_prior: float | None = None
    interest_expense: float | None = None
    nopat: float | None = None
    tax_rate: float | None = None
    invested_capital: float | None = None
    operating_cash_flow: float | None = None
    capex: float | None = None
    shares_outstanding: float | None = None
    market_cap: float | None = None
    enterprise_value: float | None = None
    dividends: float | None = None
    stock_price: float | None = None


def _ok(data):
    """统一成功响应格式。"""
    return {"code": 0, "message": "ok", "data": data}


def _ratio_to_dict(r: RatioResult) -> dict:
    return {
        "name": r.name,
        "category": r.category,
        "value": r.value,
        "formula": r.formula,
        "interpretation": r.interpretation,
        "unit": r.unit,
    }


@router.post("/compute")
async def compute_ratios_from_input(body: FinancialDataInput):
    """POST: 传入财务数据 JSON，返回全部 30+ 比率。

    示例请求体::

        {
            "revenue": 1000000,
            "cogs": 600000,
            "net_income": 100000,
            "total_equity": 500000,
            "total_assets": 1000000,
            "current_assets": 300000,
            "current_liabilities": 200000
        }
    """
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="至少提供一个财务数据字段")
    results = engine.compute_from_dict(data)
    return _ok([_ratio_to_dict(r) for r in results])


@router.get("/compute")
async def compute_ratios_from_db():
    """GET: 从数据库拉取最新财务报表数据自动计算比率。

    聚合 JournalEntry 表的 debit_amount/credit_amount 生成基础数据后计算。
    无实际分录时返回空列表。
    """
    try:
        from finpilot.database import SessionLocal
        from finpilot.database.models import JournalEntry
        from sqlalchemy import func
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"数据库模块不可用: {e}")

    db = SessionLocal()
    try:
        # 总借方 / 总贷方（简化：借方→费用类，贷方→收入类）
        totals = (
            db.query(
                func.coalesce(func.sum(JournalEntry.debit_amount), 0),
                func.coalesce(func.sum(JournalEntry.credit_amount), 0),
            )
            .first()
        )
        total_debit = float(totals[0]) if totals else 0.0
        total_credit = float(totals[1]) if totals else 0.0

        if total_credit == 0 and total_debit == 0:
            return _ok([])

        data = {
            "revenue": total_credit,
            "cogs": total_debit * 0.6,
            "net_income": total_credit - total_debit,
            "operating_income": (total_credit - total_debit) * 0.7,
        }
        results = engine.compute_from_dict(data)
        return _ok([_ratio_to_dict(r) for r in results])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"计算失败: {exc}")
    finally:
        db.close()
