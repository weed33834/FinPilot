# -*- coding: utf-8 -*-
"""
NL2SQL 统一入口
- NL2SQLResult 结果数据类
- NL2SQLEngine 双引擎调度：规则引擎优先，LLM 兜底
- 提供 SQL 生成 / 执行 / 自修复 / 结果摘要
"""
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from finpilot.llm.client import LLMUnavailableError

from .schema import FINANCIAL_TABLES, build_schema_context
from .sandbox import SQLSandbox
from .rewrite import rewrite_query


@dataclass
class NL2SQLResult:
    """NL2SQL 生成结果"""
    sql: str = ""
    confidence: float = 0.0
    backend: str = ""          # rule / llm
    explanation: str = ""
    error: str = ""
    params: dict = field(default_factory=dict)


# 必须在导入 RuleBasedEngine / LLMEngine 之前定义 NL2SQLResult，
# 以避免与子引擎模块的循环导入（子引擎会反向 import NL2SQLResult）
from .rule_engine import RuleBasedEngine          # noqa: E402
from .llm_engine import LLMEngine, _get_client, _extract_sql  # noqa: E402


class NL2SQLEngine:
    """NL2SQL 双引擎：规则引擎优先匹配，LLM 兜底生成"""

    def __init__(self, db: Optional[Session] = None) -> None:
        self.db = db
        self.rule_engine = RuleBasedEngine()
        self.llm_engine = LLMEngine()
        # 沙箱使用财务表白名单
        self.sandbox = SQLSandbox(list(FINANCIAL_TABLES.keys()))

    def generate_sql(self, question: str, history: Optional[list] = None) -> NL2SQLResult:
        """规则引擎优先；confidence>0.5 直接返回，否则走 LLM；LLM 失败回退规则结果。

        板块F（多轮）：history 非空时，先用 rewrite_query 把省略问题重写为自包含问题，
        再喂给规则引擎 / LLM；LLM 路径同时把 history 注入 prompt。LLM 不可用时 rewrite 降级为原问题。
        """
        # 多轮：基于历史重写当前问题（LLM 不可用/无历史时原样返回）
        resolved = rewrite_query(question, history, db=self.db) if history else question

        rule_result = self.rule_engine.generate_sql(resolved)
        if rule_result.confidence > 0.5:
            return rule_result

        # 规则引擎无法匹配，走 LLM（带 history）
        llm_result = self.llm_engine.generate_sql(resolved, db=self.db, history=history)
        if llm_result.confidence > 0:
            return llm_result

        # LLM 失败时返回规则引擎结果（即便 confidence=0）
        return rule_result

    def execute(self, question: str, db: Session, history: Optional[list] = None) -> dict:
        """生成 SQL -> 沙箱 prepare -> 执行，返回 {sql, rows, columns, explanation}

        板块F：支持多轮，history 经 rewrite_query + LLM prompt 双路径注入。
        """
        result = self.generate_sql(question, history=history)
        if not result.sql:
            return {
                "sql": "",
                "rows": [],
                "columns": [],
                "explanation": result.explanation or result.error or "无法生成SQL",
            }

        # 沙箱校验 + 注入 LIMIT 100
        try:
            sql = self.sandbox.prepare(result.sql, max_rows=100)
        except ValueError as exc:
            return {"sql": result.sql, "rows": [], "columns": [], "explanation": str(exc)}

        # 执行 SQL，结果硬性限制 100 行
        try:
            res = db.execute(text(sql))
            rows = [dict(row._mapping) for row in res.fetchall()][:100]
            columns = list(res.keys())
        except SQLAlchemyError as exc:  # 执行失败属于可预期运行时错误
            return {"sql": sql, "rows": [], "columns": [], "explanation": f"执行失败: {exc}"}

        return {
            "sql": sql,
            "rows": rows,
            "columns": columns,
            "explanation": result.explanation,
        }

    def refine(
        self,
        question: str,
        failed_sql: str,
        error: str,
        db: Optional[Session] = None,
        history: Optional[list] = None,
    ) -> NL2SQLResult:
        """SQL 自修复：回灌错误信息让 LLM 修正"""
        client = _get_client(db)
        if client is None:
            return NL2SQLResult(
                sql=failed_sql, confidence=0.0, backend="llm",
                explanation="LLM不可用，无法修复", error="LLM不可用",
            )

        # 板块F：用 db 绑定 engine 反射 schema
        schema_engine = None
        if db is not None:
            try:
                schema_engine = db.get_bind()
            except Exception:  # noqa: BLE001
                schema_engine = None

        system_prompt = (
            build_schema_context(schema_engine)
            + "\n\n你是 SQL 专家。根据执行错误信息修复下面的 SQL，"
            "只输出修复后的纯 SQL，不要任何解释或 markdown 代码块。"
        )
        user_prompt = (
            f"问题: {question}\n"
            f"错误SQL: {failed_sql}\n"
            f"错误信息: {error}\n"
            f"请输出修复后的纯 SQL。"
        )
        try:
            resp = client.chat(system_prompt, user_prompt, temperature=0.2, max_tokens=1000)
        except LLMUnavailableError as exc:
            return NL2SQLResult(
                sql=failed_sql, confidence=0.0, backend="llm",
                explanation="LLM调用失败", error=str(exc),
            )

        sql = _extract_sql(resp)
        ok, reason = self.sandbox.validate(sql)
        return NL2SQLResult(
            sql=sql,
            confidence=0.85 if ok else 0.0,
            backend="llm",
            explanation="LLM自修复" + ("" if ok else f"(校验未通过: {reason})"),
            error="" if ok else reason,
        )

    def summarize(
        self,
        question: str,
        rows: list,
        columns: list,
        db: Optional[Session] = None,
    ) -> str:
        """查询结果摘要：用 LLM 将结果转为自然语言"""
        client = _get_client(db)
        if client is None:
            return "LLM不可用，无法生成摘要"

        # 行数据截断避免 prompt 过长，最多 50 行
        sample = rows[:50]
        data_lines = [
            ", ".join(f"{c}={r.get(c)}" for c in columns) for r in sample
        ]
        data_text = "\n".join(data_lines) or "(无数据)"

        system_prompt = (
            "你是财务数据分析助手。根据用户问题和查询结果，"
            "用简洁的中文给出结论性摘要，包含关键数值与对比，不要复述全部数据。"
        )
        user_prompt = (
            f"问题: {question}\n"
            f"列: {columns}\n"
            f"数据(共{len(rows)}行，展示前{len(sample)}行):\n{data_text}"
        )
        try:
            return client.chat(system_prompt, user_prompt, temperature=0.3, max_tokens=500)
        except LLMUnavailableError:
            return "LLM不可用，无法生成摘要"
