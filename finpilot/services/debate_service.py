"""辩论机制 — 看涨/看跌 Agent + 裁判 Agent.

借鉴 TradingAgents-CN 的辩论机制：
1. Bull Agent：从正面分析数据，寻找增长机会和积极信号
2. Bear Agent：从反面分析数据，识别风险和潜在问题
3. Judge Agent：综合双方论点，给出平衡的投资建议

适用场景：投资建议、风险评估、战略决策
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from finpilot.llm.client import LLMClient
from finpilot.llm import LLMUnavailableError

logger = logging.getLogger(__name__)

BULL_SYSTEM_PROMPT = """你是一位乐观的财务分析师（看涨分析师）。

你的职责是从积极的角度分析财务数据：
1. 寻找增长机会和正面趋势
2. 强调公司的竞争优势和潜力
3. 找出财务数据中的亮点
4. 提出看涨的投资逻辑

要求：
- 基于提供的数据进行分析，不得编造数字
- 给出 1-3 个核心看涨论点
- 每个论点附带数据支撑
- 给出看涨置信度（0-1）
"""

BEAR_SYSTEM_PROMPT = """你是一位谨慎的财务分析师（看跌分析师）。

你的职责是从保守的角度分析财务数据：
1. 识别潜在风险和负面趋势
2. 强调财务数据中的隐忧
3. 找出可能被忽视的问题
4. 提出看跌的风险逻辑

要求：
- 基于提供的数据进行分析，不得编造数字
- 给出 1-3 个核心看跌论点
- 每个论点附带数据支撑
- 给出看跌置信度（0-1）
"""

JUDGE_SYSTEM_PROMPT = """你是一位中立的财务裁判。

你的职责是综合看涨和看跌分析师的论点：
1. 评估双方论点的合理性
2. 指出哪些论点更有说服力
3. 给出平衡的投资建议（买入/持有/卖出）
4. 评估整体风险水平（低/中/高）

要求：
- 公正评判，不偏向任何一方
- 引用双方论点中的关键数据
- 给出最终置信度（0-1）
"""


@dataclass
class DebateArguments:
    """辩论论点."""

    bull_points: list[str] = field(default_factory=list)
    bull_confidence: float = 0.5
    bear_points: list[str] = field(default_factory=list)
    bear_confidence: float = 0.5
    judge_verdict: str = ""
    recommendation: str = "持有"  # 买入/持有/卖出
    risk_level: str = "中"  # 低/中/高
    final_confidence: float = 0.5
    bull_analysis: str = ""
    bear_analysis: str = ""
    judge_analysis: str = ""


@dataclass
class DebateArgument:
    """结构化辩论论点（用于多轮辩论与评分）."""

    point: str = ""
    supporting_data: list[str] = field(default_factory=list)
    confidence: float = 0.5
    side: str = ""  # bull / bear


@dataclass
class DebateRound:
    """单轮辩论结构.

    Attributes:
        round_num: 轮次序号（1 开始）
        bull_arguments: 看涨方论点列表
        bear_arguments: 看跌方论点列表
        bull_rebuttal: 看涨方反驳（针对看跌方上一轮），无则 None
        bear_rebuttal: 看跌方反驳，无则 None
    """

    round_num: int
    bull_arguments: list[DebateArgument] = field(default_factory=list)
    bear_arguments: list[DebateArgument] = field(default_factory=list)
    bull_rebuttal: str | None = None
    bear_rebuttal: str | None = None


def run_debate(
    question: str,
    financial_data: dict[str, Any],
    tenant_id: str | None = None,
) -> DebateArguments:
    """执行看涨/看跌辩论分析.

    Args:
        question: 用户问题（如"这家公司值得投资吗？"）
        financial_data: 财务数据字典
        tenant_id: 租户 ID（用于加载 DB 提示词）

    Returns:
        DebateArguments 包含双方论点和裁判结论
    """
    data_text = _format_data(financial_data)

    # 加载 DB 提示词（可选）
    bull_prompt = BULL_SYSTEM_PROMPT
    bear_prompt = BEAR_SYSTEM_PROMPT
    judge_prompt = JUDGE_SYSTEM_PROMPT
    if tenant_id:
        try:
            from finpilot.services.prompt_loader import get_prompt
            db_bull = get_prompt("debate_bull_system", tenant_id)
            if db_bull:
                bull_prompt = db_bull
            db_bear = get_prompt("debate_bear_system", tenant_id)
            if db_bear:
                bear_prompt = db_bear
            db_judge = get_prompt("debate_judge_system", tenant_id)
            if db_judge:
                judge_prompt = db_judge
        except Exception:  # noqa: BLE001
            pass

    result = DebateArguments()

    try:
        client = LLMClient()
        user_prompt = f"分析问题：{question}\n\n财务数据：\n{data_text}"

        # 1. 看涨分析
        bull_response = client.chat(system_prompt=bull_prompt, user_prompt=user_prompt)
        result.bull_analysis = bull_response
        result.bull_points = _extract_points(bull_response)
        result.bull_confidence = _extract_confidence(bull_response, 0.6)

        # 2. 看跌分析
        bear_response = client.chat(system_prompt=bear_prompt, user_prompt=user_prompt)
        result.bear_analysis = bear_response
        result.bear_points = _extract_points(bear_response)
        result.bear_confidence = _extract_confidence(bear_response, 0.5)

        # 3. 裁判综合
        judge_prompt_text = f"""分析问题：{question}

