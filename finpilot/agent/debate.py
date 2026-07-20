"""多智能体对抗辩论（Adversarial Debate）— 投研决策场景。

借鉴 TradingAgents（AAAI 2025）架构，落地到 FinPilot 的 LangGraph 栈：

    START → research → debate(bull ⇄ bear × N 轮) → risk → pm → END

四角色：
- **Research Analyst**：从工具结果中抽取公司基本面 / 财务指标 / 行业数据
- **Bull Agent**（看多）：基于研究数据给出看多论点
- **Bear Agent**（看空）：基于研究数据给出看空论点
- **Risk Agent**：评估多空辩论结论的风险敞口（财务 / 估值 / 流动性 / 治理）
- **PM Agent**（投资经理）：综合给出最终投资建议（买 / 持 / 卖 + 仓位 + 止损）

设计要点：
- 与现有 ReAct Agent 并行存在，作为高级投研决策入口；不替换 ReAct。
- 所有 Agent 共用 LLMClient，按 tier 路由档位。
- 辩论结论结构化为 DebateResult，含各方发言 + PM 综合结论 + 风险评级 + 关键证据链。
- 阈值由环境变量 FINPILOT_DEBATE_MAX_ROUNDS 驱动（默认 3 轮）。
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from finpilot.llm.client import LLMClient, LLMUnavailableError
from finpilot.llm.config import get_default_config, get_tier_config

logger = logging.getLogger(__name__)

_MAX_ROUNDS = int(os.getenv("FINPILOT_DEBATE_MAX_ROUNDS", "3"))


# ---------------------------------------------------------------------------
# 状态与结果
# ---------------------------------------------------------------------------


class DebateState(TypedDict, total=False):
    """辩论图共享状态。"""
    question: str                       # 用户原始问题（如"分析贵州茅台 2024 年投资价值"）
    research_data: str                  # Research Analyst 抽取的研究数据文本
    bull_arguments: list[str]           # Bull 各轮论点
    bear_arguments: list[str]           # Bear 各轮论点
    risk_assessment: str                # Risk Agent 风险评估
    final_decision: str                 # PM 最终决策
    confidence: float                   # PM 综合置信度
    evidence_chain: list[dict[str, Any]]  # 关键证据链
    error: str


@dataclass
class DebateResult:
    """辩论最终结果（对外暴露）。"""
    question: str
    research_data: str
    bull_arguments: list[str]
    bear_arguments: list[str]
    risk_assessment: str
    final_decision: str
    confidence: float
    evidence_chain: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Prompt 模板
# ---------------------------------------------------------------------------


_RESEARCH_PROMPT = """你是一名严谨的证券研究分析师。
基于以下用户问题与可用的研究材料（来自上游工具调用），抽取并结构化呈现：

1. 公司基本面（主营业务、行业地位、核心竞争力）
2. 关键财务指标（营收 / 利润 / 毛利率 / 现金流 / 资产负债率）
3. 估值水平（PE / PB / PS / DCF）
4. 行业与宏观因素
5. 重大事件与风险点

输出要客观、有数据支撑，不带主观倾向。如果数据缺失，明确指出。

用户问题：{question}
"""


_BULL_PROMPT = """你是看多分析师（Bull）。
基于以下研究数据与对方上一轮的反驳论点，提出 {round} 个有力的看多论点。
每个论点必须包含：
1. 论点陈述
2. 数据支撑（引用研究数据中的具体数字）
3. 反驳对方的论点（如有）

研究数据：
{research_data}

{opponent_context}

请严格按以下格式输出（不要任何额外说明）：
1. [论点1] - 数据: xxx - 反驳: xxx
2. [论点2] - 数据: xxx - 反驳: xxx
3. [论点3] - 数据: xxx - 反驳: xxx
"""


_BEAR_PROMPT = """你是看空分析师（Bear）。
基于以下研究数据与对方上一轮的反驳论点，提出 {round} 个有力的看空论点。
每个论点必须包含：
1. 论点陈述
2. 数据支撑（引用研究数据中的具体数字）
3. 反驳对方的论点（如有）

