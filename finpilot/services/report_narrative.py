"""报告 LLM 叙事层 — 确定性计算 + LLM 解读分离.

核心理念：
- 财务数字由纯 Python 计算，保证 100% 准确
- LLM 只负责"解读数字"：趋势分析、同比环比、异常检测、风险提示
- 叙事结果附在报告 content.narrative 字段，与数字分离展示
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from finpilot.llm.client import LLMClient
from finpilot.llm import LLMUnavailableError

logger = logging.getLogger(__name__)

# 叙事分析系统提示词
NARRATIVE_SYSTEM_PROMPT = """你是一位专业的财务分析师，擅长解读财务报表数据。

请基于以下财务数据，撰写一份结构化的财务分析叙事，包含：

1. **整体表现**：用 2-3 句话概括该期间的整体财务状况。
2. **关键指标解读**：对营收、利润、资产负债率等核心指标做简要分析。
3. **同比/环比变化**：如果有多期数据，分析变化趋势（增长率、变化方向）。
4. **风险提示**：识别潜在的财务风险点（如负债率过高、现金流为负等）。
5. **亮点与关注**：本期数据中的亮点和需持续关注的指标。

要求：
- 语言专业但易懂，适合管理层阅读
- 数字引用必须与提供的数据完全一致，不得编造
- 如数据不完整，明确指出"因数据缺失，无法分析"
- 控制在 300-500 字

请以 JSON 格式输出：
{
  "overview": "整体表现描述",
  "key_metrics": "关键指标解读",
  "trend_analysis": "同比/环比变化分析",
  "risk_alerts": "风险提示",
  "highlights": "亮点与关注",
  "confidence": 0.85
}
"""

NARRATIVE_USER_TEMPLATE = """请分析以下财务数据：

报告类型：{report_type}
期间：{period_label}
{data_text}

请生成结构化的财务分析叙事。"""


def _format_financial_data(data: dict[str, Any]) -> str:
    """将财务数据格式化为 LLM 可读的文本."""
    lines: list[str] = []

    if "sections" in data:
        # 多期对比报告
        for section in data["sections"]:
            name = section.get("name", "")
            value = section.get("value", 0)
            lines.append(f"- {name}: {value:,.2f}")
    else:
        # 单期报告
        metric_labels = {
            "revenue": "营业收入",
            "operating_cost": "营业成本",
            "operating_profit": "营业利润",
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

    # 如果有图表数据（多期对比），也包含进来
    if "chart" in data and "series" in data["chart"]:
        lines.append("\n多期对比数据：")
        for series in data["chart"]["series"]:
            name = series.get("name", "")
            data_points = series.get("data", [])
            values = [f"{dp['label']}: {dp['value']:,.2f}" for dp in data_points]
            lines.append(f"- {name}: {', '.join(values)}")

    return "\n".join(lines)


def _calculate_confidence(data: dict[str, Any]) -> float:
    """基于数据完整度计算置信度.

    Returns:
        0.0-1.0 的置信度分数
    """
    # 检查核心指标是否齐全
    core_metrics = ["revenue", "net_profit", "total_assets", "total_liabilities"]
    if "sections" in data:
        # 多期对比报告
        sections = data.get("sections", [])
        filled = sum(1 for s in sections if s.get("value", 0) != 0)
        completeness = filled / max(len(sections), 1)
    else:
        filled = sum(1 for m in core_metrics if data.get(m) is not None and float(data[m]) != 0)
        completeness = filled / len(core_metrics)

    # 基础置信度 0.5 + 数据完整度 * 0.4
    confidence = 0.5 + completeness * 0.4
    return round(min(confidence, 0.95), 2)


def generate_narrative(
    report_type: str,
    content: dict[str, Any],
    tenant_id: str | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    """为报告生成 LLM 叙事分析.

    Args:
        report_type: 报告类型 (profit/balance/cash/comparison/custom)
        content: 报告结构化数据（由 ReportGenerator.generate 产生）
        tenant_id: 租户 ID（用于从 DB 加载提示词）
        db: 数据库会话

    Returns:
        包含 narrative 字段的字典，结构为：
        {
            "overview": "...",
            "key_metrics": "...",
            "trend_analysis": "...",
            "risk_alerts": "...",
            "highlights": "...",
            "confidence": 0.85,
            "source": "llm" | "fallback"
        }
    """
    period_label = content.get("period_label", content.get("period", ""))
    data_text = _format_financial_data(content)
    base_confidence = _calculate_confidence(content)

    # 尝试用 DB 提示词
    system_prompt = NARRATIVE_SYSTEM_PROMPT
    if tenant_id and db:
        try:
            from finpilot.services.prompt_loader import get_prompt
            db_prompt = get_prompt("report_narrative_system", tenant_id, db)
            if db_prompt:
                system_prompt = db_prompt
        except Exception:  # noqa: BLE001
            pass

    user_prompt = NARRATIVE_USER_TEMPLATE.format(
        report_type=report_type,
        period_label=period_label,
        data_text=data_text,
    )

    try:
        client = LLMClient()
        raw = client.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        # 尝试解析 JSON
        import re
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            narrative = json.loads(match.group(0))
            narrative["source"] = "llm"
            # 确保 confidence 在合理范围
            if "confidence" not in narrative or not isinstance(narrative["confidence"], int | float):
                narrative["confidence"] = base_confidence
            return narrative

        # JSON 解析失败，用原始文本作为 overview
        return {
            "overview": raw[:500],
            "key_metrics": "",
            "trend_analysis": "",
            "risk_alerts": "",
            "highlights": "",
            "confidence": base_confidence,
            "source": "llm_text",
        }

    except (LLMUnavailableError, Exception) as exc:  # noqa: BLE001
        logger.warning("narrative_llm_failed", error=str(exc))
        # 降级：用规则生成基础叙事
        return _fallback_narrative(content, base_confidence)


def _fallback_narrative(content: dict[str, Any], confidence: float) -> dict[str, Any]:
    """规则降级叙事 — 当 LLM 不可用时用简单规则生成."""
    overview_parts: list[str] = []

    if "sections" in content:
        # 多期对比
        sections = content["sections"]
        for s in sections:
            name = s.get("name", "")
            val = s.get("value", 0)
            if val:
                overview_parts.append(f"{name}为 {val:,.2f}")
    else:
        revenue = content.get("revenue", 0)
        net_profit = content.get("net_profit", 0)
        if revenue:
            overview_parts.append(f"营业收入 {float(revenue):,.2f}")
        if net_profit:
            overview_parts.append(f"净利润 {float(net_profit):,.2f}")

    overview = "本期" + "，".join(overview_parts) + "。" if overview_parts else "数据不足，无法生成分析。"

    # 风险检测
    risks: list[str] = []
    total_assets = float(content.get("total_assets") or 0)
    total_liabilities = float(content.get("total_liabilities") or 0)
    if total_assets > 0 and total_liabilities > 0:
        debt_ratio = total_liabilities / total_assets
        if debt_ratio > 0.7:
            risks.append(f"资产负债率 {debt_ratio:.1%}，高于 70% 警戒线")

    cash_flow = float(content.get("cash_flow_operating") or 0)
    if cash_flow < 0:
        risks.append("经营活动现金流为负，需关注现金流动性")

    return {
        "overview": overview,
        "key_metrics": "详见上方财务数据表格。",
        "trend_analysis": "需多期数据对比才能分析趋势。",
        "risk_alerts": "；".join(risks) if risks else "未发现明显风险。",
        "highlights": "",
        "confidence": confidence,
        "source": "fallback",
    }
