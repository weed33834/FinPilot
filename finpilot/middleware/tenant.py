"""多租户中间件 — 从请求头 X-Tenant-ID 或用户会话中提取租户 ID，存入 ContextVar。

所有含 tenant_id 字段的 ORM 模型在查询时自动按当前租户过滤（通过 tenant_filter
安装的 SQLAlchemy do_orm_execute 事件实现）。
"""
from __future__ import annotations

from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

current_tenant_id: ContextVar[str | None] = ContextVar("tenant_id", default=None)


class TenantMiddleware(BaseHTTPMiddleware):
    """Starlette 中间件：从请求中提取 tenant_id 并存入 ContextVar。

    优先级：
    1. 请求头 ``X-Tenant-ID``
    2. ``request.state.user`` 中的 ``tenant_id`` 字段
    3. 以上均无 → ContextVar 保持 None（全局查询）
    """

    async def dispatch(self, request: Request, call_next):
        token = request.headers.get("X-Tenant-ID")
        if not token and hasattr(request.state, "user"):
            token = request.state.user.get("tenant_id")
        if token:
            current_tenant_id.set(token)
        try:
            response = await call_next(request)
            return response
        finally:
            # finally 确保异常时也清理 ContextVar，防止 ASGI 任务复用导致跨租户数据泄漏
            current_tenant_id.set(None)