财务数据：
{data_text}

看涨分析师观点：
{bull_response}

看跌分析师观点：
{bear_response}

请综合评判，给出最终投资建议。"""
        judge_response = client.chat(system_prompt=judge_prompt, user_prompt=judge_prompt_text)
        result.judge_analysis = judge_response
        result.judge_verdict = judge_response[:500]
        result.recommendation = _extract_recommendation(judge_response)
        result.risk_level = _extract_risk_level(judge_response)
        result.final_confidence = _extract_confidence(judge_response, 0.6)

    except (LLMUnavailableError, Exception) as exc:  # noqa: BLE001
        logger.warning("debate_failed", error=str(exc))
        # 降级：基于财务数据简单规则判断
        result.judge_verdict = f"LLM 不可用，无法完成辩论分析。错误: {exc!s}"
        result.recommendation = "持有"
        result.risk_level = "中"
        result.final_confidence = 0.3

    return result


def _format_data(data: dict[str, Any]) -> str:
    """格式化财务数据为文本."""
    lines: list[str] = []
    metric_labels = {
        "revenue": "营业收入",
        "net_profit": "净利润",
        "total_assets": "总资产",
        "total_liabilities": "总负债",
        "owner_equity": "所有者权益",
        "cash_flow_operating": "经营活动现金流",
    }
    for key, label in metric_labels.items():
        val = data.get(key)
        if val is not None:
            lines.append(f"- {label}: {float(val):,.2f}")
    return "\n".join(lines) if lines else "无数据"


def _extract_points(text: str) -> list[str]:
    """从文本中提取论点列表."""
    import re
    # 匹配 "- xxx" 或 "1. xxx" 或 "• xxx" 格式
    points = re.findall(r"(?:[-*•]|\d+\.)\s*(.+?)(?=\n|$)", text)
    return [p.strip() for p in points if len(p.strip()) > 5][:5]


def _extract_confidence(text: str, default: float = 0.5) -> float:
    """从文本中提取置信度."""
    import re
    match = re.search(r"置信度[：:]\s*(0?\.\d+|[01])(?:\s|$)", text)
    if match:
        return float(match.group(1))
    match = re.search(r"confidence[：:]\s*(0?\.\d+|[01])(?:\s|$)", text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return default


def _extract_recommendation(text: str) -> str:
    """从裁判文本中提取投资建议."""
    if "买入" in text or "增持" in text or "buy" in text.lower():
        return "买入"
    if "卖出" in text or "减持" in text or "sell" in text.lower():
        return "卖出"
    return "持有"


def _extract_risk_level(text: str) -> str:
    """从裁判文本中提取风险等级."""
    if "高风险" in text or "风险高" in text:
        return "高"
    if "低风险" in text or "风险低" in text:
        return "低"
    return "中"


# ---------------------------------------------------------------------------
# 多轮对抗式辩论
# ---------------------------------------------------------------------------

MULTI_ROUND_BULL_PROMPT = """你是一位看涨财务分析师，正在参加多轮对抗式辩论。

