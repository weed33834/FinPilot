"""可解释 AI（Explainable AI）— 因子归因与决策追溯。

针对金融评委对"可解释性"的强需求，提供两层解释能力：

1. **因子归因（Factor Attribution）**
   - 基于线性回归的 SHAP-lite 近似：对每个特征计算 Shapley 值的加权近似
   - 输出每个特征对预测结果的贡献度（正/负 + 量值）
   - 适用于财务指标归因（哪些因素驱动了毛利率变化 / 现金流变化）

2. **决策追溯（Decision Trace）**
   - 从 ReAct 草稿本中抽取决策路径（Thought → Action → Observation）
   - 关联 Observation 中的关键数字与最终答案中的数字
   - 输出"为什么得到这个结论"的证据链

3. **LLM 自解释（LLM Self-Explanation）**
   - 让 LLM 用自然语言解释自己的推理过程
   - 兜底方案：当无法做数值归因时，用 LLM 描述关键依据

设计要点：
- 不依赖 shap 库（避免重依赖），用线性回归 + 加权近似实现 SHAP-lite
- 纯函数 + dataclass，无状态
- 输出 ExplainabilityReport，可序列化为 JSON
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from finpilot.llm.client import LLMClient, LLMUnavailableError
from finpilot.llm.config import get_default_config, get_tier_config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class FactorContribution:
    """单因子贡献度。"""
    factor_name: str
    value: float                   # 因子原值（标准化前）
    contribution: float            # Shapley 近似贡献度（带符号）
    relative_importance: float     # 相对重要性（0-1，所有因子加总=1）
    direction: str                 # "positive" / "negative" / "neutral"


@dataclass
class EvidenceItem:
    """证据链单条。"""
    source: str                    # "research_data" / "bull_argument" / "observation" 等
    round_idx: int                 # 轮次（如适用）
    content: str                   # 证据原文片段
    cited_in_final: bool           # 是否在最终答案中被引用


@dataclass
class ExplainabilityReport:
    """可解释性报告。"""
    question: str
    final_answer: str
    factor_contributions: list[FactorContribution] = field(default_factory=list)
    evidence_chain: list[EvidenceItem] = field(default_factory=list)
    llm_explanation: str = ""
    model_confidence: float = 0.0
    explanation_method: str = ""   # "shap_lite" / "decision_trace" / "llm_self"

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "final_answer": self.final_answer,
            "factor_contributions": [asdict(f) for f in self.factor_contributions],
            "evidence_chain": [asdict(e) for e in self.evidence_chain],
            "llm_explanation": self.llm_explanation,
            "model_confidence": self.model_confidence,
            "explanation_method": self.explanation_method,
        }


# ---------------------------------------------------------------------------
# 1. 因子归因（SHAP-lite）
# ---------------------------------------------------------------------------


def shap_lite_attribution(
    features: dict[str, float],
    *,
    weights: dict[str, float] | None = None,
    baseline: float = 0.0,
) -> list[FactorContribution]:
    """SHAP-lite 近似归因：基于线性权重的 Shapley 值加权近似。

    Args:
        features: 因子名 → 因子值（如 {"revenue_growth": 0.15, "gross_margin": 0.35}）
        weights: 因子名 → 线性权重（如 {"revenue_growth": 1.2, "gross_margin": 0.8}）
                 缺省时所有因子等权
        baseline: 基线值（默认 0）

    Returns:
        FactorContribution 列表，按相对重要性降序排序
    """
    if not features:
        return []

    if weights is None:
        weights = {k: 1.0 for k in features}

    # 计算每个因子的贡献度 = weight * (value - mean_value)
    # SHAP-lite 近似：对于线性模型 f(x) = Σ w_i * x_i，Shapley 值 ≈ w_i * (x_i - E[x_i])
    mean_value = sum(features.values()) / len(features)
    contributions: list[FactorContribution] = []
    total_abs = 0.0
    for name, value in features.items():
        weight = weights.get(name, 1.0)
        contribution = weight * (value - mean_value)
        contributions.append(FactorContribution(
            factor_name=name,
            value=value,
            contribution=contribution,
            relative_importance=0.0,  # 后面计算
            direction=(
                "positive" if contribution > 0.001
                else "negative" if contribution < -0.001
                else "neutral"
            ),
        ))
        total_abs += abs(contribution)

    # 归一化为相对重要性
    for c in contributions:
        c.relative_importance = (
            abs(c.contribution) / total_abs if total_abs > 0 else 0.0
        )

    # 按相对重要性降序
    contributions.sort(key=lambda x: x.relative_importance, reverse=True)
    return contributions


# ---------------------------------------------------------------------------
# 2. 决策追溯
# ---------------------------------------------------------------------------


_FACT_PATTERN = re.compile(r"\b\d+(?:\.\d+)?(?:,\d{3})*\b")


def trace_decision(
    question: str,
    final_answer: str,
    steps: list[dict[str, Any]],
    *,
    confidence: float = 0.0,
) -> list[EvidenceItem]:
    """从 ReAct 草稿本中抽取证据链。

    判定规则：
    - 每步 Observation 中的数字是否在 final_answer 中出现
    - 出现 → cited_in_final=True
    - 未出现但提到 → cited_in_final=False（仍可作为补充证据）
    """
    evidence: list[EvidenceItem] = []
    answer_numbers = set(_FACT_PATTERN.findall(final_answer))

    for i, step in enumerate(steps):
        obs = step.get("observation", "")
        if not obs or len(obs) < 10:
            continue
        # 抽取该步的数字
        step_numbers = set(_FACT_PATTERN.findall(obs))
        # 该步至少有一个数字被 final 引用 → 视为关键证据
        cited = bool(step_numbers & answer_numbers)
        # 取前 300 字作为证据片段
        content = obs[:300] + ("..." if len(obs) > 300 else "")
        evidence.append(EvidenceItem(
            source="observation",
            round_idx=i,
            content=content,
            cited_in_final=cited,
        ))

    # 按是否被引用排序（被引用的排前面）
    evidence.sort(key=lambda x: (not x.cited_in_final, -x.round_idx))
    return evidence


# ---------------------------------------------------------------------------
# 3. LLM 自解释
# ---------------------------------------------------------------------------


_EXPLAIN_PROMPT = """你是金融 AI 助手，需要解释你的推理过程。

