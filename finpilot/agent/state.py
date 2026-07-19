"""智能体状态定义 - LangGraph ReAct 图的共享状态结构。

所有节点通过 ``AgentState`` 读写状态，LangGraph 按字段（channel）做覆盖合并：
节点返回的 dict 中只包含需要更新的字段，未提及的字段保持上一轮的值。
"""
from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """ReAct 智能体运行时状态。

    字段说明：
        question:          用户本轮问题。
        intent:            意图标签（nl2sql/document_qa/parse_document/create_report/unknown）。
        parameters:        extract_parameters 抽取出的结构化参数。
        tool_result:       首次工具调用结果（dict），供上层直接消费。
        answer:            最终答案（由 finalize 节点写入）。
        error:             错误信息；非空时 should_continue 直接终止。
        conversation_id:   会话 ID，用于多轮追踪与 thread_id 生成。
        messages:          对话历史（list[dict|str]），作为 ReAct 上下文。
        retry_count:       解析失败累计次数（观测用）。
        react_steps:       ReAct 草稿本，每项含 thought/action/action_input/observation。
        react_thought:     当前轮 Thought 文本。
        react_action:      当前轮 Action（工具名 / FinalAnswer / __retry__）。
        react_action_input:当前轮 Action Input（工具参数 JSON 或最终答案文本）。
        confidence:        最终答案置信度（0~1）。
        tenant_id:         租户 ID，用于数据隔离。
    """

    question: str
    intent: str
    parameters: dict[str, Any]
    tool_result: dict[str, Any]
    answer: str
    error: str
    conversation_id: str
    messages: list[Any]
    retry_count: int
    react_steps: list[dict[str, Any]]
    react_thought: str
    react_action: str
    react_action_input: str
    confidence: float
    tenant_id: str
