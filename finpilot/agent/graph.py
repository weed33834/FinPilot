"""LangGraph 图构建 - ReAct 智能体的编译与运行入口。

图结构::

    START → agent → [should_continue] ─ tools → agent (循环)
                           └─ end → finalize → END

- ``build_agent`` 用闭包把 db/tenant_id/user_id 注入节点，返回带 MemorySaver 的编译图。
- ``run_agent`` 完成意图识别 → 参数抽取 → 图执行 → 结果归一化。
- 会话持久化第一版用进程内 MemorySaver 单例，按 thread_id 复用。
"""
from __future__ import annotations

import uuid
from typing import Any

from langgraph.graph import END, START, StateGraph

from finpilot.llm.intent import classify_intent, extract_parameters

from . import tools as _tools  # noqa: F401  导入即触发内置工具注册
from .checkpoint import get_checkpointer
from .react_nodes import (
    react_agent_node,
    react_finalize_node,
    react_tool_executor_node,
    should_continue,
)
from .state import AgentState

# 会话检查点：默认进程内 MemorySaver（行为不变），可经环境变量
# FINPILOT_CHECKPOINT_BACKEND=sqlite 升级为落盘持久化（重启不丢会话）。
_memory_saver = get_checkpointer()


def build_agent(
    tenant_id: str = "default",
    user_id: str | None = None,
    db: Any = None,
) -> Any:
    """构建 ReAct 智能体编译图。

    通过闭包将 db/tenant_id/user_id 注入 agent 与 tools 节点。
    条件边 should_continue 返回 "tools" 或 "end"（"end" 路由到 finalize 终止节点）。
    """
    workflow = StateGraph(AgentState)
    workflow.add_node(
        "agent",
        lambda state: react_agent_node(
            state, db=db, tenant_id=tenant_id, user_id=user_id
        ),
    )
    workflow.add_node(
        "tools",
        lambda state: react_tool_executor_node(
            state, db=db, tenant_id=tenant_id, user_id=user_id
        ),
    )
    workflow.add_node("finalize", react_finalize_node)

    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges(
        "agent", should_continue, {"tools": "tools", "end": "finalize"}
    )
    workflow.add_edge("tools", "agent")
    workflow.add_edge("finalize", END)

    return workflow.compile(checkpointer=_memory_saver)


def make_thread_id(tenant_id: str, conversation_id: str | None) -> str:
    """生成 thread_id：有 conversation_id 则确定性拼接，否则用 uuid 保证唯一。"""
    if conversation_id:
        return f"{tenant_id}:{conversation_id}"
    return f"{tenant_id}:{uuid.uuid4().hex}"


def run_agent(
    question: str,
    tenant_id: str = "default",
    user_id: str | None = None,
    db: Any = None,
    conversation_id: str | None = None,
    history: list[Any] | None = None,
) -> dict[str, Any]:
    """一次性运行智能体并返回结果。

    Returns:
        {"answer": str, "intent": str, "confidence": float,
         "steps": list, "tool_result": dict}
    """
    # 1. 意图识别 + 参数抽取（规则优先，LLM 不可用时各自内部降级）
    intent_result = classify_intent(question, history=history, db=db)
    intent = intent_result.get("intent", "unknown")
    parameters = extract_parameters(question, intent, history=history, db=db)

    # 2. 初始化状态：工作字段全部置空，messages 携带历史供 ReAct 上下文
    initial_state: dict[str, Any] = {
        "question": question,
        "intent": intent,
        "parameters": parameters,
        "tool_result": {},
        "answer": "",
        "error": "",
        "conversation_id": conversation_id or "",
        "messages": history or [],
        "retry_count": 0,
        "react_steps": [],
        "react_thought": "",
        "react_action": "",
        "react_action_input": "",
        "confidence": 0.0,
        "tenant_id": tenant_id,
    }

    # 3. 编译并执行图；thread_id 驱动 MemorySaver 会话持久化
    agent = build_agent(tenant_id=tenant_id, user_id=user_id, db=db)
    thread_id = make_thread_id(tenant_id, conversation_id)
    config = {"configurable": {"thread_id": thread_id}}
    final_state = agent.invoke(initial_state, config=config)

    # 4. 归一化输出
    return {
        "answer": final_state.get("answer", ""),
        "intent": final_state.get("intent", intent),
        "confidence": float(final_state.get("confidence", 0.0) or 0.0),
        "steps": final_state.get("react_steps", []),
        "tool_result": final_state.get("tool_result", {}),
    }
