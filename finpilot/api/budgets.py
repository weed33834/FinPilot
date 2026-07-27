# -*- coding: utf-8 -*-
"""预算管理 CRUD — 10 个端点，使用 RBAC 权限守卫。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from finpilot.api.deps import get_current_user, get_db_session
from finpilot.core.approval_state import ApprovalState, validate_transition
from finpilot.core.permissions import Permission, require_permission
from finpilot.database.models import Budget, BudgetItem

router = APIRouter(prefix="/budgets", tags=["budgets"])


class BudgetItemCreate(BaseModel):
    category: str = Field(..., max_length=64)
    description: str | None = Field(None, max_length=500)
    amount: float = Field(..., ge=0)
    account_code: str | None = Field(None, max_length=32)
    notes: str | None = None


class BudgetItemUpdate(BaseModel):
    category: str | None = Field(None, max_length=64)
    description: str | None = Field(None, max_length=500)
    amount: float | None = Field(None, ge=0)
    account_code: str | None = Field(None, max_length=32)
    notes: str | None = None


class BudgetCreate(BaseModel):
    name: str = Field(..., max_length=200)
    year: int = Field(..., ge=2020, le=2099)
    department: str | None = Field(None, max_length=100)
    notes: str | None = None
    items: list[BudgetItemCreate] = []


class BudgetUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    department: str | None = Field(None, max_length=100)
    notes: str | None = None


class ApproveRequest(BaseModel):
    approved: bool
    reason: str | None = None


def _item_dict(item) -> dict:
    return {
        "id": item.id, "budget_id": item.budget_id, "category": item.category,
        "description": item.description, "amount": item.amount,
        "account_code": item.account_code, "notes": item.notes,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _budget_dict(b: Budget) -> dict:
    return {
        "id": b.id, "name": b.name, "year": b.year, "department": b.department,
        "total_amount": b.total_amount, "status": b.status,
        "created_by": b.created_by, "approved_by": b.approved_by,
        "approved_at": b.approved_at.isoformat() if b.approved_at else None,
        "reject_reason": b.reject_reason, "notes": b.notes,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
        "items": [_item_dict(it) for it in (b.items or [])],
    }


def _recalc(db: Session, budget: Budget):
    budget.total_amount = sum(it.amount for it in budget.items)
    db.flush()


@router.post("", dependencies=[Depends(require_permission(Permission.CREATE_BUDGET))])
async def create_budget(body: BudgetCreate, db=Depends(get_db_session), user=Depends(get_current_user)):
    b = Budget(name=body.name, year=body.year, department=body.department,
               notes=body.notes, created_by=user["id"], tenant_id=user.get("tenant_id"))
    db.add(b)
    db.flush()
    for it in body.items:
        db.add(BudgetItem(budget_id=b.id, category=it.category, description=it.description,
                          amount=it.amount, account_code=it.account_code, notes=it.notes,
                          tenant_id=user.get("tenant_id")))
    _recalc(db, b)
    db.commit()
    db.refresh(b)
    return {"code": 0, "message": "ok", "data": _budget_dict(b)}


@router.get("", dependencies=[Depends(require_permission(Permission.VIEW_BUDGET))])
async def list_budgets(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                       year: int | None = None, status: str | None = None,
                       department: str | None = None, db=Depends(get_db_session),
                       user=Depends(get_current_user)):
    tid = user.get("tenant_id")
    base = select(Budget).where(Budget.tenant_id == tid)
    cnt_base = select(func.count(Budget.id)).where(Budget.tenant_id == tid)
    for col, val in [(Budget.year, year), (Budget.status, status), (Budget.department, department)]:
        if val is not None:
            base = base.where(col == val)
            cnt_base = cnt_base.where(col == val)
    total = db.execute(cnt_base).scalar() or 0
    items = db.execute(base.order_by(Budget.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return {"code": 0, "message": "ok", "data": {"total": total, "page": page, "page_size": page_size, "items": [_budget_dict(b) for b in items]}}


@router.get("/{budget_id}", dependencies=[Depends(require_permission(Permission.VIEW_BUDGET))])
async def get_budget(budget_id: int, db=Depends(get_db_session), user=Depends(get_current_user)):
    b = db.execute(select(Budget).where(Budget.id == budget_id, Budget.tenant_id == user.get("tenant_id"))).scalar_one_or_none()
    if not b:
        raise HTTPException(404, "Budget not found")
    return {"code": 0, "message": "ok", "data": _budget_dict(b)}


@router.put("/{budget_id}")
async def update_budget(budget_id: int, body: BudgetUpdate, db=Depends(get_db_session), user=Depends(get_current_user)):
    b = db.execute(select(Budget).where(Budget.id == budget_id, Budget.tenant_id == user.get("tenant_id"))).scalar_one_or_none()
    if not b:
        raise HTTPException(404, "Budget not found")
    for f in ["name", "department", "notes"]:
        v = getattr(body, f)
        if v is not None:
            setattr(b, f, v)
    b.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(b)
    return {"code": 0, "message": "ok", "data": _budget_dict(b)}


@router.post("/{budget_id}/items", dependencies=[Depends(require_permission(Permission.CREATE_BUDGET))])
async def add_item(budget_id: int, body: BudgetItemCreate, db=Depends(get_db_session), user=Depends(get_current_user)):
    b = db.execute(select(Budget).where(Budget.id == budget_id, Budget.tenant_id == user.get("tenant_id"))).scalar_one_or_none()
    if not b:
        raise HTTPException(404, "Budget not found")
    it = BudgetItem(budget_id=b.id, category=body.category, description=body.description,
                    amount=body.amount, account_code=body.account_code, notes=body.notes,
                    tenant_id=user.get("tenant_id"))
    db.add(it)
    db.flush()
    _recalc(db, b)
    db.commit()
    db.refresh(b)
    return {"code": 0, "message": "ok", "data": _budget_dict(b)}


@router.put("/{budget_id}/items/{item_id}")
async def update_item(budget_id: int, item_id: int, body: BudgetItemUpdate, db=Depends(get_db_session), user=Depends(get_current_user)):
    b = db.execute(select(Budget).where(Budget.id == budget_id, Budget.tenant_id == user.get("tenant_id"))).scalar_one_or_none()
    if not b:
        raise HTTPException(404, "Budget not found")
    it = db.execute(select(BudgetItem).where(BudgetItem.id == item_id, BudgetItem.budget_id == budget_id)).scalar_one_or_none()
    if not it:
        raise HTTPException(404, "Budget item not found")
    for f in ["category", "description", "account_code", "notes"]:
        v = getattr(body, f)
        if v is not None:
            setattr(it, f, v)
    if body.amount is not None:
        it.amount = body.amount
    _recalc(db, b)
    db.commit()
    db.refresh(b)
    return {"code": 0, "message": "ok", "data": _budget_dict(b)}


@router.delete("/{budget_id}/items/{item_id}")
async def delete_item(budget_id: int, item_id: int, db=Depends(get_db_session), user=Depends(get_current_user)):
    b = db.execute(select(Budget).where(Budget.id == budget_id, Budget.tenant_id == user.get("tenant_id"))).scalar_one_or_none()
    if not b:
        raise HTTPException(404, "Budget not found")
    it = db.execute(select(BudgetItem).where(BudgetItem.id == item_id, BudgetItem.budget_id == budget_id)).scalar_one_or_none()
    if not it:
        raise HTTPException(404, "Budget item not found")
    db.delete(it)
    _recalc(db, b)
    db.commit()
    return {"code": 0, "message": "ok", "data": None}


@router.post("/{budget_id}/submit")
async def submit_budget(budget_id: int, db=Depends(get_db_session), user=Depends(get_current_user)):
    b = db.execute(select(Budget).where(Budget.id == budget_id, Budget.tenant_id == user.get("tenant_id"))).scalar_one_or_none()
    if not b:
        raise HTTPException(404, "Budget not found")
    try:
        validate_transition(b.status, ApprovalState.SUBMITTED.value)
    except ValueError as e:
        raise HTTPException(400, str(e))
    b.status = ApprovalState.SUBMITTED.value
    b.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(b)
    return {"code": 0, "message": "ok", "data": _budget_dict(b)}


@router.post("/{budget_id}/approve", dependencies=[Depends(require_permission(Permission.APPROVE_BUDGET))])
async def approve_budget(budget_id: int, body: ApproveRequest, db=Depends(get_db_session), user=Depends(get_current_user)):
    b = db.execute(select(Budget).where(Budget.id == budget_id, Budget.tenant_id == user.get("tenant_id"))).scalar_one_or_none()
    if not b:
        raise HTTPException(404, "Budget not found")
    target = ApprovalState.APPROVED.value if body.approved else ApprovalState.REJECTED.value
    try:
        validate_transition(b.status, target)
    except ValueError as e:
        raise HTTPException(400, str(e))
    b.status = target
    b.approved_by = user["id"]
    b.approved_at = datetime.utcnow()
    if not body.approved:
        b.reject_reason = body.reason
    db.commit()
    db.refresh(b)
    return {"code": 0, "message": "ok", "data": _budget_dict(b)}


@router.post("/{budget_id}/reject", dependencies=[Depends(require_permission(Permission.APPROVE_BUDGET))])
async def reject_budget(budget_id: int, body: ApproveRequest, db=Depends(get_db_session), user=Depends(get_current_user)):
    """独立驳回端点 — 状态必须是 SUBMITTED，改为 REJECTED。"""
    b = db.execute(select(Budget).where(Budget.id == budget_id, Budget.tenant_id == user.get("tenant_id"))).scalar_one_or_none()
    if not b:
        raise HTTPException(404, "Budget not found")
    try:
        validate_transition(b.status, ApprovalState.REJECTED.value)
    except ValueError as e:
        raise HTTPException(400, str(e))
    b.status = ApprovalState.REJECTED.value
    b.approved_by = user["id"]
    b.approved_at = datetime.utcnow()
    b.reject_reason = body.reason or ""
    db.commit()
    db.refresh(b)
    return {"code": 0, "message": "ok", "data": _budget_dict(b)}


@router.post("/{budget_id}/reopen")
async def reopen_budget(budget_id: int, db=Depends(get_db_session), user=Depends(get_current_user)):
    """重新打开已驳回预算 — 状态从 REJECTED 回到 SUBMITTED。"""
    b = db.execute(select(Budget).where(Budget.id == budget_id, Budget.tenant_id == user.get("tenant_id"))).scalar_one_or_none()
    if not b:
        raise HTTPException(404, "Budget not found")
    try:
        validate_transition(b.status, ApprovalState.SUBMITTED.value)
    except ValueError as e:
        raise HTTPException(400, str(e))
    b.status = ApprovalState.SUBMITTED.value
    b.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(b)
    return {"code": 0, "message": "ok", "data": _budget_dict(b)}
