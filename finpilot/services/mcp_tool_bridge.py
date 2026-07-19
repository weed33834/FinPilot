# TODO: requires finpilot.agent.tool_registry —— 注意 FinPilot 的 ToolRegistry.register 为装饰器工厂
#       （签名为 register(name, description, parameters_schema, tags=None)，不接受 ToolSpec 实例），
#       与本模块 tool_registry.register(spec) 调用方式不兼容，后续需适配 register 逻辑或扩展 ToolRegistry API。
"""MCP 工具桥接 — 将 MCP 服务器发现的工具注册到 agent tool_registry.

工作流程:
1. register_mcp_tools(tenant_id, db)
   - 调用 McpConnectionManager.discover_all_tools() 连接所有启用的 MCP 服务器
   - 为每个发现的工具创建 ToolSpec 包装器，注册到全局 tool_registry
   - 工具调用时通过 McpConnectionManager.call_tool() 路由到对应服务器
   - MCP input_schema 直接映射为 tool_registry 的 parameters_schema（同为 JSON Schema）
2. unregister_mcp_tools(server_id)
   - 移除指定服务器的所有已注册工具

命名约定: 注册的工具名为 ``mcp_{server_name}_{tool_name}``，
带 ``mcp`` 与 server_name 标签，便于区分内置/自定义工具。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from finpilot.agent.tool_registry import ToolContext, ToolSpec, tool_registry
from finpilot.services.mcp_client import McpConnectionManager, mcp_manager, run_async

logger = logging.getLogger(__name__)

# 已注册的 MCP 工具，按 server_id 分组：{server_id: {tool_name_in_registry, ...}}
_registered_mcp_tools: dict[str, set[str]] = {}

# 工具名中非法字符的正则（只保留字母、数字、下划线）
_INVALID_NAME_CHARS = re.compile(r"[^a-zA-Z0-9_]+")


def _sanitize_name(name: str) -> str:
    """将任意字符串规整为合法的工具名片段（字母/数字/下划线）."""
    cleaned = _INVALID_NAME_CHARS.sub("_", name).strip("_")
    return cleaned or "tool"


def _build_tool_name(server_name: str, tool_name: str) -> str:
    """构造注册到 tool_registry 的工具全名."""
    return f"mcp_{_sanitize_name(server_name)}_{_sanitize_name(tool_name)}"


def _map_input_schema(input_schema: dict[str, Any] | None) -> dict[str, Any]:
    """将 MCP inputSchema 映射为 tool_registry parameters_schema.

    两者均为 JSON Schema，结构一致（type/properties/required），
    这里做一次规范化，确保至少是 object 类型。
    """
    if not isinstance(input_schema, dict) or not input_schema:
        return {"type": "object", "properties": {}, "required": []}
    schema = dict(input_schema)
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})
    schema.setdefault("required", [])
    return schema


def _make_mcp_tool_func(
    server_id: str, tool_name: str, param_names: set[str]
) -> Any:
    """为单个 MCP 工具创建同步执行函数.

    执行时通过 run_async() 在后台事件循环中调用 McpConnectionManager.call_tool()，
    实现 async -> sync 转换。仅传入 schema 中声明的参数。
    """

    def execute(ctx: ToolContext, **kwargs: Any) -> dict[str, Any]:
        # 过滤掉 None 值与不在 schema 中的多余参数（question 等元参数）
        arguments: dict[str, Any] = {}
        for key, val in kwargs.items():
            if val is None:
                continue
            if param_names and key not in param_names:
                continue
            arguments[key] = val
        try:
            result = run_async(
                mcp_manager.call_tool(server_id, tool_name, arguments, ctx.db),
                timeout=120.0,
            )
            return result
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "mcp_tool_invoke_failed",
                server_id=server_id,
                tool=tool_name,
                error=str(exc),
            )
            return {"error": f"MCP 工具调用失败: {exc}"}

    return execute


def _register_one_server(
    server_id: str, server_name: str, tools: list[Any]
) -> int:
    """为单个服务器的工具列表执行注册，返回新注册数量."""
    names: set[str] = set()
    count = 0
    for tool in tools:
        if not tool.name:
            continue
        registry_name = _build_tool_name(server_name, tool.name)
        # 已注册则跳过（避免重复）
        if registry_name in _registered_mcp_tools.get(server_id, set()):
            names.add(registry_name)
            continue
        if tool_registry.get(registry_name) is not None:
            names.add(registry_name)
            continue

        schema = _map_input_schema(tool.input_schema)
        param_names = set((schema.get("properties") or {}).keys())
        try:
            spec = ToolSpec(
                name=registry_name,
                description=tool.description or f"MCP 工具 {tool.name}",
                parameters_schema=schema,
                func=_make_mcp_tool_func(server_id, tool.name, param_names),
                tags=["mcp", _sanitize_name(server_name)],
            )
            tool_registry.register(spec)
            names.add(registry_name)
            count += 1
            logger.info(
                "registered_mcp_tool",
                server=server_name,
                tool=tool.name,
                registry_name=registry_name,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "register_mcp_tool_failed",
                server=server_name,
                tool=tool.name,
                error=str(exc),
            )
    # 合并已注册集合（保留其它已注册工具名）
    existing = _registered_mcp_tools.get(server_id, set())
    _registered_mcp_tools[server_id] = existing | names
    return count


def register_server_mcp_tools(
    server_id: str,
    db: Session,
    manager: McpConnectionManager | None = None,
) -> tuple[str, int]:
    """连接单个 MCP 服务器并注册其工具.

    Returns:
        (server_name, registered_count)
    """
    mgr = manager or mcp_manager
    try:
        tools = run_async(mgr.list_server_tools(server_id, db), timeout=120.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("register_server_mcp_tools_failed", server_id=server_id, error=str(exc))
        return "", 0
    # 取 server_name：从连接池中的 client 配置读取
    server_name = ""
    client = mgr._connections.get(server_id)  # noqa: SLF001
    if client is not None:
        server_name = client.config.name
    return server_name, _register_one_server(server_id, server_name, tools)


def register_mcp_tools(
    tenant_id: str,
    db: Session,
    manager: McpConnectionManager | None = None,
) -> int:
    """发现并注册租户下所有 MCP 服务器的工具到 tool_registry.

    Args:
        tenant_id: 租户 ID。
        db: 数据库会话。
        manager: 可选的连接管理器（默认使用模块单例）。

    Returns:
        本次新注册的工具数量。
    """
    mgr = manager or mcp_manager
    try:
        discovered = run_async(mgr.discover_all_tools(tenant_id, db), timeout=120.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("register_mcp_tools_discover_failed", error=str(exc))
        return 0

    count = 0
    for server_id, server_name, tools in discovered:
        count += _register_one_server(server_id, server_name, tools)
    return count


def unregister_mcp_tools(server_id: str) -> int:
    """移除指定服务器注册到 tool_registry 的所有工具.

    Returns:
        移除的工具数量。
    """
    names = _registered_mcp_tools.pop(server_id, set())
    removed = 0
    for name in names:
        if tool_registry._tools.pop(name, None) is not None:  # noqa: SLF001
            removed += 1
    if removed:
        logger.info("unregistered_mcp_tools", server_id=server_id, count=removed)
    return removed


def unregister_all_mcp_tools() -> int:
    """移除所有已注册的 MCP 工具."""
    server_ids = list(_registered_mcp_tools.keys())
    total = 0
    for sid in server_ids:
        total += unregister_mcp_tools(sid)
    return total


def get_registered_mcp_servers() -> dict[str, set[str]]:
    """返回已注册 MCP 工具的服务器映射（server_id -> 工具名集合）."""
    return {sid: set(names) for sid, names in _registered_mcp_tools.items()}
