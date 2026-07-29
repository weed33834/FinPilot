# -*- coding: utf-8 -*-
"""审计日志路由（管理员/审计员）。

响应统一包裹为 ``{code, message, data}`` 格式。

- GET /logs  分页列出审计日志（最新在前）
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from finpilot.database.models import AuditLog

from .deps import get_db_session, require_admin

router = APIRouter(prefix="/audit", tags=["audit"])


def _ok(data: Any, message: str = "success") -> dict:
    return {"code": 0, "message": message, "data": data}


def _row_dict(row: AuditLog) -> dict:
    """ORM 行 -> 前端 AuditLog 结构。

    前端 types/audit.ts 期望字段：
      { id, timestamp, tenant_id, user_id, action, resource, result, ip, reason }
    后端 AuditLog ORM 已补齐 resource / ip_address / target_object_type / target_object_id
    （迁移 e1f2a3b4c5d6），此处读取真实值而非硬编码 None。
    """
    return {
        "id": str(row.id),
        "timestamp": row.created_at.isoformat() if row.created_at else None,
        "tenant_id": row.tenant_id or "",
        "user_id": str(row.user_id) if row.user_id is not None else None,
        "action": row.action or "",
        "resource": getattr(row, "resource", None),
        "result": row.status or None,
        "ip": getattr(row, "ip_address", None),
        "reason": row.detail or None,
    }


@router.get("/logs")
def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    action: str | None = Query(None, description="按动作类型过滤"),
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """分页列出审计日志（最新在前）。

    返回结构与前端 useCrudResource 兼容：``{ code, message, data: { items, total, page, page_size } }``。
    """
    try:
        query = db.query(AuditLog)
        if action:
            query = query.filter(AuditLog.action == action)
        total = query.count()
        rows = (
            query.order_by(AuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
    except SQLAlchemyError as exc:
        # 表缺失或 schema 不匹配属可预期情况（首次启动未初始化），返回空列表而非 500
        return _ok({
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "error": f"audit_logs 表不可用: {exc}",
        })
    return _ok({
        "items": [_row_dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    })