请基于问题与财务数据，给出 1-3 个看涨论点。每个论点必须严格按以下格式输出：

[论点]
观点: <一句话核心观点>
数据支撑: <引用的具体数据，多条用分号分隔>
置信度: <0-1 之间的数值>

要求：
- 仅基于提供的数据，不得编造数字
- 数据支撑须引用财务数据中的具体数值
- 观点应聚焦增长、优势与正面信号"""

MULTI_ROUND_BEAR_PROMPT = """你是一位看跌财务分析师，正在参加多轮对抗式辩论。

请基于问题与财务数据，给出 1-3 个看跌论点。每个论点必须严格按以下格式输出：

[论点]
观点: <一句话核心观点>
数据支撑: <引用的具体数据，多条用分号分隔>
置信度: <0-1 之间的数值>

要求：
- 仅基于提供的数据，不得编造数字
- 数据支撑须引用财务数据中的具体数值
- 观点应聚焦风险、隐忧与负面信号"""

BULL_REBUTTAL_PROMPT = """你是一位看涨财务分析师，现在需要反驳看跌方的论点。

请针对看跌方的论点逐一反驳，指出其推理的漏洞或对数据的误读。
你的反驳应基于事实数据，保持客观专业。直接输出反驳内容，不要使用格式标签。"""

BEAR_REBUTTAL_PROMPT = """你是一位看跌财务分析师，现在需要反驳看涨方的论点。

请针对看涨方的论点逐一反驳，指出其推理的漏洞或对数据的误读。
你的反驳应基于事实数据，保持客观专业。直接输出反驳内容，不要使用格式标签。"""

JUDGE_MULTI_ROUND_PROMPT = """你是一位中立的财务裁判，正在评判一场多轮对抗式辩论。

你将看到所有轮次的看涨/看跌论点与反驳。请：
1. 对每个论点按三个维度打分（1-10 分）：证据质量、逻辑严密性、相关性
2. 综合判断哪一方更有说服力（bull/bear/tie）
3. 给出最终投资建议（买入/持有/卖出）与风险等级（低/中/高）

请严格按以下格式输出：

[评分]
看涨方平均分: <数值>
看跌方平均分: <数值>

[裁决]
胜方: <bull/bear/tie>
建议: <买入/持有/卖出>
风险: <低/中/高>
置信度: <0-1>

[理由]
<详细说明>"""

ARGUMENT_SCORING_PROMPT = """你是一位严格的财务论点评审专家。

请对每个论点按以下三个维度打分（1-10 分，整数）：
- evidence_quality（证据质量）：是否引用了具体数据，数据是否准确
- logical_rigor（逻辑严密性）：推理是否合理、是否存在逻辑漏洞
- relevance（相关性）：是否切题、与待分析问题相关

对每个论点严格按以下格式输出（编号需与输入对应）：

[论点 1]
evidence_quality: <分数>
logical_rigor: <分数>
relevance: <分数>

[论点 2]
...

