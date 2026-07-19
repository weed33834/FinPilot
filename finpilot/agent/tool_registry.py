"""工具注册机制 - 工具规格、上下文与注册中心。

用法::

    from finpilot.agent.tool_registry import tool_registry

    @tool_registry.register(
        name="my_tool",
        description="做什么的工具",
        parameters_schema={"question": "str,必填,问题"},
        tags=["data"],
    )
    def my_tool(ctx: ToolContext, **kwargs) -> dict:
        ...

导入 :mod:`finpilot.agent.tools` 即可完成内置工具的注册。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class ToolContext:
    """工具运行时上下文 - 由执行节点构造并传入工具函数。

    携带租户/用户/数据库/会话/历史等运行时信息，工具据此做数据隔离与上下文检索。
    """

    tenant_id: str = "default"
    user_id: Optional[str] = None
    db: Any = None
    conversation_id: Optional[str] = None
    history: Optional[list] = None


@dataclass
class ToolSpec:
    """工具规格 - 名称、描述、参数 schema、可调用实现与标签。"""

    name: str
    description: str
    parameters_schema: dict[str, str]
    func: Callable[..., dict]
    tags: list[str] = field(default_factory=list)


class ToolRegistry:
    """工具注册中心 - 支持装饰器注册与按名查询。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters_schema: dict[str, str],
        tags: Optional[list[str]] = None,
    ) -> Callable[[Callable[..., dict]], Callable[..., dict]]:
        """装饰器：将函数注册为工具。"""

        def decorator(func: Callable[..., dict]) -> Callable[..., dict]:
            self._tools[name] = ToolSpec(
                name=name,
                description=description,
                parameters_schema=parameters_schema,
                func=func,
                tags=list(tags) if tags else [],
            )
            return func

        return decorator

    def get(self, name: str) -> Optional[ToolSpec]:
        """按名获取工具规格，不存在返回 None。"""
        return self._tools.get(name)

    def all(self) -> list[ToolSpec]:
        """返回全部已注册工具。"""
        return list(self._tools.values())

    def names(self) -> list[str]:
        """返回全部工具名。"""
        return list(self._tools.keys())

    def build_description(self, tools: Optional[list[ToolSpec]] = None) -> str:
        """生成供 ReAct prompt 使用的工具描述文本。

        每行一个工具：``- name(param: 说明): description``。
        """
        if tools is None:
            tools = self.all()
        lines: list[str] = []
        for spec in tools:
            params = ", ".join(
                f"{k}: {v}" for k, v in spec.parameters_schema.items()
            )
            lines.append(f"- {spec.name}({params}): {spec.description}")
        return "\n".join(lines)


# 全局单例：内置工具与租户自定义工具均注册于此
tool_registry = ToolRegistry()
