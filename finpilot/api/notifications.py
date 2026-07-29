# -*- coding: utf-8 -*-
"""``/notifications`` —— 站内通知管理（对接前端 NotificationBell 组件）。

前端契约（types/notification.ts + NotificationBell.tsx）：
- GET /notifications?page=1&page_size=20 → ApiResponse<{items: Notification[], total}>
- POST /notifications/{id}/read → ApiResponse<null>

Notification 字段：id / user_id / channel / title / content / is_read / created_at

本模块从 audit_service 的 log_action 写入链路接收通知（channel 映射 action 前缀），
也可由其他业务模块直接调用 ``create_notification`` 写入。
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from finpilot.database.models import Notification

from .deps import get_current_user, get_db_session, tenant_of

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _ok(data: Any, message: str = "success") -> dict:
    return {"code": 0, "message": message, "data": data}


def _serialize(n: Notification) -> dict:
    """Notification ORM → 前端 Notification 字段。"""
    return {
        "id": str(n.id),
        "user_id": str(n.user_id),
        "channel": n.channel or "system",
        "title": n.title or "",
        "content": n.content or "",
        "is_read": bool(n.is_read),
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


def _user_id_of(current_user: dict) -> str:
    """从当前用户解析通知归属 user_id（与审计日志一致用 user_{id}）。"""
    return f"user_{current_user.get('user_id', 'default')}"


def create_notification(
    db: Session,
    *,
    user_id: str,
    channel: str = "system",
    title: str,
    content: Optional[str] = None,
    tenant_id: Optional[str] = None,
    commit: bool = True,
) -> Notification:
    """供其他业务模块调用的写入入口（如审批通过、报告生成完成时推送通知）。

    channel 取值：approval / report / document / agent / security / system
    """
    n = Notification(
        tenant_id=tenant_id or "default",
        user_id=str(user_id),
        channel=channel,
        title=title,
        content=content,
        is_read=False,
    )
    db.add(n)
    if commit:
        db.commit()
        db.refresh(n)
    return n


def notify_user(
    db: Session,
    user_id: str,
    channel: str,
    title: str,
    content: Optional[str] = None,
    tenant_id: Optional[str] = None,
    ws_push: bool = True,
) -> Notification:
    """业务模块推送通知的便捷入口：先落 DB 再 WebSocket 实时推送。

    ``user_id`` 须为 ``user_{id}`` 格式（与 ``_user_id_of`` / ``tenant_of`` 一致），
    同时也是 ``ConnectionManager`` 的连接分组键。WebSocket 推送为 best-effort：
    跨线程 / 无事件循环场景会自动降级，失败不影响 DB 写入。

    调用方示例::

        notify_user(db, f"user_{report.created_by}", "report",
                    "报告生成完成", f"《{report.title}》已就绪")
    """
    n = create_notification(
        db,
        user_id=user_id,
        channel=channel,
        title=title,
        content=content,
        tenant_id=tenant_id,
    )

    if ws_push:
        # 局部导入避免在 notifications 模块加载时强依赖 websocket（避免循环导入）
        try:
            from .websocket import manager

            manager.send_to_user_sync(user_id, {
                "type": "notification",
                "data": _serialize(n),
                "timestamp": (
                    n.created_at.isoformat() if n.created_at else None
                ),
            })
        except Exception:  # noqa: BLE001  WS 推送失败不影响通知主流程
            pass
    return n


@router.get("")
def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_read: Optional[str] = Query(None, description="按已读状态筛选: true/false"),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """列出当前用户的通知（分页，最新在前）。

    前端 NotificationBell 期望 data 为 {items, total} 或直接为数组，
    这里统一返回 {items, total, page, page_size} 兼容两种消费方式。
    """
    uid = _user_id_of(current_user)
    tenant_id = tenant_of(current_user)
    q = db.query(Notification).filter(
        Notification.tenant_id == tenant_id,
        Notification.user_id == uid,
    )
    if is_read in ("true", "1", "yes"):
        q = q.filter(Notification.is_read.is_(True))
    elif is_read in ("false", "0", "no"):
        q = q.filter(Notification.is_read.is_(False))

    total = q.count()
    items = (
        q.order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return _ok({
        "items": [_serialize(n) for n in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.post("/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """标记单条通知为已读。"""
    uid = _user_id_of(current_user)
    tenant_id = tenant_of(current_user)
    try:
        pk = int(notification_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"通知 {notification_id} 不存在",
        )
    n = (
        db.query(Notification)
        .filter(
            Notification.id == pk,
            Notification.tenant_id == tenant_id,
            Notification.user_id == uid,
        )
        .first()
    )
    if not n:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"通知 {notification_id} 不存在",
        )
    if not n.is_read:
        n.is_read = True
        db.commit()
        db.refresh(n)
    return _ok(None, "已标记为已读")


@router.post("/read-all")
def mark_all_read(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """标记当前用户所有未读通知为已读。"""
    uid = _user_id_of(current_user)
    tenant_id = tenant_of(current_user)
    updated = (
        db.query(Notification)
        .filter(
            Notification.tenant_id == tenant_id,
            Notification.user_id == uid,
            Notification.is_read.is_(False),
        )
        .update({Notification.is_read: True})
    )
    db.commit()
    return _ok({"updated_count": int(updated)}, "全部已标记为已读")
