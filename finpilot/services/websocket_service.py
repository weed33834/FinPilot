"""WebSocket 实时推送 — 报告状态变更、HITL 请求、订阅完成通知."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])


class ConnectionManager:
    """WebSocket 连接管理器 — 按 tenant_id 分组管理连接."""

    def __init__(self) -> None:
        # tenant_id → set of WebSocket connections
        self._connections: dict[str, set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, tenant_id: str) -> None:
        """接受新连接并加入租户分组."""
        await websocket.accept()
        if tenant_id not in self._connections:
            self._connections[tenant_id] = set()
        self._connections[tenant_id].add(websocket)
        logger.info("ws_connected", tenant_id=tenant_id, total=len(self._connections[tenant_id]))

    def disconnect(self, websocket: WebSocket, tenant_id: str) -> None:
        """移除断开的连接."""
        if tenant_id in self._connections:
            self._connections[tenant_id].discard(websocket)
            if not self._connections[tenant_id]:
                del self._connections[tenant_id]

    async def send_to_tenant(self, tenant_id: str, message: dict[str, Any]) -> None:
        """向指定租户的所有连接推送消息."""
        if tenant_id not in self._connections:
            return

        dead: list[WebSocket] = []
        for ws in self._connections[tenant_id]:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(json.dumps(message, ensure_ascii=False, default=str))
            except Exception as exc:  # noqa: BLE001
                logger.warning("ws_send_failed", error=str(exc))
                dead.append(ws)

        for ws in dead:
            self._connections[tenant_id].discard(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        """向所有连接广播消息."""
        for tenant_id in list(self._connections.keys()):
            await self.send_to_tenant(tenant_id, message)


# 全局单例
manager = ConnectionManager()


def push_event(
    tenant_id: str,
    event_type: str,
    data: dict[str, Any],
) -> None:
    """推送事件到指定租户的 WebSocket 连接（同步接口，内部异步）.

    Args:
        tenant_id: 租户 ID
        event_type: 事件类型 (report.status_changed / hitl.created / subscription.completed)
        data: 事件数据

    推送的事件格式：
    {
        "type": "report.status_changed",
        "data": {...},
        "timestamp": "2026-07-15T10:30:00"
    }
    """
    message = {
        "type": event_type,
        "data": data,
        "timestamp": datetime.now().isoformat(),
    }
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(manager.send_to_tenant(tenant_id, message))
        else:
            loop.run_until_complete(manager.send_to_tenant(tenant_id, message))
    except RuntimeError:
        # 没有 event loop，创建新的
        asyncio.run(manager.send_to_tenant(tenant_id, message))


@router.websocket("/ws/notifications")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket 端点 — 客户端连接后接收实时推送.

    连接时通过 query 参数传递 token，服务端解析租户 ID。
    """
    # 从 query 参数获取认证信息
    token = websocket.query_params.get("token", "")
    tenant_id = websocket.query_params.get("tenant_id", "")

    # TODO: 从 token 验证用户身份和租户
    if not tenant_id:
        await websocket.close(code=4001, reason="缺少 tenant_id 参数")
        return

    await manager.connect(websocket, tenant_id)
    try:
        while True:
            # 保持连接，等待客户端心跳
            data = await websocket.receive_text()
            # 处理心跳
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket, tenant_id)
        logger.info("ws_disconnected", tenant_id=tenant_id)
