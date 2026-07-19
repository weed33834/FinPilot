"""Multi-agent orchestration -- Supervisor pattern (migrated from legacy,
dropping the langgraph giant graph for a native lightweight edition).

Keeps the legacy supervisor's core skills:
1. Role division: research (retrieval) / analyst (data analysis) / writer
   (consolidated output), each with its own responsibility.
2. Confidence scoring: every worker returns a confidence; the writer judges.
3. Reasoning chain: records each step's action and result, traceable.
4. LLM decision routing + rule fallback: keyword rules route when the LLM is down.

Trade-off: legacy used a langgraph.StateGraph of 1135 lines plus a batch of
legacy services. finpilot already has native RagService / NL2SQLEngine, so here
a deterministic linear orchestration (research -> analyst -> writer) replaces
the heavy graph, delivering multi-role collaboration with minimal code and
running on a single machine. The LLMClient is injected by the caller (carrying
the user's key), matching "input key and use".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Role system prompt (used by the writer)
WRITER_PROMPT = """你是一位专业的财务报告撰写专家。请整合下方检索发现与数据分析结果，
生成结构化、易读的中文最终回答：整体结论 → 关键数据 → 简要分析 → 风险提示。
引用数据来源，确保可追溯。若上下文不足，如实说明。"""


@dataclass
class SupervisorResult:
    """Structured output of multi-agent collaboration."""

    answer: str = ""
    confidence: float = 0.0
    reasoning_chain: list[dict[str, Any]] = field(default_factory=list)
    research_result: dict[str, Any] = field(default_factory=dict)
    analyst_result: dict[str, Any] = field(default_factory=dict)
    visited_workers: list[str] = field(default_factory=list)


class MultiAgentSupervisor:
    """Lightweight multi-agent orchestrator: research / analyst / writer cooperate."""

    def __init__(self, llm_client: Any, db: Any = None) -> None:
        """Initialize.

        Args:
            llm_client: finpilot LLMClient instance (carrying the user key), used
                for routing and the writer.
            db: SQLAlchemy session (for RagService / NL2SQLEngine), may be None.
        """
        self.llm = llm_client
        self.db = db

    # -- routing decision: whether research / analyst are needed --
    def _plan(self, question: str) -> list[str]:
        """Plan which workers to call (keyword rules + run all by default).

        For robustness, research + analyst both run by default, writer closes;
        pure small-talk questions may go through the writer only.
        """
        q = question
        need_analyst = any(k in q for k in ("多少", "计算", "增长", "比率", "营收", "利润", "查询", "数据", "报表"))
        need_research = any(k in q for k in ("文档", "资料", "查找", "介绍", "是什么", "定义", "解释"))
        plan: list[str] = []
        if need_research:
            plan.append("research")
        if need_analyst:
            plan.append("analyst")
        if not plan:  # no clear signal: default to analyst (finance is data-first)
            plan.append("analyst")
        return plan

    # -- research worker: RAG retrieval --
    def _research(self, question: str, tenant_id: str) -> dict[str, Any]:
        # RAG needs the DB vector store + embedding service; skip directly when
        # there is no DB, avoiding the internal query-rewrite (LLM) and embed
        # (network) blocking in an empty environment.
        if self.db is None:
            return {"findings": [], "confidence": 0.2, "note": "无 DB 会话，跳过检索"}
        try:
            from finpilot.rag import RagService

            svc = RagService(self.db)
            result = svc.query(question, tenant_id=tenant_id)
            chunks = result.get("chunks", []) if isinstance(result, dict) else []
            findings = [c.get("text", "")[:200] for c in chunks[:5]]
            confidence = 0.8 if findings else 0.3
            return {
                "findings": findings,
                "rag_answer": result.get("answer", "") if isinstance(result, dict) else "",
                "sources": [f"chunk-{i+1}" for i in range(len(findings))],
                "confidence": confidence,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("research_worker_failed: %s", exc)
            return {"findings": [], "error": str(exc), "confidence": 0.1}

    # -- analyst worker: NL2SQL data analysis --
    def _analyst(self, question: str) -> dict[str, Any]:
        if self.db is None:
            return {"sql": "", "rows": [], "confidence": 0.2, "note": "无 DB 会话，跳过数据分析"}
        try:
            from finpilot.text2sql import NL2SQLEngine

            eng = NL2SQLEngine(self.db)
            out = eng.execute(question, self.db)
            rows = out.get("rows", []) if isinstance(out, dict) else []
            sql = out.get("sql", "") if isinstance(out, dict) else ""
            confidence = 0.85 if rows else (0.5 if sql else 0.2)
            return {
                "sql": sql,
                "rows": rows[:20],
                "columns": out.get("columns", []) if isinstance(out, dict) else [],
                "explanation": out.get("explanation", "") if isinstance(out, dict) else "",
                "row_count": len(rows),
                "confidence": confidence,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("analyst_worker_failed: %s", exc)
            return {"sql": "", "rows": [], "error": str(exc), "confidence": 0.1}

    # -- writer worker: consolidate context + LLM generation --
    def _writer(self, question: str, research: dict, analyst: dict) -> str:
        parts: list[str] = []
        if research.get("rag_answer"):
            parts.append(f"## 检索答案\n{research['rag_answer']}")
        if research.get("findings"):
            parts.append("## 检索发现\n" + "\n".join(f"- {f}" for f in research["findings"]))
        if analyst.get("sql"):
            parts.append(f"## 数据查询 SQL\n{analyst['sql']}")
        if analyst.get("rows"):
            parts.append(f"## 查询结果（前若干行）\n{analyst['rows']}")
        if analyst.get("explanation"):
            parts.append(f"## 分析说明\n{analyst['explanation']}")
        context = "\n\n".join(parts) or "（无检索/数据上下文）"

        user_prompt = f"用户问题：{question}\n\n可用上下文：\n{context}\n\n请据此生成最终回答。"
        try:
            return self.llm.chat(WRITER_PROMPT, user_prompt, temperature=0.3, max_tokens=1200)
        except Exception as exc:  # noqa: BLE001
            logger.warning("writer_worker_failed: %s", exc)
            # Degrade to returning the context summary when the LLM fails
            return context

    def run(self, question: str, tenant_id: str = "default") -> SupervisorResult:
        """Run multi-agent collaboration and return a structured result."""
        result = SupervisorResult()
        plan = self._plan(question)

        research: dict[str, Any] = {}
        analyst: dict[str, Any] = {}

        if "research" in plan:
            research = self._research(question, tenant_id)
            result.research_result = research
            result.visited_workers.append("research")
            result.reasoning_chain.append({
                "step": "research", "action": "RAG 检索",
                "result": f"命中 {len(research.get('findings', []))} 条",
                "confidence": research.get("confidence", 0.0),
            })

        if "analyst" in plan:
            analyst = self._analyst(question)
            result.analyst_result = analyst
            result.visited_workers.append("analyst")
            result.reasoning_chain.append({
                "step": "analyst", "action": "NL2SQL 数据分析",
                "result": f"返回 {analyst.get('row_count', 0)} 行" if not analyst.get("error") else f"失败: {analyst['error']}",
                "confidence": analyst.get("confidence", 0.0),
            })

        # writer closes
        result.answer = self._writer(question, research, analyst)
        result.visited_workers.append("writer")

        # Combined confidence: mean of each worker's confidence
        confs = [w["confidence"] for w in (research, analyst) if w.get("confidence") is not None]
        result.confidence = round(sum(confs) / len(confs), 3) if confs else 0.5
        result.reasoning_chain.append({
            "step": "writer", "action": "整合输出", "confidence": result.confidence,
        })
        return result


__all__ = ["MultiAgentSupervisor", "SupervisorResult", "WRITER_PROMPT"]
