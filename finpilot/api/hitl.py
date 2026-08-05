"""Human-in-the-loop 人工介入路由 — 高风险动作需人工审批.

对应前端：HitlPage.tsx，调用 /hitl 前缀。
提供 stats / list / detail / action 端点。
"""

from __future__ import annotations

from datetime import datetime
try:
    from datetime import UTC
except ImportError:  # Python 3.10 lacks datetime.UTC; use timezone.utc
    from datetime import timezone
    UTC = timezone.utc
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from finpilot.api.deps import get_current_user, get_db_session
from finpilot.database.models import HitlRequest

router = APIRouter(prefix="/hitl", tags=["HITL"])

_ACTION_TO_STATUS = {
    "approve": "approved",
    "reject": "rejected",
}


def _to_response(r: HitlRequest) -> dict[str, Any]:
    """ORM 对象转响应字典（字段与前端 interface HitlRequest 对齐）."""
    return {
        "id": str(r.id),
        "action_type": r.action_type,
        "description": r.description or "",
        "risk_level": r.risk_level,
        "action_params": r.action_params,
        "status": r.status,
        "created_at": r.created_at.isoformat(sep=" ") if r.created_at else "",
        "requested_by": r.requested_by,
        "resolved_by": r.resolved_by,
        "comment": r.comment,
        "resolved_at": r.resolved_at.isoformat(sep=" ") if r.resolved_at else None,
        "context": r.context,
    }


@router.get("/stats")
def hitl_stats(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """获取 HITL 统计数据（总数/待审/通过/拒绝/高风险待审）."""
    tenant_id = f"user_{current_user.get('user_id', 'default')}"
    q = db.query(HitlRequest).filter(HitlRequest.tenant_id == tenant_id)

    try:
        total = q.count()
        pending = q.filter(HitlRequest.status == "pending").count()
        approved = q.filter(HitlRequest.status == "approved").count()
        rejected = q.filter(HitlRequest.status == "rejected").count()
        high_risk_pending = q.filter(
            HitlRequest.status == "pending",
            HitlRequest.risk_level == "high",
        ).count()
    except Exception:  # noqa: BLE001
        total = pending = approved = rejected = high_risk_pending = 0

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "total": total,
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "high_risk_pending": high_risk_pending,
        },
    }


@router.get("")
def list_hitl(
    status_filter: str = Query(default="", alias="status_filter", description="按状态筛选: pending/approved/rejected"),
    risk_level: str = Query(default="", description="按风险等级筛选: low/medium/high"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """列出 HITL 请求（支持状态/风险筛选）.

    前端兼容直接返回数组与 { items } 两种形态，这里返回 { items }。
    """
    tenant_id = f"user_{current_user.get('user_id', 'default')}"
    q = db.query(HitlRequest).filter(HitlRequest.tenant_id == tenant_id)
    if status_filter:
        q = q.filter(HitlRequest.status == status_filter)
    if risk_level:
        q = q.filter(HitlRequest.risk_level == risk_level)

    total = q.count()
    items = (
        q.order_by(HitlRequest.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [_to_response(r) for r in items],
        },
    }


@router.get("/{hitl_id}")
def get_hitl(
    hitl_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """获取单条 HITL 请求详情."""
    r = db.get(HitlRequest, hitl_id)
    if not r:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="HITL 请求不存在")
    return {"code": 0, "message": "ok", "data": _to_response(r)}


@router.post("/{hitl_id}/action")
def hitl_action(
    hitl_id: int,
    payload: dict,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """审批 HITL 请求（approve/reject）."""
    action = (payload.get("action") or "").strip().lower()
    if action not in _ACTION_TO_STATUS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效动作: {action}，支持 approve/reject",
        )

    r = db.get(HitlRequest, hitl_id)
    if not r:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="HITL 请求不存在")
    if r.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"该请求已处理（当前状态: {r.status}）",
        )

    comment = (payload.get("comment") or "").strip()
    reviewer = (
        current_user.get("name")
        or current_user.get("email")
        or str(current_user.get("user_id", ""))
    )

    prev_status = r.status
    new_status = _ACTION_TO_STATUS[action]
    r.status = new_status
    r.resolved_by = reviewer
    r.comment = comment or None
    r.resolved_at = datetime.now(UTC)

    try:
        db.commit()
        db.refresh(r)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"审批失败: {exc}"
        ) from exc

    try:
        from finpilot.services.audit_service import log_action

        log_action(
            db=db,
            action=f"hitl.{action}",
            resource=f"hitl:{r.id}",
            user=current_user,
            reason=f"HITL {action}: {r.action_type}",
            commit=False,
            target_object_type="hitl",
            target_object_id=str(r.id),
            meta={"prev_status": prev_status, "new_status": new_status, "comment": comment[:200]},
        )
    except Exception:  # noqa: BLE001
        pass

    return {"code": 0, "message": "ok", "data": _to_response(r)}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_hitl(
    payload: dict,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """创建 HITL 请求（供智能体/工具调用，触发人工介入）."""
    action_type = (payload.get("action_type") or "").strip()
    if not action_type:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="action_type 不能为空")

    risk_level = (payload.get("risk_level") or "medium").strip().lower()
    if risk_level not in {"low", "medium", "high"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="risk_level 无效，支持 low/medium/high",
        )

    requester = (
        current_user.get("name")
        or current_user.get("email")
        or str(current_user.get("user_id", ""))
    )
    tenant_id = f"user_{current_user.get('user_id', 'default')}"

    r = HitlRequest(
        tenant_id=tenant_id,
        action_type=action_type,
        description=payload.get("description"),
        risk_level=risk_level,
        action_params=payload.get("action_params"),
        context=payload.get("context"),
        status="pending",
        requested_by=requester,
    )
    db.add(r)
    try:
        db.commit()
        db.refresh(r)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"创建失败: {exc}"
        ) from exc

    return {"code": 0, "message": "ok", "data": _to_response(r)}
