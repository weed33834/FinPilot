"""审计服务适配层 —— 为订阅/模板等业务模块提供 ``log_action`` 入口.

FinPilot 内核已有 ``finpilot.security.audit.record_event``，但其签名为
``record_event(action, *, detail, status, tenant_id, user_id, meta)``，自行开
Session，不接受 db/resource/user/commit 等参数。

历史代码（subscription_crud / subscription_runner 等）按
``log_action(db, action, resource, user, reason=None, commit=False)`` 调用，本
模块作为薄适配层把这些参数映射到 ``record_event``：

- ``resource`` + ``reason`` 合并写入 ``detail``；
- ``user`` 支持 dict / User ORM / None，统一抽出 user_id/tenant_id；
- ``commit`` 仅控制是否由本函数 ``db.commit()``。审计写入本身是 best-effort，
  任何失败都被吞掉，绝不阻断主业务流程（与 ``record_event`` 语义一致）。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _extract_user_info(user: Any) -> tuple[str | None, str | None]:
    """从 user 参数中提取 (user_id, tenant_id)，兼容 dict / ORM / None."""
    if user is None:
        return None, None
    if isinstance(user, dict):
        uid = user.get("user_id") or user.get("id")
        tid = user.get("tenant_id") or (f"user_{uid}" if uid is not None else None)
        return str(uid) if uid is not None else None, tid
    # ORM 对象：尝试常见属性
    uid = getattr(user, "id", None)
    tid = getattr(user, "tenant_id", None)
    if tid is None and uid is not None:
        tid = f"user_{uid}"
    return str(uid) if uid is not None else None, tid


def log_action(
    db: Session,
    *,
    action: str,
    resource: str | None = None,
    user: Any = None,
    reason: str | None = None,
    commit: bool = False,
) -> None:
    """记录一条审计日志（best-effort，永不抛错）.

    Args:
        db: 当前请求/事务的 SQLAlchemy Session；仅用于 ``commit`` 参数，
            审计落库由 ``record_event`` 自行开 Session 完成。
        action: 事件类型，如 ``report_subscription.create``.
        resource: 受影响的资源 URI，如 ``report_subscription://42``.
        user: 触发者，可为 dict / User ORM / None.
        reason: 附带说明（如 ``subscription=42``）.
        commit: 是否在记录后 ``db.commit()`` 当前事务.
    """
    try:
        from finpilot.security.audit import record_event

        user_id, tenant_id = _extract_user_info(user)
        parts: list[str] = []
        if resource:
            parts.append(f"resource={resource}")
        if reason:
            parts.append(f"reason={reason}")
        detail = "; ".join(parts) if parts else None

        record_event(
            action,
            detail=detail,
            status="ok",
            tenant_id=tenant_id,
            user_id=user_id,
        )
    except Exception as exc:  # noqa: BLE001
        # 审计失败不能阻断主业务，降级为本地日志
        logger.warning("audit_log_action_failed action=%s err=%s", action, exc)

    if commit:
        try:
            db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("audit_log_action_commit_failed action=%s err=%s", action, exc)


__all__ = ["log_action"]