研究数据：
{research_data}

{opponent_context}

请严格按以下格式输出（不要任何额外说明）：
1. [论点1] - 数据: xxx - 反驳: xxx
2. [论点2] - 数据: xxx - 反驳: xxx
3. [论点3] - 数据: xxx - 反驳: xxx
"""


_RISK_PROMPT = """你是风险评估专家。
基于多空辩论结论，从以下 5 个维度评估风险（每项 1-5 分，5 为最高风险）：

1. 财务风险（杠杆 / 流动性 / 盈利质量）
2. 估值风险（是否过高 / 是否被低估）
3. 经营风险（业务模式 / 客户集中 / 技术替代）
4. 治理风险（关联交易 / 信息披露 / 管理层）
5. 宏观风险（行业政策 / 周期 / 地缘）

研究数据：
{research_data}

Bull 论点：
{bull_arguments}

Bear 论点：
{bear_arguments}

请严格按以下格式输出：
财务风险: X/5 - 说明
估值风险: X/5 - 说明
经营风险: X/5 - 说明
治理风险: X/5 - 说明
宏观风险: X/5 - 说明
综合风险等级: 低/中/高
"""


_PM_PROMPT = """你是投资组合经理（PM）。
基于研究数据、多空辩论、风险评估，给出最终投资建议。

研究数据：
{research_data}

Bull 论点：
{bull_arguments}

Bear 论点：
{bear_arguments}

风险评估：
{risk_assessment}

