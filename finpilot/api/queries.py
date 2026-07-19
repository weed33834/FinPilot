# -*- coding: utf-8 -*-
"""NL2SQL 查询路由。

- POST /        自然语言 -> SQL -> 执行，返回结果集
- POST /nl2sql  同上，但响应包裹 {code, message, data} 并对齐前端 NLQueryResult
- GET  /history 查询历史（从会话 user 消息中提取）

调用 NL2SQLEngine：规则引擎优先，LLM 兜底，SQLSandbox 注入 LIMIT 并校验。
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from finpilot.database.models import Conversation, Message
from finpilot.text2sql import NL2SQLEngine

from .deps import get_current_user, get_db_session
from .schemas import QueryRequest, QueryResponse

router = APIRouter(prefix="/queries", tags=["queries"])


def _ok(data, message: str = "ok", code: int = 0):
    return {"code": code, "message": message, "data": data}


@router.post("", response_model=QueryResponse)
def execute_query(
    req: QueryRequest,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """自然语言 -> SQL -> 执行，返回结果集与置信度"""
    engine = NL2SQLEngine(db)
    # 生成一次拿到置信度，避免重复调用 LLM
    gen = engine.generate_sql(req.question)
    if not gen.sql:
        return QueryResponse(
            sql="",
            rows=[],
            columns=[],
            explanation=gen.explanation or gen.error or "无法生成SQL",
            confidence=gen.confidence,
        )

    # 沙箱校验 + 注入 LIMIT 100
    try:
        sql = engine.sandbox.prepare(gen.sql, max_rows=100)
    except ValueError as exc:
        return QueryResponse(
            sql=gen.sql, rows=[], columns=[], explanation=str(exc), confidence=gen.confidence
        )

    # 执行 SQL，结果硬性限制 100 行
    try:
        res = db.execute(text(sql))
        rows = [dict(r._mapping) for r in res.fetchall()][:100]
        columns = list(res.keys())
    except SQLAlchemyError as exc:
        return QueryResponse(
            sql=sql, rows=[], columns=[], explanation=f"执行失败: {exc}", confidence=gen.confidence
        )

    return QueryResponse(
        sql=sql, rows=rows, columns=columns, explanation=gen.explanation, confidence=gen.confidence
    )


@router.post("/nl2sql")
def execute_query_wrapped(
    req: QueryRequest,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """NL2SQL 查询 — 响应包裹 {code, message, data} 并对齐前端 NLQueryResult 结构.

    前端 types/query.ts NLQueryResult:
      { question, sql, data, execution_time_ms, confidence, backend, explanation, error }
    """
    started = time.time()
    engine = NL2SQLEngine(db)
    gen = engine.generate_sql(req.question)

    # 无法生成 SQL
    if not gen.sql:
        return _ok({
            "question": req.question,
            "sql": None,
            "data": [],
            "execution_time_ms": int((time.time() - started) * 1000),
            "confidence": gen.confidence,
            "backend": "rule" if gen.confidence > 0 else None,
            "explanation": gen.explanation or gen.error or "无法生成SQL",
            "error": gen.error,
        })

    # 沙箱校验
    try:
        sql = engine.sandbox.prepare(gen.sql, max_rows=100)
    except ValueError as exc:
        return _ok({
            "question": req.question,
            "sql": gen.sql,
            "data": [],
            "execution_time_ms": int((time.time() - started) * 1000),
            "confidence": gen.confidence,
            "backend": "rule",
            "explanation": str(exc),
            "error": str(exc),
        })

    # 执行
    try:
        res = db.execute(text(sql))
        rows = [dict(r._mapping) for r in res.fetchall()][:100]
        error = None
    except SQLAlchemyError as exc:
        rows = []
        error = f"执行失败: {exc}"

    return _ok({
        "question": req.question,
        "sql": sql,
        "data": rows,
        "execution_time_ms": int((time.time() - started) * 1000),
        "confidence": gen.confidence,
        "backend": "rule",
        "explanation": gen.explanation,
        "error": error,
    })


@router.get("/history")
def query_history(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """查询历史：从当前用户会话的 user 消息中提取"""
    msgs = (
        db.query(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .filter(Conversation.user_id == current_user["user_id"], Message.role == "user")
        .order_by(Message.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": m.id,
            "question": m.content,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in msgs
    ]
