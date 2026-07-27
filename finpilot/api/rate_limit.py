# -*- coding: utf-8 -*-
"""共享限流器 — 供全项目统一使用，Redis 不可用时自动降级为内存模式。

用法::

    from finpilot.api.rate_limit import limiter, get_user_key

    @router.post("/login")
    @limiter.limit("5/minute")
    async def login(...): ...

    @router.post("/agent/chat")
    @limiter.limit("20/minute", key_func=get_user_key)
    async def chat(...): ...
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

from finpilot.core.config import settings
from finpilot.core.logging import get_logger

logger = get_logger(__name__)

# ── 共享 Limiter 实例 ──
try:
    limiter = Limiter(
        key_func=get_remote_address,
        storage_uri=settings.redis_url,
        default_limits=["100/minute"],
        application_limits=["100/minute"],
        headers_enabled=True,
    )
    logger.info("slowapi Limiter 已连接 Redis: %s", settings.redis_url)
except Exception:
    logger.warning("slowapi Limiter 无法连接 Redis，降级为内存模式（进程重启后重置）")
    limiter = Limiter(
        key_func=get_remote_address,
        storage_uri="memory://",
        default_limits=["100/minute"],
        application_limits=["100/minute"],
        headers_enabled=True,
    )


def get_user_key(request: Request) -> str:
    """基于用户身份的限流 key 函数。

    优先从 session cookie 提取 session_id 作为用户标识；
    未登录时回退到 IP 地址。
    """
    session_id = request.cookies.get("session_id")
    if session_id:
        return f"user:{session_id}"
    return get_remote_address(request)