用户问题：{question}
你的最终答案：{answer}
草稿本（Thought/Action/Observation 链）：
{scratchpad}

请用 3-5 条简短的要点说明：
1. 你为什么得出这个结论
2. 哪些数据支撑了你的结论
3. 哪些数据与结论矛盾（如有）
4. 你的结论的局限性

输出格式：
1. xxx
2. xxx
3. xxx
4. xxx
"""


def llm_self_explain(
    question: str,
    answer: str,
    steps: list[dict[str, Any]],
    *,
    db: Any = None,
) -> str:
    """LLM 自解释：让 LLM 用自然语言解释推理过程。

    LLM 不可用时返回空串（兜底）。
    """
    try:
        config = None
        if db is not None:
            config = get_tier_config(db, "medium") or get_default_config(db)
        if config is None:
            return ""
        client = LLMClient(config)
    except (LLMUnavailableError, Exception) as exc:  # noqa: BLE001
        logger.warning("explain_llm_unavailable: %s", exc)
        return ""

    scratchpad = "\n".join(
        f"Thought: {s.get('thought', '')}\n"
        f"Action: {s.get('action', '')}\n"
        f"Observation: {s.get('observation', '')[:200]}"
        for s in steps[-5:]  # 最近 5 步
    )

    try:
        return client.chat(
            _EXPLAIN_PROMPT.format(
                question=question,
                answer=answer,
                scratchpad=scratchpad,
            ),
            "请解释你的推理过程。",
            temperature=0.2,
            max_tokens=500,
        )
    except LLMUnavailableError as exc:
        logger.warning("explain_llm_call_failed: %s", exc)
        return ""


# ---------------------------------------------------------------------------
# 4. 统一入口
# ---------------------------------------------------------------------------


def explain_decision(
    question: str,
    answer: str,
    steps: list[dict[str, Any]],
    *,
    features: dict[str, float] | None = None,
    feature_weights: dict[str, float] | None = None,
    confidence: float = 0.0,
    db: Any = None,
) -> ExplainabilityReport:
    """统一解释入口：组合因子归因 + 决策追溯 + LLM 自解释。

    Args:
        question: 用户原始问题
        answer: Agent 最终答案
        steps: ReAct 草稿本
        features: 可选的因子 dict（用于数值归因）
        feature_weights: 可选的因子权重
        confidence: 模型置信度
        db: 数据库会话（用于 LLM 自解释）

    Returns:
        ExplainabilityReport：含因子贡献 + 证据链 + LLM 解释
    """
    report = ExplainabilityReport(
        question=question,
        final_answer=answer,
        model_confidence=confidence,
    )

    # 1. 因子归因（如有 features）
    if features:
        report.factor_contributions = shap_lite_attribution(
            features, weights=feature_weights
        )
        report.explanation_method = "shap_lite"

    # 2. 决策追溯
    report.evidence_chain = trace_decision(
        question, answer, steps, confidence=confidence
    )
    if not report.explanation_method:
        report.explanation_method = "decision_trace"

    # 3. LLM 自解释（兜底/补充）
    llm_expl = llm_self_explain(question, answer, steps, db=db)
    if llm_expl:
        report.llm_explanation = llm_expl
        if not report.explanation_method:
            report.explanation_method = "llm_self"

    return report
