# -*- coding: utf-8 -*-
"""三表联动投影 API 路由。

端点：
    POST /api/v1/projection/run     发起三表联动投影
    POST /api/v1/projection/assumptions  保存假设参数集
    GET  /api/v1/projection/assumptions  列出历史假设参数集
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from finpilot.services.three_statement_engine import ThreeStatementEngine

router = APIRouter(prefix="/projection", tags=["projection"])


class ProjectionRequest(BaseModel):
    revenue_growth: float = 0.08
    cogs_pct: float = 0.60
    opex_pct: float = 0.25
    tax_rate: float = 0.25
    capex_pct: float = 0.05
    depreciation_rate: float = 0.10
    dividend_payout: float = 0.30
    ar_days: float = 45
    ap_days: float = 30
    inventory_days: float = 60
    periods: int = 4
    base_revenue: float | None = None
    total_assets: float = 1_000_000
    current_assets: float = 400_000
    non_current_assets: float = 600_000
    total_liabilities: float = 400_000
    current_liabilities: float = 240_000
    non_current_liabilities: float = 160_000
    total_equity: float = 600_000
    retained_earnings: float = 180_000
    cash: float = 120_000
    accounts_receivable: float = 120_000
    inventory: float = 80_000
    accounts_payable: float = 96_000


class AssumptionSaveRequest(BaseModel):
    name: str
    parameters: dict
    periods: int = 4


def _ok(data):
    return {"code": 0, "message": "ok", "data": data}


def _df_to_dicts(df):
    """DataFrame → list of dicts，处理 NaN。"""
    import pandas as pd
    records = df.to_dict(orient="records")
    for r in records:
        for k, v in r.items():
            if isinstance(v, float) and pd.isna(v):
                r[k] = None
    return records


@router.post("/run")
async def run_projection(req: ProjectionRequest):
    """POST: 发起三表联动投影。

    返回 IS / BS / CF 三张投影表 + 平衡诊断。
    """
    engine = ThreeStatementEngine()

    historical_bs = {
        "total_assets": req.total_assets,
        "current_assets": req.current_assets,
        "non_current_assets": req.non_current_assets,
        "total_liabilities": req.total_liabilities,
        "current_liabilities": req.current_liabilities,
        "non_current_liabilities": req.non_current_liabilities,
        "total_equity": req.total_equity,
        "retained_earnings": req.retained_earnings,
        "cash": req.cash,
        "accounts_receivable": req.accounts_receivable,
        "inventory": req.inventory,
        "accounts_payable": req.accounts_payable,
    }

    assumptions = {
        "revenue_growth": req.revenue_growth,
        "cogs_pct": req.cogs_pct,
        "opex_pct": req.opex_pct,
        "tax_rate": req.tax_rate,
        "capex_pct": req.capex_pct,
        "depreciation_rate": req.depreciation_rate,
        "dividend_payout": req.dividend_payout,
        "ar_days": req.ar_days,
        "ap_days": req.ap_days,
        "inventory_days": req.inventory_days,
    }

    try:
        result = engine.run_projection(
            historical_bs=historical_bs,
            assumptions=assumptions,
            periods=req.periods,
            base_revenue=req.base_revenue,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"投影计算失败: {exc}")

    return _ok({
        "income_statement": _df_to_dicts(result.income_statement),
        "balance_sheet": _df_to_dicts(result.balance_sheet),
        "cash_flow": _df_to_dicts(result.cash_flow),
        "balanced": result.balanced,
        "diagnostics": result.diagnostics,
    })


@router.post("/assumptions")
async def save_assumptions(req: AssumptionSaveRequest):
    """POST: 保存假设参数集到数据库。"""
    try:
        from finpilot.database import SessionLocal
        from finpilot.database.models import AssumptionSet
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"数据库模块不可用: {e}")

    db = SessionLocal()
    try:
        a = AssumptionSet(name=req.name, parameters=req.parameters, periods=req.periods)
        db.add(a)
        db.commit()
        db.refresh(a)
        return _ok({"id": a.id, "name": a.name, "periods": a.periods})
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"保存失败: {exc}")
    finally:
        db.close()


@router.get("/assumptions")
async def list_assumptions():
    """GET: 列出所有假设参数集。"""
    try:
        from finpilot.database import SessionLocal
        from finpilot.database.models import AssumptionSet
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"数据库模块不可用: {e}")

    db = SessionLocal()
    try:
        sets = db.query(AssumptionSet).order_by(AssumptionSet.created_at.desc()).limit(20).all()
        return _ok([{"id": s.id, "name": s.name, "periods": s.periods, "created_at": str(s.created_at)} for s in sets])
    finally:
        db.close()