请严格按以下格式输出：
投资建议: 买入/持有/卖出
建议仓位: X%（0-100）
止损位: xxx
目标价: xxx
持有期: 短期/中期/长期
置信度: X%（0-100）
核心理由（3 条）:
1. xxx
2. xxx
3. xxx
"""


# ---------------------------------------------------------------------------
# 节点实现
# ---------------------------------------------------------------------------


def _resolve_llm(db: Any, tier: str = "medium") -> LLMClient | None:
    """按 tier 解析 LLM 配置，失败返回 None。"""
    try:
        config = None
        if db is not None:
            config = get_tier_config(db, tier) or get_default_config(db)
        if config is None:
            return None
        return LLMClient(config)
    except LLMUnavailableError as exc:
        logger.warning("debate_llm_unavailable: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("debate_llm_init_failed: %s", exc)
        return None


def research_node(state: DebateState, *, db: Any = None) -> dict[str, Any]:
    """研究分析师节点：从问题中抽取研究数据。"""
    question = state.get("question", "")
    client = _resolve_llm(db, tier="medium")
    if client is None:
        return {
            "research_data": "",
            "error": "LLM 不可用，无法执行研究分析",
        }
    try:
        research = client.chat(
            _RESEARCH_PROMPT.format(question=question),
            "请开始研究分析。",
            temperature=0.2,
            max_tokens=1500,
        )
    except LLMUnavailableError as exc:
        return {"research_data": "", "error": f"研究分析 LLM 调用失败: {exc}"}
    return {"research_data": research, "error": ""}


def bull_node(
    state: DebateState,
    *,
    round_idx: int,
    db: Any = None,
) -> dict[str, Any]:
    """Bull 节点：根据轮次产生看多论点。"""
    bull_args = state.get("bull_arguments", [])
    bear_args = state.get("bear_arguments", [])
    research = state.get("research_data", "")

    # 首轮无对方论点；后续轮次有 Bear 上一轮论点
    if round_idx == 0 or not bear_args:
        opponent_context = "（首轮辩论，暂无对方论点可反驳）"
    else:
        opponent_context = f"对方（Bear）上一轮论点：\n{bear_args[-1]}"

    client = _resolve_llm(db, tier="medium")
    if client is None:
        return {"bull_arguments": bull_args + ["[Bull LLM 不可用，跳过本轮]"]}

    try:
        argument = client.chat(
            _BULL_PROMPT.format(
                round=3,
                research_data=research[:3000],
                opponent_context=opponent_context,
            ),
            f"开始第 {round_idx + 1} 轮看多辩论。",
            temperature=0.4,
            max_tokens=800,
        )
    except LLMUnavailableError as exc:
        logger.warning("bull_llm_failed: %s", exc)
        argument = f"[Bull LLM 调用失败: {exc}]"
    return {"bull_arguments": bull_args + [argument]}


def bear_node(
    state: DebateState,
    *,
    round_idx: int,
    db: Any = None,
) -> dict[str, Any]:
    """Bear 节点：根据轮次产生看空论点。"""
    bear_args = state.get("bear_arguments", [])
    bull_args = state.get("bull_arguments", [])
    research = state.get("research_data", "")

    if round_idx == 0 or not bull_args:
        opponent_context = "（首轮辩论，暂无对方论点可反驳）"
    else:
        opponent_context = f"对方（Bull）上一轮论点：\n{bull_args[-1]}"

    client = _resolve_llm(db, tier="medium")
    if client is None:
        return {"bear_arguments": bear_args + ["[Bear LLM 不可用，跳过本轮]"]}

    try:
        argument = client.chat(
            _BEAR_PROMPT.format(
                round=3,
                research_data=research[:3000],
                opponent_context=opponent_context,
            ),
            f"开始第 {round_idx + 1} 轮看空辩论。",
            temperature=0.4,
            max_tokens=800,
        )
    except LLMUnavailableError as exc:
        logger.warning("bear_llm_failed: %s", exc)
        argument = f"[Bear LLM 调用失败: {exc}]"
    return {"bear_arguments": bear_args + [argument]}


def risk_node(state: DebateState, *, db: Any = None) -> dict[str, Any]:
    """风险节点：评估多空辩论结论的风险。"""
    client = _resolve_llm(db, tier="medium")
    if client is None:
        return {"risk_assessment": "[LLM 不可用，风险评估跳过]"}

    bull_args = state.get("bull_arguments", [])
    bear_args = state.get("bear_arguments", [])
    research = state.get("research_data", "")

    try:
        assessment = client.chat(
            _RISK_PROMPT.format(
                research_data=research[:2000],
                bull_arguments="\n---\n".join(bull_args[-2:]),
                bear_arguments="\n---\n".join(bear_args[-2:]),
            ),
            "请开始风险评估。",
            temperature=0.2,
            max_tokens=800,
        )
    except LLMUnavailableError as exc:
        assessment = f"[风险评估 LLM 调用失败: {exc}]"
    return {"risk_assessment": assessment}


def pm_node(state: DebateState, *, db: Any = None) -> dict[str, Any]:
    """PM 节点：综合所有信息给出最终决策。"""
    client = _resolve_llm(db, tier="high")
    if client is None:
        return {
            "final_decision": "[LLM 不可用，无法生成最终决策]",
            "confidence": 0.0,
            "evidence_chain": [],
        }

    bull_args = state.get("bull_arguments", [])
    bear_args = state.get("bear_arguments", [])
    research = state.get("research_data", "")
    risk = state.get("risk_assessment", "")

    try:
        decision = client.chat(
            _PM_PROMPT.format(
                research_data=research[:1500],
                bull_arguments="\n---\n".join(bull_args[-2:]),
                bear_arguments="\n---\n".join(bear_args[-2:]),
                risk_assessment=risk,
            ),
            "请给出最终投资决策。",
            temperature=0.2,
            max_tokens=800,
        )
    except LLMUnavailableError as exc:
        return {
            "final_decision": f"[PM LLM 调用失败: {exc}]",
            "confidence": 0.0,
            "evidence_chain": [],
        }

    # 从决策文本中提取置信度
    confidence = _extract_confidence(decision)
    evidence = _build_evidence_chain(state, decision)

    return {
        "final_decision": decision,
        "confidence": confidence,
        "evidence_chain": evidence,
    }


def _extract_confidence(text: str) -> float:
    """从决策文本中提取置信度百分比。"""
    import re
    m = re.search(r"置信度[:：]\s*(\d+(?:\.\d+)?)\s*%", text)
    if m:
        try:
            return round(float(m.group(1)) / 100, 2)
        except ValueError:
            pass
    return 0.6  # 默认置信度


def _build_evidence_chain(state: DebateState, decision: str) -> list[dict[str, Any]]:
    """构建证据链：列出 Bull/Bear 各轮核心论点 + 风险评级 + PM 决策。"""
    chain: list[dict[str, Any]] = []
    for i, arg in enumerate(state.get("bull_arguments", [])):
        chain.append({
            "type": "bull_argument",
            "round": i + 1,
            "content": arg[:500],
        })
    for i, arg in enumerate(state.get("bear_arguments", [])):
        chain.append({
            "type": "bear_argument",
            "round": i + 1,
            "content": arg[:500],
        })
    chain.append({
        "type": "risk_assessment",
        "content": state.get("risk_assessment", "")[:500],
    })
    chain.append({
        "type": "pm_decision",
        "content": decision[:500],
    })
    return chain


# ---------------------------------------------------------------------------
# 图构建与运行入口
# ---------------------------------------------------------------------------


def build_debate_graph(*, db: Any = None, max_rounds: int = _MAX_ROUNDS) -> Any:
    """构建多智能体辩论图。

    图结构：
        START → research → bull_0 → bear_0 → bull_1 → bear_1 → ... → risk → pm → END

    每轮 Bull 和 Bear 各发言一次，共 max_rounds 轮。
    """
    workflow = StateGraph(DebateState)

    workflow.add_node("research", lambda s: research_node(s, db=db))

    # 动态添加 max_rounds 轮 Bull/Bear 节点
    for i in range(max_rounds):
        workflow.add_node(
            f"bull_{i}",
            lambda s, idx=i: bull_node(s, round_idx=idx, db=db),
        )
        workflow.add_node(
            f"bear_{i}",
            lambda s, idx=i: bear_node(s, round_idx=idx, db=db),
        )

    workflow.add_node("risk", lambda s: risk_node(s, db=db))
    workflow.add_node("pm", lambda s: pm_node(s, db=db))

    # 连边
    workflow.add_edge(START, "research")
    workflow.add_edge("research", "bull_0")
    for i in range(max_rounds):
        workflow.add_edge(f"bull_{i}", f"bear_{i}")
        if i + 1 < max_rounds:
            workflow.add_edge(f"bear_{i}", f"bull_{i+1}")
        else:
            workflow.add_edge(f"bear_{i}", "risk")
    workflow.add_edge("risk", "pm")
    workflow.add_edge("pm", END)

    return workflow.compile()


def run_debate(
    question: str,
    *,
    db: Any = None,
    max_rounds: int | None = None,
) -> DebateResult:
    """运行多智能体辩论，返回结构化结果。

    Args:
        question: 投研问题（如"分析贵州茅台 2024 年投资价值"）
        db: 数据库会话（用于解析 LLM 配置）
        max_rounds: 辩论轮数，默认取环境变量

    Returns:
        DebateResult：含各方发言 + PM 决策 + 风险评估 + 证据链
    """
    rounds = max_rounds if max_rounds is not None else _MAX_ROUNDS
    graph = build_debate_graph(db=db, max_rounds=rounds)

    initial_state: DebateState = {
        "question": question,
        "research_data": "",
        "bull_arguments": [],
        "bear_arguments": [],
        "risk_assessment": "",
        "final_decision": "",
        "confidence": 0.0,
        "evidence_chain": [],
        "error": "",
    }
    final_state = graph.invoke(initial_state)

    return DebateResult(
        question=question,
        research_data=final_state.get("research_data", ""),
        bull_arguments=final_state.get("bull_arguments", []),
        bear_arguments=final_state.get("bear_arguments", []),
        risk_assessment=final_state.get("risk_assessment", ""),
        final_decision=final_state.get("final_decision", ""),
        confidence=float(final_state.get("confidence", 0.0) or 0.0),
        evidence_chain=final_state.get("evidence_chain", []),
    )
