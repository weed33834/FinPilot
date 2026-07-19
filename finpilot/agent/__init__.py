"""FinPilot 智能体运行时 - 基于 LangGraph 的 ReAct 编排层。

提供工具注册、多步推理（Thought/Action/Observation）、会话持久化与 LLM 不可用降级。
导入本包即自动注册内置工具（nl2sql / document_qa / parse_document）。
"""
from __future__ import annotations

from . import tools as _tools  # noqa: F401  触发内置工具注册
from .graph import build_agent, make_thread_id, run_agent
from .tool_registry import ToolContext, ToolRegistry, ToolSpec, tool_registry

__all__ = [
    "run_agent",
    "build_agent",
    "make_thread_id",
    "ToolRegistry",
    "ToolContext",
    "ToolSpec",
    "tool_registry",
]
