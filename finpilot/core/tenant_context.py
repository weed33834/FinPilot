"""租户上下文管理 — 基于 ContextVar 的请求级租户隔离.

订阅调度器 / 执行器在多租户场景下需要为每段 DB 写入显式声明租户上下文，
让行级安全（RLS）策略按当前租户过滤。FinPilot 内核默认走 SQLite（无 RLS），
本模块提供 ``ContextVar`` 持有当前租户 ID，作为统一接入点：

- ``set_tenant_session(db, tenant_id)``：设置当前上下文租户。
  ``db`` 参数为兼容 PostgreSQL RLS GUC（``SET LOCAL app.tenant_id``）预留，
  SQLite 方言下安全 no-op（与 subscription_scheduler / runner 既有注释一致）。
- ``get_tenant_session()``：读取当前上下文租户 ID（未设置返回 None）。
- ``reset_tenant_session()``：清空当前上下文租户，避免跨任务泄漏。

ContextVar 天然按 asyncio task / 线程上下文隔离，调度器后台线程逐次
``SessionLocal()`` 调用时不会串租户。
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 当前租户上下文：未设置时为 None
_tenant_session: ContextVar[Optional[str]] = ContextVar(
    "finpilot_tenant_session", default=None
)


def set_tenant_session(db: Any, tenant_id: str | None) -> None:
    """设置当前上下文的租户 ID.

    Args:
        db: SQLAlchemy Session。为 PostgreSQL RLS GUC 预留；
            SQLite / 缺失方言上 no-op，仅记录 ContextVar。
        tenant_id: 租户 ID；传入 None 等价于 reset。
    """
    # PostgreSQL 场景：通过会话级 GUC 让 RLS 策略识别当前租户。
    # SQLite 等不支持 RLS 的方言静默降级（不阻断主流程）。
    if tenant_id is not None and db is not None:
        try:
            from sqlalchemy import text

            dialect_name = ""
            bind = getattr(db, "bind", None)
            if bind is not None:
                dia = getattr(bind, "dialect", None)
                dialect_name = getattr(dia, "name", "") or ""
            if dialect_name.startswith("postgresql"):
                # 参数化绑定，避免 SQL 注入
                db.execute(
                    text("SELECT set_config('app.tenant_id', :tid, true)"),
                    {"tid": str(tenant_id)},
                )
        except Exception:  # noqa: BLE001
            # GUC 设置失败不阻断主流程，仅依赖 ContextVar
            logger.debug("set_tenant_session_guc_failed tenant_id=%s", tenant_id)

    _tenant_session.set(str(tenant_id) if tenant_id is not None else None)


def get_tenant_session() -> str | None:
    """读取当前上下文租户 ID（未设置返回 None）."""
    return _tenant_session.get()


def reset_tenant_session() -> None:
    """清空当前上下文租户，避免跨任务泄漏."""
    _tenant_session.set(None)
