"""Agent 鲁棒性护栏（Guardrails）。

针对开源 Agent 框架的四大通病补齐：
1. **死循环检测**：同一工具连续调用 N 次无进展（参数与结果 hash 都未变化）即判定死循环，
   强制中止并降级。
2. **上下文压缩**：草稿本累计 token 超阈值时，把历史 Observation 摘要为单行，保留最近 2 轮原文。
3. **工具降级**：工具不存在 / 参数错误 / 异常时返回结构化 Observation，让 LLM 自愈而非崩溃。
4. **幻觉校验**：FinalAnswer 中的数字 / 凭证号 / 日期类关键事实，必须能在 Observation 里回查到，
   命中率过低时给答案打 `[低可信]` 标记 + 列出未验证项。

设计要点：
- 纯函数 + 模块级常量，无状态，不污染 AgentState 字段（仅在 react_nodes 调用时按需写入）。
- 阈值由环境变量驱动，默认值在 .env.example 中维护。
- 每个函数都有清晰的"信号 → 行动"语义，便于扩展。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---- 阈值（env 驱动，便于现场调参） ----
_LOOP_LIMIT = int(os.getenv("FINPILOT_GUARDRAILS_LOOP_LIMIT", "3"))
_CONTEXT_TOKENS = int(os.getenv("FINPILOT_GUARDRAILS_CONTEXT_TOKENS", "8000"))
_HALLUCINATION_CHECK = os.getenv("FINPILOT_GUARDRAILS_HALLUCINATION_CHECK", "1") in (
    "1", "true", "yes", "on",
)

# 数字 / 凭证号 / 日期 模式（用于幻觉校验时抽取答案中的"事实"）
_FACT_PATTERNS = [
    re.compile(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b"),                # 2024-01-31
    re.compile(r"\b\d+\.\d{2}\b"),                                   # 1234.56
    re.compile(r"\b\d{1,3}(?:,\d{3})+\b"),                           # 1,234,567
    re.compile(r"\b[A-Z]{2,4}[-_]?\d{4,}[-_]?\d*\b"),                # JZ-2025-99-999
    re.compile(r"[\u4e00-\u9fa5]{2,6}[-_]\d{4,}"),                   # 凭证-2025001
]


# ---------------------------------------------------------------------------
# 1. 死循环检测
# ---------------------------------------------------------------------------


def _step_signature(action: str, action_input: str, observation: str) -> str:
    """生成单步签名：action + 参数 hash + 结果 hash（前 8 字符）。

    同工具 + 同参数 + 同结果 → 同签名，视为无进展。
    """
    inp_h = hashlib.md5(action_input.encode("utf-8")).hexdigest()[:8]
    obs_h = hashlib.md5((observation or "")[:200].encode("utf-8")).hexdigest()[:8]
    return f"{action}|{inp_h}|{obs_h}"


@dataclass
class LoopDetectionResult:
    is_looping: bool
    consecutive_count: int
    action: str
    reason: str = ""


def detect_tool_loop(steps: list[dict[str, Any]]) -> LoopDetectionResult:
    """检测草稿本中是否存在同工具连续无进展调用。

    判定规则：从最近一步往前看，连续 N 步 action 相同 *且* 签名相同 → 死循环。
    """
    if not steps:
        return LoopDetectionResult(False, 0, "")

    last_action = steps[-1].get("action", "") or ""
    if not last_action or last_action == "FinalAnswer":
        return LoopDetectionResult(False, 0, last_action)

    last_sig = _step_signature(
        last_action,
        steps[-1].get("action_input", ""),
        steps[-1].get("observation", ""),
    )

    count = 1
    for step in reversed(steps[:-1]):
        action = step.get("action", "") or ""
        if action != last_action:
            break
        sig = _step_signature(
            action,
            step.get("action_input", ""),
            step.get("observation", ""),
        )
        if sig != last_sig:
            break
        count += 1

    is_looping = count >= _LOOP_LIMIT
    return LoopDetectionResult(
        is_looping=is_looping,
        consecutive_count=count,
        action=last_action,
        reason=(
            f"工具 {last_action} 连续调用 {count} 次无进展（签名相同），"
            f"判定为死循环，强制终止"
            if is_looping
            else ""
        ),
    )


# ---------------------------------------------------------------------------
# 2. 上下文压缩
# ---------------------------------------------------------------------------


def _approx_tokens(text: str) -> int:
    """粗略估算 token 数：中文按 1.5 字/token，英文按 4 字符/token。"""
    if not text:
        return 0
    cn = sum(1 for c in text if "\u4e00" <= c <= "\u9fa5")
    other = len(text) - cn
    return int(cn * 1.5 + other / 4)


@dataclass
class CompressionResult:
    compressed: bool
    new_steps: list[dict[str, Any]]
    saved_tokens: int
    reason: str = ""


def compress_context(steps: list[dict[str, Any]]) -> CompressionResult:
    """草稿本超阈值时压缩：旧步骤 Observation 折叠为单行摘要，保留最近 2 轮原文。"""
    if len(steps) <= 3:
        return CompressionResult(False, steps, 0)

    total_tokens = sum(_approx_tokens(s.get("observation", "")) for s in steps)
    if total_tokens <= _CONTEXT_TOKENS:
        return CompressionResult(False, steps, 0)

    # 保留最近 2 轮原文，更早的 Observation 折叠
    keep_recent = 2
    new_steps: list[dict[str, Any]] = []
    for i, step in enumerate(steps):
        if i >= len(steps) - keep_recent:
            new_steps.append(step)
            continue
        obs = step.get("observation", "")
        if not obs:
            new_steps.append(step)
            continue
        # 折叠：取前 80 字 + 长度信息
        folded = obs[:80] + (f"...(已折叠，原 {len(obs)} 字符)" if len(obs) > 80 else "")
        new_steps.append({**step, "observation": folded})

    saved = total_tokens - sum(_approx_tokens(s.get("observation", "")) for s in new_steps)
    return CompressionResult(
        compressed=True,
        new_steps=new_steps,
        saved_tokens=saved,
        reason=f"草稿本累计 ~{total_tokens} tokens 超阈值 {_CONTEXT_TOKENS}，已折叠旧步骤（节省 ~{saved} tokens）",
    )


# ---------------------------------------------------------------------------
# 3. 工具降级（结构化错误 Observation）
# ---------------------------------------------------------------------------


def make_tool_error_observation(
    tool_name: str,
    error: Exception | str,
    *,
    available_tools: list[str] | None = None,
) -> str:
    """生成结构化工具错误 Observation，引导 LLM 自愈。

    返回的 Observation 明确告诉 LLM：
    - 出错的工具与错误类型
    - 可选的替代工具
    - 建议的下一步动作（换工具 / 修正参数 / 直接 FinalAnswer）
    """
    err_msg = str(error) if isinstance(error, Exception) else str(error)
    err_type = type(error).__name__ if isinstance(error, Exception) else "Error"
    parts = [
        f"工具执行失败：{tool_name}({err_type}): {err_msg[:200]}",
    ]
    if available_tools:
        alternatives = [t for t in available_tools if t != tool_name]
        if alternatives:
            parts.append(f"可用替代工具：{', '.join(alternatives[:5])}")
    parts.append("建议：1) 检查参数格式 2) 换用替代工具 3) 若已获得足够信息，直接 FinalAnswer")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 4. 幻觉校验
# ---------------------------------------------------------------------------


def _extract_facts(text: str) -> list[str]:
    """从文本中抽取"事实"token：日期 / 金额 / 凭证号。"""
    facts: list[str] = []
    for pat in _FACT_PATTERNS:
        facts.extend(pat.findall(text))
    # 去重保序
    seen: set[str] = set()
    unique: list[str] = []
    for f in facts:
        if f not in seen:
            seen.add(f)
            unique.append(f)
    return unique


@dataclass
class HallucinationReport:
    is_enabled: bool
    total_facts: int
    verified_facts: list[str]
    unverified_facts: list[str]
    hit_rate: float
    should_flag: bool
    reason: str = ""


def check_hallucination(
    answer: str, steps: list[dict[str, Any]]
) -> HallucinationReport:
    """校验答案中的关键事实能否在 Observation 中回查到。

    判定规则：
    - 抽取答案中的日期 / 金额 / 凭证号
    - 每个 fact 必须能在任一 Observation 中找到
    - 命中率 < 0.5 且事实数 >= 3 → 标记为低可信

    Returns:
        HallucinationReport：包含命中 / 未命中清单与是否标记。
    """
    if not _HALLUCINATION_CHECK:
        return HallucinationReport(False, 0, [], [], 1.0, False, "幻觉校验已禁用")

    facts = _extract_facts(answer)
    if not facts:
        return HallucinationReport(True, 0, [], [], 1.0, False, "答案中无可校验事实")

    all_observations = " ".join(s.get("observation", "") for s in steps)
    verified: list[str] = []
    unverified: list[str] = []
    for fact in facts:
        if fact in all_observations:
            verified.append(fact)
        else:
            unverified.append(fact)

    hit_rate = len(verified) / len(facts) if facts else 1.0
    should_flag = len(facts) >= 3 and hit_rate < 0.5
    reason = (
        f"事实命中率 {hit_rate:.0%}（{len(verified)}/{len(facts)}）"
        + ("，低于 50% 阈值，标记为低可信" if should_flag else "")
    )
    return HallucinationReport(
        is_enabled=True,
        total_facts=len(facts),
        verified_facts=verified,
        unverified_facts=unverified,
        hit_rate=hit_rate,
        should_flag=should_flag,
        reason=reason,
    )


def annotate_answer_with_confidence(
    answer: str, report: HallucinationReport
) -> str:
    """如果触发幻觉告警，给答案加低可信前缀 + 未验证项清单。"""
    if not report.should_flag:
        return answer
    prefix = "⚠️ [低可信] 以下关键事实未能从工具结果中验证："
    unverified_list = "\n".join(f"  - {f}" for f in report.unverified_facts[:5])
    suffix = "建议人工核对上述数据后再采信。"
    return f"{prefix}\n{unverified_list}\n\n{answer}\n\n{suffix}"
