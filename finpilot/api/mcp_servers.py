"""MCP 服务器配置路由 — 管理外部 MCP 服务器连接.

提供 CRUD + 真实的连接测试、工具发现、工具调用与连接生命周期管理。
连接逻辑委托给 McpConnectionManager（真实 MCP 协议实现）。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

# TODO: FinPilot deps 暂未提供 get_current_user_or_api_key（带 API Key + scope 校验），
#       暂用 get_current_user；如需 API Key 鉴权与 scope 校验，需扩展 finpilot.api.deps。
# TODO: FinPilot 暂未引入多租户(tenant_id)概念，user.tenant_id 暂以 user_id 字符串替代。
# TODO: McpServerConfig ORM 模型尚未在 FinPilot 中定义，需后续在 finpilot.database.models 补充。
from finpilot.api.deps import get_current_user, get_db_session
# TODO: McpServerConfig 模型尚未在 finpilot.database.models 中定义，导入会失败，
#       需后续补充该模型（或临时改为内联占位模型）。
from finpilot.database.models import McpServerConfig  # noqa: F401
from finpilot.services.mcp_client import McpConnectionError, mcp_manager, run_async
from finpilot.services.mcp_tool_bridge import (
    register_server_mcp_tools,
    unregister_mcp_tools,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp-servers", tags=["MCP Servers Admin"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class McpServerBase(BaseModel):
    name: str = Field(..., max_length=128, description="服务器名称")
    display_name: str = Field(..., max_length=128, description="展示名称")
    description: str | None = Field(default=None, description="描述")
    transport: str = Field(default="stdio", description="传输方式: stdio/sse/streamable_http")
    command: str | None = Field(default=None, description="stdio 命令")
    args: str | None = Field(default=None, description="命令参数 JSON")
    url: str | None = Field(default=None, description="服务器 URL")
    api_key: str | None = Field(default=None, description="API Key")
    env_vars: dict[str, str] = Field(default_factory=dict, description="环境变量")
    is_active: bool = Field(default=True)
    priority: int = Field(default=0)


class McpServerCreate(McpServerBase):
    pass


class McpServerUpdate(BaseModel):
    display_name: str | None = None
    description: str | None = None
    transport: str | None = None
    command: str | None = None
    args: str | None = None
    url: str | None = None
    api_key: str | None = None
    env_vars: dict[str, str] | None = None
    is_active: bool | None = None
    priority: int | None = None


class McpServerResponse(McpServerBase):
    id: str
    is_builtin: bool
    last_connected_at: str | None
    last_status: str | None

    class Config:
        from_attributes = True


class McpToolInvokeRequest(BaseModel):
    """MCP 工具调用请求体."""

    arguments: dict[str, Any] = Field(default_factory=dict, description="工具参数")


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _model_to_response(mcp: McpServerConfig) -> dict[str, Any]:
    return {
        "id": str(mcp.id),
        "name": mcp.name,
        "display_name": mcp.display_name,
        "description": mcp.description,
        "transport": mcp.transport,
        "command": mcp.command,
        "args": mcp.args,
        "url": mcp.url,
        "env_vars": mcp.env_vars or {},
        "is_active": mcp.is_active,
        "is_builtin": mcp.is_builtin,
        "priority": mcp.priority,
        "last_connected_at": mcp.last_connected_at,
        "last_status": mcp.last_status,
    }


def _get_owned_mcp(
    mcp_id: str, tenant_id: str, db: Session
) -> McpServerConfig:
    """加载并校验当前租户的 MCP 服务器配置."""
    mcp = (
        db.query(McpServerConfig)
        .filter(
            McpServerConfig.id == mcp_id,
            McpServerConfig.tenant_id == tenant_id,
        )
        .first()
    )
    if not mcp:
        raise HTTPException(status_code=404, detail="服务器不存在")
    return mcp


def _auto_connect(mcp: McpServerConfig, db: Session) -> None:
    """若服务器启用，则尝试连接并注册其工具（best-effort，失败不阻塞主流程）."""
    if not mcp.is_active:
        return
    try:
        run_async(mcp_manager.get_or_connect(str(mcp.id), db, force=True), timeout=30.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("mcp_auto_connect_failed server=%s error=%s", mcp.name, exc)
        return
    try:
        register_server_mcp_tools(str(mcp.id), db)
    except Exception as exc:  # noqa: BLE001
        logger.warning("mcp_auto_register_failed server=%s error=%s", mcp.name, exc)


def _safe_disconnect(mcp_id: str) -> None:
    """断开连接池中的连接（best-effort）."""
    try:
        run_async(mcp_manager.disconnect_server(mcp_id), timeout=10.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("mcp_safe_disconnect_failed server_id=%s error=%s", mcp_id, exc)


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------


@router.get("")
def list_mcp_servers(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    active_only: bool = Query(default=False, description="仅返回激活的"),
) -> dict[str, Any]:
    """获取 MCP 服务器列表."""
    tenant_id = str(current_user.get("user_id", "default"))
    query = db.query(McpServerConfig).filter(McpServerConfig.tenant_id == tenant_id)
    if active_only:
        query = query.filter(McpServerConfig.is_active.is_(True))
    items = query.order_by(McpServerConfig.priority, McpServerConfig.created_at).all()
    pool_status = mcp_manager.get_status()
    data = []
    for m in items:
        item = _model_to_response(m)
        item["connected"] = pool_status.get(str(m.id), {}).get("connected", False)
        data.append(item)
    return {
        "code": 0,
        "message": "ok",
        "data": data,
    }


@router.get("/transports")
def list_transports(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """获取支持的传输方式列表."""
    return {
        "code": 0,
        "message": "ok",
        "data": [
            {"value": "stdio", "label": "Stdio（本地进程）"},
            {"value": "sse", "label": "SSE（Server-Sent Events）"},
            {"value": "streamable_http", "label": "Streamable HTTP"},
        ],
    }


@router.get("/status")
def mcp_connection_status(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """获取所有 MCP 服务器的连接状态总览."""
    tenant_id = str(current_user.get("user_id", "default"))
    servers = (
        db.query(McpServerConfig)
        .filter(McpServerConfig.tenant_id == tenant_id)
        .order_by(McpServerConfig.priority, McpServerConfig.created_at)
        .all()
    )
    pool_status = mcp_manager.get_status()
    data = []
    connected_count = 0
    for s in servers:
        sid = str(s.id)
        conn = pool_status.get(sid, {})
        connected = bool(conn.get("connected", False))
        if connected:
            connected_count += 1
        data.append(
            {
                "id": sid,
                "name": s.name,
                "transport": s.transport,
                "is_active": s.is_active,
                "connected": connected,
                "connected_at": conn.get("connected_at"),
                "last_status": s.last_status,
                "last_connected_at": s.last_connected_at,
            }
        )
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "total": len(data),
            "connected_count": connected_count,
            "servers": data,
        },
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.post("", status_code=status.HTTP_201_CREATED)
def create_mcp_server(
    body: McpServerCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """创建 MCP 服务器配置（若启用则自动连接并注册工具）."""
    tenant_id = str(current_user.get("user_id", "default"))
    existing = (
        db.query(McpServerConfig)
        .filter(
            McpServerConfig.tenant_id == tenant_id,
            McpServerConfig.name == body.name,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="服务器名称已存在")

    mcp = McpServerConfig(
        tenant_id=tenant_id,
        name=body.name,
        display_name=body.display_name,
        description=body.description,
        transport=body.transport,
        command=body.command,
        args=body.args,
        url=body.url,
        api_key=body.api_key,
        env_vars=body.env_vars,
        is_active=body.is_active,
        priority=body.priority,
        last_status="untested",
    )
    db.add(mcp)
    db.commit()
    db.refresh(mcp)

    # 启用则自动连接
    _auto_connect(mcp, db)
    db.refresh(mcp)
    return {"code": 0, "message": "ok", "data": _model_to_response(mcp)}


@router.put("/{mcp_id}")
def update_mcp_server(
    mcp_id: str,
    body: McpServerUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """更新 MCP 服务器配置（配置变更后重连）."""
    tenant_id = str(current_user.get("user_id", "default"))
    mcp = _get_owned_mcp(mcp_id, tenant_id, db)

    update_data = body.model_dump(exclude_unset=True)
    for key, val in update_data.items():
        setattr(mcp, key, val)

    # 配置可能已变更，断开旧连接并卸载旧工具
    _safe_disconnect(str(mcp.id))
    unregister_mcp_tools(str(mcp.id))

    db.commit()
    db.refresh(mcp)

    # 重新启用则自动连接
    _auto_connect(mcp, db)
    db.refresh(mcp)
    return {"code": 0, "message": "ok", "data": _model_to_response(mcp)}


@router.delete("/{mcp_id}")
def delete_mcp_server(
    mcp_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """删除 MCP 服务器配置（先断开连接并卸载工具）."""
    tenant_id = str(current_user.get("user_id", "default"))
    mcp = _get_owned_mcp(mcp_id, tenant_id, db)
    if mcp.is_builtin:
        raise HTTPException(status_code=400, detail="内置服务器不可删除")

    _safe_disconnect(str(mcp.id))
    unregister_mcp_tools(str(mcp.id))

    db.delete(mcp)
    db.commit()
    return {"code": 0, "message": "ok", "data": None}


@router.patch("/{mcp_id}/toggle")
def toggle_mcp_server(
    mcp_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """启用/禁用 MCP 服务器."""
    tenant_id = str(current_user.get("user_id", "default"))
    mcp = _get_owned_mcp(mcp_id, tenant_id, db)

    mcp.is_active = not mcp.is_active
    if not mcp.is_active:
        # 禁用：断开连接并卸载工具
        _safe_disconnect(str(mcp.id))
        unregister_mcp_tools(str(mcp.id))
    db.commit()
    db.refresh(mcp)

    if mcp.is_active:
        _auto_connect(mcp, db)
        db.refresh(mcp)
    return {"code": 0, "message": "ok", "data": _model_to_response(mcp)}


# ---------------------------------------------------------------------------
# 连接测试 / 工具发现
# ---------------------------------------------------------------------------


@router.post("/{mcp_id}/test")
def test_mcp_server(
    mcp_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """测试 MCP 服务器连接（真实握手）."""
    tenant_id = str(current_user.get("user_id", "default"))
    mcp = _get_owned_mcp(mcp_id, tenant_id, db)

    try:
        result = run_async(
            mcp_manager.health_check(str(mcp.id), db), timeout=60.0
        )
    except Exception as exc:  # noqa: BLE001
        mcp.last_status = "error"
        db.commit()
        return {"code": 1, "message": f"连接失败: {exc!s}", "data": None}

    db.refresh(mcp)
    reachable = bool(result.get("reachable"))
    return {
        "code": 0 if reachable else 1,
        "message": "ok" if reachable else f"连接失败: {result.get('error', '')}",
        "data": {
            "status": "connected" if reachable else "error",
            "reachable": reachable,
            "name": mcp.name,
            "transport": mcp.transport,
            "last_status": mcp.last_status,
            "last_connected_at": mcp.last_connected_at,
            "error": result.get("error"),
            "server_info": result.get("server_info"),
        },
    }


@router.get("/{mcp_id}/tools")
def list_mcp_tools(
    mcp_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """获取 MCP 服务器暴露的工具列表（真实连接后获取）."""
    tenant_id = str(current_user.get("user_id", "default"))
    mcp = _get_owned_mcp(mcp_id, tenant_id, db)

    try:
        tools = run_async(
            mcp_manager.list_server_tools(str(mcp.id), db, force=True), timeout=60.0
        )
    except McpConnectionError as exc:
        return {
            "code": 1,
            "message": f"无法连接服务器: {exc!s}",
            "data": {"server_name": mcp.name, "tools": [], "count": 0},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "code": 1,
            "message": f"获取工具列表失败: {exc!s}",
            "data": {"server_name": mcp.name, "tools": [], "count": 0},
        }

    tool_list = [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_schema,
        }
        for t in tools
    ]
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "server_name": mcp.name,
            "tools": tool_list,
            "count": len(tool_list),
        },
    }


# ---------------------------------------------------------------------------
# 连接生命周期
# ---------------------------------------------------------------------------


@router.post("/{mcp_id}/connect")
def connect_mcp_server(
    mcp_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """显式连接 MCP 服务器并注册其工具."""
    tenant_id = str(current_user.get("user_id", "default"))
    mcp = _get_owned_mcp(mcp_id, tenant_id, db)

    try:
        run_async(mcp_manager.get_or_connect(str(mcp.id), db, force=True), timeout=60.0)
    except Exception as exc:  # noqa: BLE001
        db.refresh(mcp)
        return {
            "code": 1,
            "message": f"连接失败: {exc!s}",
            "data": {"connected": False, "server_name": mcp.name},
        }

    _server_name, count = register_server_mcp_tools(str(mcp.id), db)
    db.refresh(mcp)
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "connected": True,
            "server_name": mcp.name,
            "tools_registered": count,
            "last_status": mcp.last_status,
        },
    }


@router.post("/{mcp_id}/disconnect")
def disconnect_mcp_server(
    mcp_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """断开 MCP 服务器连接并卸载其工具."""
    tenant_id = str(current_user.get("user_id", "default"))
    mcp = _get_owned_mcp(mcp_id, tenant_id, db)

    _safe_disconnect(str(mcp.id))
    removed = unregister_mcp_tools(str(mcp.id))

    try:
        mcp.last_status = "disconnected"
        db.commit()
        db.refresh(mcp)
    except Exception as exc:  # noqa: BLE001
        logger.warning("mcp_disconnect_status_update_failed error=%s", exc)

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "disconnected": True,
            "server_name": mcp.name,
            "tools_unregistered": removed,
        },
    }


@router.post("/{mcp_id}/tools/{tool_name}/invoke")
def invoke_mcp_tool(
    mcp_id: str,
    tool_name: str,
    body: McpToolInvokeRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """调用指定 MCP 服务器的指定工具."""
    tenant_id = str(current_user.get("user_id", "default"))
    mcp = _get_owned_mcp(mcp_id, tenant_id, db)

    try:
        result = run_async(
            mcp_manager.call_tool(str(mcp.id), tool_name, body.arguments, db),
            timeout=120.0,
        )
    except McpConnectionError as exc:
        return {
            "code": 1,
            "message": f"无法连接服务器: {exc!s}",
            "data": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "code": 1,
            "message": f"工具调用失败: {exc!s}",
            "data": None,
        }

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "server_name": mcp.name,
            "tool_name": tool_name,
            "result": result,
        },
    }
