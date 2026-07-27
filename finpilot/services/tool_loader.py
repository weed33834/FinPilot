"""工具加载器 — 从 DB tools 表读取工具并动态注册到 tool_registry.

将管理后台配置的自定义工具接入 Agent 运行时工具注册表。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from finpilot.agent.tool_registry import ToolContext, ToolSpec, tool_registry
from finpilot.database.models import Tool

logger = logging.getLogger(__name__)

# 记录已注册的 DB 工具名，用于增量更新
_registered_names: set[str] = set()


def reload_db_tools(tenant_id: str, db: Session) -> None:
    """从数据库 tools 表加载激活的工具并注册到 tool_registry.

    只会加载 type 为 'python_function' 的自定义工具（is_builtin=False）。
    工具函数通过 exec 动态编译并注册。

    Args:
        tenant_id: 租户 ID，用于数据隔离
        db: 数据库会话
    """
    global _registered_names

    tools = (
        db.query(Tool)
        .filter(
            Tool.tenant_id == tenant_id,
            Tool.is_active.is_(True),
            Tool.is_builtin.is_(False),
            Tool.type == "python_function",
        )
        .all()
    )

    new_names: set[str] = set()

    for tool in tools:
        config = tool.config or {}
        code = config.get("code", "")
        entry_function = config.get("entry_function", "run")

        if not code:
            logger.warning("tool_loader: tool %s has no code, skipping", tool.name)
            continue

        try:
            # 动态编译工具函数
            namespace: dict[str, Any] = {
                "ToolContext": ToolContext,
                "json": json,
                "__builtins__": __builtins__,
            }
            exec(compile(code, f"<tool:{tool.name}>", "exec"), namespace)

            func = namespace.get(entry_function)
            if func is None:
                logger.warning(
                    "tool_loader: entry function '%s' not found in tool %s",
                    entry_function,
                    tool.name,
                )
                continue

            spec = ToolSpec(
                name=tool.name,
                description=tool.description or tool.display_name,
                parameters_schema=config.get("parameters_schema", {}),
                func=func,
                tags=["db_tool", tool.type],
            )

            tool_registry._tools[tool.name] = spec
            new_names.add(tool.name)
            logger.info("tool_loader: registered tool '%s' from DB", tool.name)

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "tool_loader: failed to compile/register tool '%s': %s",
                tool.name,
                exc,
            )

    # 清理已从 DB 中删除的工具
    stale = _registered_names - new_names
    for name in stale:
        tool_registry._tools.pop(name, None)
        logger.info("tool_loader: unregistered stale tool '%s'", name)

    _registered_names = new_names
