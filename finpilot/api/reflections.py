"""错误自省日志路由 — 查看任务失败的模式、根因与修复建议.

对应前端：ReflectionsPage.tsx，调用 /reflections 前缀。
字段与前端 interface Reflection 对齐。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from finpilot.api.deps import get_current_user, get_db_session
from finpilot.database.models import ReflectionLog

router = APIRouter(prefix="/reflections", tags=["Reflections"])


def _to_response(r: ReflectionLog) -> dict[str, Any]:
    """ORM 对象转响应字典（字段与前端 interface Reflection 对齐）."""
    return {
        "id": str(r.id),
        "created_at": r.created_at.isoformat(sep=" ") if r.created_at else "",
        "task_name": r.task_name,
        "task_id": r.task_id,
        "resource_type": r.resource_type,
        "resource_id": r.resource_id,
        "exception_type": r.exception_type,
        "exception_message": r.exception_message,
        "stack_trace": r.stack_trace,
        "error_category": r.error_category,
        "root_cause": r.root_cause,
        "suggested_fix": r.suggested_fix,
        "retried": bool(r.retried),
        "resolved": bool(r.resolved),
        "resolution": r.resolution,
    }


@router.get("")
def list_reflections(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    category: str = Query(default="", description="按错误分类筛选"),
    resolved: str = Query(default="", description="按解决状态筛选: true/false"),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """列出错误自省日志（分页 + 分类/状态筛选）."""
    tenant_id = f"user_{current_user.get('user_id', 'default')}"

    q = db.query(ReflectionLog).filter(ReflectionLog.tenant_id == tenant_id)
    if category:
        q = q.filter(ReflectionLog.error_category == category)
    if resolved == "true":
        q = q.filter(ReflectionLog.resolved.is_(True))
    elif resolved == "false":
        q = q.filter(ReflectionLog.resolved.is_(False))

    total = q.count()
    items = (
        q.order_by(ReflectionLog.created_at.desc())
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


@router.get("/{reflection_id}")
def get_reflection(
    reflection_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """获取单条自省日志详情."""
    r = db.get(ReflectionLog, reflection_id)
    if not r:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="自省日志不存在")
    return {"code": 0, "message": "ok", "data": _to_response(r)}


@router.post("/{reflection_id}/resolve")
def resolve_reflection(
    reflection_id: int,
    payload: dict,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """标记自省日志为已解决，记录解决方案."""
    r = db.get(ReflectionLog, reflection_id)
    if not r:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="自省日志不存在")

    resolution = (payload.get("resolution") or "").strip()
    if not resolution:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="resolution 不能为空")

    r.resolved = True
    r.resolution = resolution
    try:
        db.commit()
        db.refresh(r)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"标记解决失败: {exc}"
        ) from exc

    try:
        from finpilot.services.audit_service import log_action

        log_action(
            db=db,
            action="reflection.resolve",
            resource=f"reflection:{r.id}",
            user=current_user,
            reason=f"标记自省已解决: {r.exception_type}",
            commit=False,
            target_object_type="reflection",
            target_object_id=str(r.id),
            meta={"resolution": resolution[:200]},
        )
    except Exception:  # noqa: BLE001
        pass

    return {"code": 0, "message": "ok", "data": _to_response(r)}
