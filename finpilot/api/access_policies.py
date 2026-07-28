"""访问策略路由 — ABAC 访问控制策略管理.

对应前端：AccessPoliciesPage.tsx，通过 useCrudResource 调用 /access-policies 前缀。
支持 list / create / update / delete，字段与前端 types/accessPolicy.ts 对齐。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from finpilot.api.deps import get_current_user, get_db_session
from finpilot.database.models import AccessPolicy

router = APIRouter(prefix="/access-policies", tags=["Access Policies"])

# 合法枚举（与前端 RESOURCE_TYPES / ACTIONS / EFFECT_LABELS 对齐）
_RESOURCE_TYPES = {"report", "document", "audit", "approval", "user", "api_key"}
_ACTIONS = {"read", "write", "delete", "export", "approve"}
_EFFECTS = {"allow", "deny"}


def _to_response(p: AccessPolicy) -> dict[str, Any]:
    """ORM 对象转响应字典（字段与前端 types/accessPolicy.ts 对齐）."""
    return {
        "id": str(p.id),
        "tenant_id": p.tenant_id or "",
        "name": p.name,
        "resource_type": p.resource_type,
        "action": p.action,
        "effect": p.effect,
        "priority": p.priority,
        "conditions": p.conditions,
        "description": p.description,
        "is_active": bool(p.is_active),
        "created_at": p.created_at.isoformat(sep=" ") if p.created_at else None,
        "updated_at": p.updated_at.isoformat(sep=" ") if p.updated_at else None,
    }


def _validate_payload(payload: dict, *, partial: bool = False) -> None:
    """校验 payload 字段合法性."""
    if not partial or "resource_type" in payload:
        rt = payload.get("resource_type")
        if rt not in _RESOURCE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"resource_type 无效，支持: {sorted(_RESOURCE_TYPES)}",
            )
    if not partial or "action" in payload:
        act = payload.get("action")
        if act not in _ACTIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"action 无效，支持: {sorted(_ACTIONS)}",
            )
    if not partial or "effect" in payload:
        eff = payload.get("effect")
        if eff is not None and eff not in _EFFECTS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"effect 无效，支持: {sorted(_EFFECTS)}",
            )


@router.get("")
def list_policies(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    resource_type: str = Query(default="", description="按资源类型筛选"),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """列出当前租户的访问策略（分页）."""
    tenant_id = f"user_{current_user.get('user_id', 'default')}"

    q = db.query(AccessPolicy).filter(AccessPolicy.tenant_id == tenant_id)
    if resource_type:
        q = q.filter(AccessPolicy.resource_type == resource_type)

    total = q.count()
    items = (
        q.order_by(AccessPolicy.priority.asc(), AccessPolicy.id.desc())
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
            "items": [_to_response(p) for p in items],
        },
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_policy(
    payload: dict,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """新建访问策略."""
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name 不能为空")
    _validate_payload(payload)

    tenant_id = f"user_{current_user.get('user_id', 'default')}"
    policy = AccessPolicy(
        tenant_id=tenant_id,
        name=name,
        resource_type=payload["resource_type"],
        action=payload["action"],
        effect=payload.get("effect", "allow"),
        priority=int(payload.get("priority", 100)),
        conditions=payload.get("conditions"),
        description=payload.get("description"),
        is_active=bool(payload.get("is_active", True)),
        created_by=current_user.get("user_id"),
    )
    db.add(policy)
    try:
        db.commit()
        db.refresh(policy)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"创建失败: {exc}"
        ) from exc

    try:
        from finpilot.services.audit_service import log_action

        log_action(
            db=db,
            action="access_policy.create",
            resource=f"access_policy:{policy.id}",
            user=current_user,
            reason=f"新建策略: {name}",
            commit=False,
            target_object_type="access_policy",
            target_object_id=str(policy.id),
        )
    except Exception:  # noqa: BLE001
        pass

    return {"code": 0, "message": "ok", "data": _to_response(policy)}


@router.put("/{policy_id}")
def update_policy(
    policy_id: int,
    payload: dict,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """更新访问策略（支持部分更新）."""
    policy = db.get(AccessPolicy, policy_id)
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="策略不存在")

    tenant_id = f"user_{current_user.get('user_id', 'default')}"
    if policy.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作他人策略")

    _validate_payload(payload, partial=True)

    for field in ("name", "resource_type", "action", "effect", "priority", "conditions", "description", "is_active"):
        if field in payload:
            value = payload[field]
            if field == "priority":
                value = int(value)
            if field == "is_active":
                value = bool(value)
            setattr(policy, field, value)

    try:
        db.commit()
        db.refresh(policy)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"更新失败: {exc}"
        ) from exc

    return {"code": 0, "message": "ok", "data": _to_response(policy)}


@router.delete("/{policy_id}", status_code=status.HTTP_200_OK)
def delete_policy(
    policy_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """删除访问策略."""
    policy = db.get(AccessPolicy, policy_id)
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="策略不存在")

    tenant_id = f"user_{current_user.get('user_id', 'default')}"
    if policy.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作他人策略")

    try:
        db.delete(policy)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"删除失败: {exc}"
        ) from exc

    return {"code": 0, "message": "ok", "data": {"id": str(policy_id), "deleted": True}}
