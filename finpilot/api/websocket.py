# -*- coding: utf-8 -*-
"""``/ws/notifications`` —— WebSocket 实时通知推送端点。

前端 ``useWebSocket.ts`` 连接 ``/ws/notifications`` 接收实时通知，并通过 query
参数 ``tenant_id`` 标识租户。鉴权通过 HttpOnly cookie ``session_id``（浏览器同源
自动携带）或 query 参数 ``session_id``（curl / 调试用）完成，未认证连接立即关闭。

消息格式（与前端 ``WebSocketMessage`` 接口对齐）::

    {"type": "notification", "data": Notification, "timestamp": "ISO8601"}

心跳：客户端发送文本 "ping"，服务端回复 "pong"。

``ConnectionManager`` 为模块级单例，业务模块通过 ``manager.send_to_user_sync``
（sync 调用方）或 ``manager.send_to_user``（async 调用方）推送消息；跨线程投递由
sync 包装器内部用 ``run_coroutine_threadsafe`` 处理。

路由挂载：本 ``router`` 不带 prefix，由 ``finpilot/api/router.py`` 在 ``app`` 上
直接 ``include_router``（不能放进 ``create_router`` 的 ``/api/v1`` 子路由，否则
路径会变成 ``/api/v1/ws/notifications``，与前端契约不符）。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from finpilot.core.session import session_store

from .deps import SESSION_COOKIE

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


def _user_id_from_session(user_data: dict) -> str:
    """与 notifications._user_id_of 一致，统一用 ``user_{id}`` 作为连接分组键。"""
    return f"user_{user_data.get('user_id', 'default')}"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ConnectionManager:
    """按 user_id 分组的 WebSocket 连接管理器（模块级单例）。

    - ``connect`` 由 WebSocket 端点在握手成功后调用，会自动 ``accept()``；
    - ``disconnect`` 由端点在连接断开时调用，清理集合；
    - ``send_to_user`` 异步推送，调用方在 async 上下文使用；
    - ``send_to_user_sync`` 同步包装，供 sync 函数 / 后台线程调用，
      自动选择 ``create_task`` 或 ``run_coroutine_threadsafe``。
    """

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        # 主事件循环引用：WebSocket 端点握手时捕获，供后台线程投递协程
        self._main_loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, user_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.setdefault(user_id, set()).add(ws)
        if self._main_loop is None:
            try:
                self._main_loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

    def disconnect(self, user_id: str, ws: WebSocket) -> None:
        conns = self._connections.get(user_id)
        if not conns:
            return
        conns.discard(ws)
        if not conns:
            self._connections.pop(user_id, None)

    async def send_to_user(self, user_id: str, message: dict[str, Any]) -> None:
        """异步推送消息给指定用户的所有活跃连接（best-effort，失败连接清理）。"""
        conns = list(self._connections.get(user_id, set()))
        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001  连接已断开，下一轮清理
                dead.append(ws)
        for ws in dead:
            self.disconnect(user_id, ws)

    def send_to_user_sync(self, user_id: str, message: dict[str, Any]) -> None:
        """同步推送包装：自动适配 async / 后台线程两种调用场景。

        - 当前线程已在事件循环中（如 async 路由）：``create_task`` fire-and-forget；
        - 当前线程无事件循环（如 BackgroundTasks / 调度器线程）：
          通过主循环 ``run_coroutine_threadsafe`` 投递。
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            loop.create_task(self.send_to_user(user_id, message))
            return

        main_loop = self._main_loop
        if main_loop is None or not main_loop.is_running():
            logger.debug("ws_push_skipped: no running event loop available")
            return
        asyncio.run_coroutine_threadsafe(
            self.send_to_user(user_id, message), main_loop
        )


# 模块级单例
manager = ConnectionManager()


async def _authenticate(ws: WebSocket) -> dict | None:
    """从 cookie 或 query 参数提取 session_id 并校验，返回 user_data 或 None。"""
    session_id = ws.query_params.get("session_id") or ws.cookies.get(SESSION_COOKIE)
    if not session_id:
        return None
    try:
        user_data = await session_store.get(session_id)
    except Exception:  # noqa: BLE001  Redis/SQLite 异常统一拒绝
        return None
    return user_data or None


@router.websocket("/ws/notifications")
async def notifications_ws(ws: WebSocket) -> None:
    """实时通知推送端点。

    鉴权失败立即关闭（code=4401）；握手成功后推送欢迎消息，然后循环接收
    客户端心跳（"ping" → "pong"）直至断开。断开时清理 ``ConnectionManager``。
    """
    user_data = await _authenticate(ws)
    if not user_data:
        await ws.close(code=4401)
        return

    user_id = _user_id_from_session(user_data)
    await manager.connect(user_id, ws)

    welcome = {
        "type": "notification",
        "data": {
            "channel": "system",
            "title": "连接成功",
            "content": f"已订阅 {user_id} 的实时通知",
        },
        "timestamp": _now_iso(),
    }
    try:
        await ws.send_json(welcome)
    except Exception:  # noqa: BLE001
        manager.disconnect(user_id, ws)
        return

    try:
        while True:
            text = await ws.receive_text()
            if text == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.debug("ws_unexpected_close user=%s", user_id)
    finally:
        manager.disconnect(user_id, ws)