不要输出其它内容。"""


def _parse_arguments(text: str, side: str = "") -> list[DebateArgument]:
    """从 LLM 输出文本中解析结构化论点.

    支持格式：
        [论点]
        观点: xxx
        数据支撑: a; b
        置信度: 0.8
    """
    import re

    arguments: list[DebateArgument] = []
    # 按 [论点] 分块
    blocks = re.split(r"\[\s*论点\s*\]", text)
    for block in blocks[1:]:
        point_match = re.search(r"观点[：:]\s*(.+?)(?=\n|$)", block)
        data_match = re.search(r"数据支撑[：:]\s*(.+?)(?=\n|$)", block)
        conf_match = re.search(r"置信度[：:]\s*(0?\.\d+|[01])", block)

        point = point_match.group(1).strip() if point_match else block.strip()
        if not point or len(point) < 3:
            continue
        supporting: list[str] = []
        if data_match:
            raw = data_match.group(1).strip()
            supporting = [s.strip() for s in re.split(r"[;；]", raw) if s.strip()]
        confidence = float(conf_match.group(1)) if conf_match else 0.5
        arguments.append(
            DebateArgument(
                point=point,
                supporting_data=supporting,
                confidence=confidence,
                side=side,
            )
        )

    # 降级：如果未解析到结构化论点，按列表项提取
    if not arguments:
        points = _extract_points(text)
        for p in points:
            arguments.append(DebateArgument(point=p, side=side))

    return arguments[:5]


def _argument_to_dict(arg: DebateArgument) -> dict[str, Any]:
    """将 DebateArgument 转为字典."""
    return {
        "point": arg.point,
        "supporting_data": arg.supporting_data,
        "confidence": arg.confidence,
        "side": arg.side,
    }


def _round_to_dict(round_obj: DebateRound) -> dict[str, Any]:
    """将 DebateRound 序列化为字典."""
    return {
        "round_num": round_obj.round_num,
        "bull_arguments": [_argument_to_dict(a) for a in round_obj.bull_arguments],
        "bear_arguments": [_argument_to_dict(a) for a in round_obj.bear_arguments],
        "bull_rebuttal": round_obj.bull_rebuttal,
        "bear_rebuttal": round_obj.bear_rebuttal,
    }


def _load_role_prompt(key: str, default: str, tenant_id: str | None, db: Any = None) -> str:
    """加载角色提示词，优先 DB，降级到内置默认."""
    if not tenant_id:
        return default
    try:
        from finpilot.services.prompt_loader import get_prompt
        db_prompt = get_prompt(key, tenant_id, db)
        return db_prompt if db_prompt else default
    except Exception:  # noqa: BLE001
        return default


def _fallback_arguments(financial_data: dict[str, Any], side: str) -> list[DebateArgument]:
    """LLM 不可用时的降级论点（基于财务数据规则）."""
    revenue = financial_data.get("revenue")
    net_profit = financial_data.get("net_profit")
    args: list[DebateArgument] = []
    if side == "bull":
        if net_profit is not None and float(net_profit) > 0:
            args.append(
                DebateArgument(
                    point=f"公司净利润为 {float(net_profit):,.2f}，保持盈利能力",
                    supporting_data=[f"净利润 {float(net_profit):,.2f}"],
                    confidence=0.5,
                    side="bull",
                )
            )
        if revenue is not None:
            args.append(
                DebateArgument(
                    point=f"营业收入 {float(revenue):,.2f}，具备收入规模",
                    supporting_data=[f"营业收入 {float(revenue):,.2f}"],
                    confidence=0.4,
                    side="bull",
                )
            )
    else:
        liabilities = financial_data.get("total_liabilities")
        if liabilities is not None and float(liabilities) > 0:
            args.append(
                DebateArgument(
                    point=f"总负债 {float(liabilities):,.2f}，需关注偿债压力",
                    supporting_data=[f"总负债 {float(liabilities):,.2f}"],
                    confidence=0.4,
                    side="bear",
                )
            )
        if not args:
            args.append(
                DebateArgument(
                    point="财务数据存在不确定性，需谨慎评估潜在风险",
                    supporting_data=[],
                    confidence=0.3,
                    side="bear",
                )
            )
    return args


def run_multi_round_debate(
    question: str,
    financial_data: dict[str, Any],
    tenant_id: str | None = None,
    db: Any = None,
    rounds: int = 3,
) -> dict[str, Any]:
    """执行多轮对抗式辩论.

    流程（默认 3 轮）：
    - 第 1 轮：看涨方陈述论点 → 看跌方陈述论点（双方均可见问题与数据）
    - 第 2 轮：看涨方反驳看跌方第 1 轮 → 看跌方反驳看涨方第 1 轮
    - 第 3 轮：看涨方总结陈词 → 看跌方总结陈词
    - 裁判：审阅全部轮次，对论点评分，判定胜方并给出投资建议

    LLM 不可用时降级为基于财务数据的规则论点，保证流程可用。

    Args:
        question: 分析问题
        financial_data: 财务数据字典
        tenant_id: 租户 ID（用于加载 DB 提示词）
        db: 数据库会话（可选，用于提示词加载）
        rounds: 辩论轮数（默认 3）

    Returns:
        包含 rounds / judge_verdict / argument_scores / fact_checks /
        winner / recommendation / final_confidence 的字典
    """
    data_text = _format_data(financial_data)
    bull_prompt = _load_role_prompt("debate_bull_system", MULTI_ROUND_BULL_PROMPT, tenant_id, db)
    bear_prompt = _load_role_prompt("debate_bear_system", MULTI_ROUND_BEAR_PROMPT, tenant_id, db)
    judge_prompt = _load_role_prompt("debate_judge_system", JUDGE_MULTI_ROUND_PROMPT, tenant_id, db)

    rounds_data: list[DebateRound] = []
    bull_r1_args: list[DebateArgument] = []
    bear_r1_args: list[DebateArgument] = []
    all_arguments: list[DebateArgument] = []

    client: LLMClient | None = None
    try:
        client = LLMClient()
    except Exception as exc:  # noqa: BLE001
        logger.warning("multi_round_debate_llm_init_failed", error=str(exc))
        client = None

    def _llm(system: str, user: str) -> str:
        if client is None:
            raise LLMUnavailableError("LLM 客户端未初始化")
        return client.chat(system_prompt=system, user_prompt=user)

    n_rounds = max(int(rounds), 1)

    for round_num in range(1, n_rounds + 1):
        round_obj = DebateRound(round_num=round_num)
        user_prompt_base = f"分析问题：{question}\n\n财务数据：\n{data_text}"

        if round_num == 1:
            # 第 1 轮：双方陈述论点
            try:
                bull_text = _llm(bull_prompt, user_prompt_base)
                round_obj.bull_arguments = _parse_arguments(bull_text, "bull")
                bull_r1_args = list(round_obj.bull_arguments)
            except (LLMUnavailableError, Exception) as exc:  # noqa: BLE001
                logger.warning("multi_round_bull_r1_failed", error=str(exc))
                round_obj.bull_arguments = _fallback_arguments(financial_data, "bull")
                bull_r1_args = list(round_obj.bull_arguments)

            try:
                bear_text = _llm(bear_prompt, user_prompt_base)
                round_obj.bear_arguments = _parse_arguments(bear_text, "bear")
                bear_r1_args = list(round_obj.bear_arguments)
            except (LLMUnavailableError, Exception) as exc:  # noqa: BLE001
                logger.warning("multi_round_bear_r1_failed", error=str(exc))
                round_obj.bear_arguments = _fallback_arguments(financial_data, "bear")
                bear_r1_args = list(round_obj.bear_arguments)

        elif round_num == 2:
            # 第 2 轮：双方互相反驳
            bull_opponent = "\n".join(
                f"- {a.point}" for a in bear_r1_args
            ) or "（看跌方无明确论点）"
            bear_opponent = "\n".join(
                f"- {a.point}" for a in bull_r1_args
            ) or "（看涨方无明确论点）"

            try:
                round_obj.bull_rebuttal = _llm(
                    BULL_REBUTTAL_PROMPT,
                    f"{user_prompt_base}\n\n看跌方论点：\n{bull_opponent}\n\n请逐一反驳上述看跌论点。",
                )
            except (LLMUnavailableError, Exception) as exc:  # noqa: BLE001
                logger.warning("multi_round_bull_rebuttal_failed", error=str(exc))
                round_obj.bull_rebuttal = "（LLM 不可用，无法生成反驳）"

            try:
                round_obj.bear_rebuttal = _llm(
                    BEAR_REBUTTAL_PROMPT,
                    f"{user_prompt_base}\n\n看涨方论点：\n{bear_opponent}\n\n请逐一反驳上述看涨论点。",
                )
            except (LLMUnavailableError, Exception) as exc:  # noqa: BLE001
                logger.warning("multi_round_bear_rebuttal_failed", error=str(exc))
                round_obj.bear_rebuttal = "（LLM 不可用，无法生成反驳）"

        else:
            # 第 3 轮及以后：总结陈词
            try:
                round_obj.bull_rebuttal = _llm(
                    "你是看涨财务分析师，请给出最终总结陈词，重申核心看涨逻辑。",
                    f"{user_prompt_base}\n\n你此前的论点：\n"
                    + "\n".join(f"- {a.point}" for a in bull_r1_args),
                )
            except (LLMUnavailableError, Exception) as exc:  # noqa: BLE001
                logger.warning("multi_round_bull_final_failed", error=str(exc))
                round_obj.bull_rebuttal = "（LLM 不可用，无法生成总结）"

            try:
                round_obj.bear_rebuttal = _llm(
                    "你是看跌财务分析师，请给出最终总结陈词，重申核心看跌逻辑。",
                    f"{user_prompt_base}\n\n你此前的论点：\n"
                    + "\n".join(f"- {a.point}" for a in bear_r1_args),
                )
            except (LLMUnavailableError, Exception) as exc:  # noqa: BLE001
                logger.warning("multi_round_bear_final_failed", error=str(exc))
                round_obj.bear_rebuttal = "（LLM 不可用，无法生成总结）"

        all_arguments.extend(round_obj.bull_arguments)
        all_arguments.extend(round_obj.bear_arguments)
        rounds_data.append(round_obj)

    # 裁判综合评判
    judge_verdict = ""
    winner = "tie"
    recommendation = "持有"
    risk_level = "中"
    final_confidence = 0.5
    bull_avg_score = 0.0
    bear_avg_score = 0.0

    try:
        rounds_summary = "\n\n".join(_round_to_dict(r).__repr__() for r in rounds_data)
        judge_input = f"分析问题：{question}\n\n财务数据：\n{data_text}\n\n辩论轮次记录：\n{rounds_summary}"
        judge_verdict = _llm(judge_prompt, judge_input)

        winner = _extract_winner(judge_verdict)
        recommendation = _extract_recommendation(judge_verdict)
        risk_level = _extract_risk_level(judge_verdict)
        final_confidence = _extract_confidence(judge_verdict, 0.6)
        bull_avg_score, bear_avg_score = _extract_judge_scores(judge_verdict)
    except (LLMUnavailableError, Exception) as exc:  # noqa: BLE001
        logger.warning("multi_round_judge_failed", error=str(exc))
        judge_verdict = f"LLM 不可用，无法完成裁判评判。错误: {exc!s}"
        # 降级：基于置信度比较
        bull_conf = sum(a.confidence for a in bull_r1_args) / len(bull_r1_args) if bull_r1_args else 0.5
        bear_conf = sum(a.confidence for a in bear_r1_args) / len(bear_r1_args) if bear_r1_args else 0.5
        winner = "bull" if bull_conf > bear_conf else ("bear" if bear_conf > bull_conf else "tie")
        final_confidence = 0.3

    # 论点评分
    try:
        argument_scores = score_arguments(all_arguments, question, financial_data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("multi_round_scoring_failed", error=str(exc))
        argument_scores = [_default_score(a) for a in all_arguments]

    # 事实核查
    try:
        fact_checks = check_argument_facts(all_arguments, financial_data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("multi_round_factcheck_failed", error=str(exc))
        fact_checks = []

    return {
        "question": question,
        "rounds": [_round_to_dict(r) for r in rounds_data],
        "judge_verdict": judge_verdict,
        "argument_scores": argument_scores,
        "fact_checks": fact_checks,
        "winner": winner,
        "recommendation": recommendation,
        "risk_level": risk_level,
        "final_confidence": round(final_confidence, 2),
        "bull_average_score": round(bull_avg_score, 2),
        "bear_average_score": round(bear_avg_score, 2),
        "rounds_completed": len(rounds_data),
    }


def score_arguments(
    arguments: list[DebateArgument],
    question: str,
    financial_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """使用 LLM 对每个论点打分.

    评分维度（1-10）：
    - evidence_quality：是否引用具体数据
    - logical_rigor：推理是否严密
    - relevance：是否切题
    - overall_score：加权平均（证据 0.4 / 逻辑 0.4 / 相关 0.2）

    LLM 不可用时降级为基于启发式的默认评分。

    Args:
        arguments: 待评分论点列表
        question: 原始分析问题
        financial_data: 财务数据字典

    Returns:
        每项形如 ``{"argument": {...}, "scores": {...}}`` 的列表
    """
    if not arguments:
        return []

    # 启发式默认分（降级用）
    def _heuristic(arg: DebateArgument) -> dict[str, Any]:
        evidence = 6 if arg.supporting_data else 3
        logic = 5 + int(arg.confidence * 3)
        relevance = 6 if any(
            kw in question for kw in ("分析", "评估", "投资", "风险")
        ) else 5
        overall = evidence * 0.4 + logic * 0.4 + relevance * 0.2
        return {
            "evidence_quality": evidence,
            "logical_rigor": min(max(logic, 1), 10),
            "relevance": relevance,
            "overall_score": round(overall, 2),
        }

    # 尝试 LLM 批量评分
    llm_scores: dict[int, dict[str, Any]] = {}
    try:
        client = LLMClient()
        arg_text = "\n".join(
            f"[论点 {i + 1}] {a.point}（数据支撑: {'; '.join(a.supporting_data) or '无'}）"
            for i, a in enumerate(arguments)
        )
        user_prompt = (
            f"分析问题：{question}\n\n财务数据：{_format_data(financial_data)}\n\n"
            f"待评分论点：\n{arg_text}"
        )
        response = client.chat(system_prompt=ARGUMENT_SCORING_PROMPT, user_prompt=user_prompt)
        llm_scores = _parse_scores(response, len(arguments))
    except (LLMUnavailableError, Exception) as exc:  # noqa: BLE001
        logger.warning("score_arguments_llm_failed", error=str(exc))
        llm_scores = {}

    results: list[dict[str, Any]] = []
    for i, arg in enumerate(arguments):
        scores = llm_scores.get(i)
        if scores is None:
            scores = _heuristic(arg)
        else:
            # 补全 overall_score
            if "overall_score" not in scores:
                overall = (
                    scores.get("evidence_quality", 5) * 0.4
                    + scores.get("logical_rigor", 5) * 0.4
                    + scores.get("relevance", 5) * 0.2
                )
                scores["overall_score"] = round(overall, 2)
        results.append({"argument": _argument_to_dict(arg), "scores": scores})

    return results


def _default_score(arg: DebateArgument) -> dict[str, Any]:
    """论点默认评分（评分失败时使用）."""
    evidence = 6 if arg.supporting_data else 3
    logic = 5
    relevance = 5
    overall = evidence * 0.4 + logic * 0.4 + relevance * 0.2
    return {
        "argument": _argument_to_dict(arg),
        "scores": {
            "evidence_quality": evidence,
            "logical_rigor": logic,
            "relevance": relevance,
            "overall_score": round(overall, 2),
        },
    }


def _parse_scores(text: str, n_args: int) -> dict[int, dict[str, Any]]:
    """从 LLM 评分输出中解析每个论点的分数."""
    import re

    scores: dict[int, dict[str, Any]] = {}
    # 按 [论点 N] 分块
    blocks = re.split(r"\[\s*论点\s*(\d+)\s*\]", text)
    # blocks: [前导, 编号1, 内容1, 编号2, 内容2, ...]
    for i in range(1, len(blocks), 2):
        try:
            idx = int(blocks[i]) - 1
        except (ValueError, IndexError):
            continue
        content = blocks[i + 1] if i + 1 < len(blocks) else ""
        ev = re.search(r"evidence_quality[：:]\s*(\d+(?:\.\d+)?)", content, re.IGNORECASE)
        lg = re.search(r"logical_rigor[：:]\s*(\d+(?:\.\d+)?)", content, re.IGNORECASE)
        rel = re.search(r"relevance[：:]\s*(\d+(?:\.\d+)?)", content, re.IGNORECASE)
        if ev or lg or rel:
            scores[idx] = {
                "evidence_quality": min(max(int(round(float(ev.group(1)))), 1), 10) if ev else 5,
                "logical_rigor": min(max(int(round(float(lg.group(1)))), 1), 10) if lg else 5,
                "relevance": min(max(int(round(float(rel.group(1)))), 1), 10) if rel else 5,
            }
    return scores


def _extract_winner(text: str) -> str:
    """从裁判文本中提取胜方."""
    import re

    match = re.search(r"胜方[：:]\s*(bull|bear|tie|看涨|看跌|平)", text, re.IGNORECASE)
    if match:
        val = match.group(1).lower()
        if "bull" in val or "看涨" in val:
            return "bull"
        if "bear" in val or "看跌" in val:
            return "bear"
        return "tie"
    if "看涨方胜" in text or "看涨胜" in text:
        return "bull"
    if "看跌方胜" in text or "看跌胜" in text:
        return "bear"
    return "tie"


def _extract_judge_scores(text: str) -> tuple[float, float]:
    """从裁判文本中提取看涨/看跌平均分."""
    import re

    bull_match = re.search(r"看涨方平均分[：:]\s*(\d+(?:\.\d+)?)", text)
    bear_match = re.search(r"看跌方平均分[：:]\s*(\d+(?:\.\d+)?)", text)
    bull = float(bull_match.group(1)) if bull_match else 0.0
    bear = float(bear_match.group(1)) if bear_match else 0.0
    return bull, bear


def check_argument_facts(
    arguments: list[DebateArgument],
    financial_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """对每个论点引用的数据点进行事实核查.

    使用正则从论点文本（观点 + 数据支撑）中提取数值，与 financial_data 中的
    实际数值比对：若某数值与某个财务指标的值相等（或近似匹配），则视为正确，
    否则标记为未在数据中找到。

    Args:
        arguments: 待核查论点列表
        financial_data: 实际财务数据字典

    Returns:
        每项形如 ``{"argument": {...}, "fact_check_results": [...]}`` 的列表，
        其中 fact_check_results 元素为 ``{claim, actual_value, is_correct}``
    """
    import re

    # 收集财务数据中的所有数值
    actual_values: list[tuple[str, float]] = []
    for key, val in financial_data.items():
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            actual_values.append((key, float(val)))
        elif isinstance(val, str):
            # 尝试从字符串中解析数值
            for m in re.finditer(r"-?\d+\.?\d*", val):
                try:
                    actual_values.append((key, float(m.group())))
                except ValueError:
                    continue

    def _find_match(num: float) -> tuple[str | None, bool]:
        """查找数值是否匹配某个财务指标."""
        for key, actual in actual_values:
            if abs(num - actual) < 1e-6:
                return key, True
            # 近似匹配：相对误差 < 1%
            if actual != 0 and abs(num - actual) / abs(actual) < 0.01:
                return key, True
            # 忽略量级差异（如 12.5亿 vs 12.5）：仅当整数部分一致且小数接近
            if abs(num - actual) < 0.5 and actual != 0:
                return key, True
        return None, False

    results: list[dict[str, Any]] = []
    for arg in arguments:
        # 合并论点文本与数据支撑
        text_parts = [arg.point] + list(arg.supporting_data)
        combined_text = " ".join(text_parts)

        # 提取所有数值（含百分比、千分位）
        numbers = re.findall(r"-?\d[\d,]*\.?\d*", combined_text)
        fact_check: list[dict[str, Any]] = []
        for num_str in numbers:
            clean = num_str.replace(",", "")
            try:
                num = float(clean)
            except ValueError:
                continue
            # 跳过过小的纯序号（如论点编号 1/2/3）与置信度
            if num in (1.0, 2.0, 3.0) and clean.isdigit() and len(clean) == 1:
                continue
            matched_key, is_correct = _find_match(num)
            fact_check.append(
                {
                    "claim": num_str,
                    "claimed_value": num,
                    "matched_metric": matched_key,
                    "actual_value": (
                        next(
                            (v for k, v in actual_values if k == matched_key),
                            None,
                        )
                        if matched_key
                        else None
                    ),
                    "is_correct": is_correct,
                }
            )
        results.append(
            {
                "argument": _argument_to_dict(arg),
                "fact_check_results": fact_check,
                "correct_count": sum(1 for f in fact_check if f["is_correct"]),
                "total_claims": len(fact_check),
            }
        )

    return results
