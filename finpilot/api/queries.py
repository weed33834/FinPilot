# -*- coding: utf-8 -*-
"""NL2SQL 查询路由。

- POST /        自然语言 -> SQL -> 执行，返回结果集
- POST /nl2sql  同上，但响应包裹 {code, message, data} 并对齐前端 NLQueryResult
- GET  /history 查询历史（从 QueryRecord 表读取，回放完整链路上下文）

每次查询都会落一条 QueryRecord 记录，保存 question/sql/rows/confidence/engine，
建立 自然语言问题→SQL→执行结果→审计 的完整因果链条。
调用 NL2SQLEngine：规则引擎优先，LLM 兜底，SQLSandbox 注入 LIMIT 并校验。
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from finpilot.database.models import Conversation, Message, QueryRecord
from finpilot.text2sql import NL2SQLEngine

from .deps import get_current_user, get_db_session, tenant_of
from .schemas import QueryRequest, QueryResponse

router = APIRouter(prefix="/queries", tags=["queries"])


def _ok(data, message: str = "ok", code: int = 0):
    return {"code": code, "message": message, "data": data}


# 单条查询记录持久化的 rows 截断上限，避免单条记录过大
_MAX_PERSISTED_ROWS = 100
_MAX_PERSISTED_ROW_CHARS = 20000


def _truncate_rows_for_persist(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """裁剪 rows 以便安全落库为 JSON 文本。"""
    out: list[dict[str, Any]] = []
    total_chars = 0
    for row in rows[:_MAX_PERSISTED_ROWS]:
        # 把所有值转成字符串便于序列化
        flat = {k: _coerce_jsonable(v) for k, v in row.items()}
        row_str = json.dumps(flat, ensure_ascii=False, default=str)
        if total_chars + len(row_str) > _MAX_PERSISTED_ROW_CHARS:
            break
        total_chars += len(row_str)
        out.append(flat)
    return out


def _coerce_jsonable(v: Any) -> Any:
    """把 SQLAlchemy Row / Decimal / datetime 等转为 JSON 可序列化值。"""
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    try:
        return float(v)
    except (TypeError, ValueError):
        return str(v)


def _persist_query_record(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    question: str,
    gen_sql: Optional[str],
    executed_sql: Optional[str],
    rows: list[dict[str, Any]],
    confidence: float,
    engine_backend: str,
    duration_ms: int,
    status_: str,
    error_message: Optional[str],
    conversation_id: Optional[int],
) -> Optional[int]:
    """best-effort 落一条 QueryRecord，失败不影响主流程。

    返回记录 id（用于审计关联），失败返回 None。
    """
    try:
        rec = QueryRecord(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            question=question,
            sql_text=executed_sql or gen_sql,
            engine=engine_backend,
            confidence=confidence,
            rows_json=json.dumps(
                _truncate_rows_for_persist(rows),
                ensure_ascii=False,
                default=str,
            ),
            row_count=len(rows),
            status=status_,
            error_message=error_message,
            duration_ms=duration_ms,
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return rec.id
    except Exception:  # noqa: BLE001
        db.rollback()
        return None


def _audit_query(
    db: Session,
    *,
    current_user: dict,
    record_id: Optional[int],
    question: str,
    status_: str,
    row_count: int,
    duration_ms: int,
    error_message: Optional[str],
) -> None:
    """best-effort 审计埋点：把查询事件关联到 QueryRecord 业务对象。"""
    try:
        from finpilot.services.audit_service import log_action

        log_action(
            db,
            action="query_executed",
            resource=f"query:{record_id}" if record_id else "query",
            user=current_user,
            reason=question[:200],
            commit=False,
            target_object_type="query",
            target_object_id=str(record_id) if record_id else None,
            meta={
                "status": status_,
                "row_count": row_count,
                "duration_ms": duration_ms,
                "error": error_message,
            },
        )
    except Exception:  # noqa: BLE001
        pass


def _load_conversation_history(db: Session, conversation_id: Optional[int], limit: int = 6) -> list:
    """板块F（多轮）：按会话加载最近 N 条消息作为 text2sql 上下文。

    返回按时间正序排列的消息列表（role/content）。conversation_id 为空或加载失败时返回 []。
    这些消息会经 NL2SQLEngine.generate_sql(history=...) → rewrite_query + LLM prompt 双注入，
    使"那净利润呢"这类省略问句能结合上文生成正确 SQL。
    """
    if not conversation_id:
        return []
    try:
        msgs = (
            db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
            .all()
        )
        msgs.reverse()  # 转为时间正序
        return msgs
    except Exception:  # noqa: BLE001  历史加载失败不应阻断查询
        return []


@router.post("", response_model=QueryResponse)
def execute_query(
    req: QueryRequest,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """自然语言 -> SQL -> 执行，返回结果集与置信度"""
    tenant_id = tenant_of(current_user)
    user_id = str(current_user["user_id"])
    started = time.time()

    engine = NL2SQLEngine(db)
    # 板块F（多轮）：按会话加载历史，传入 generate_sql 支撑省略问句重写与多轮生成
    history = _load_conversation_history(db, req.conversation_id)
    # 生成一次拿到置信度，避免重复调用 LLM
    gen = engine.generate_sql(req.question, history=history)
    if not gen.sql:
        rec_id = _persist_query_record(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            question=req.question,
            gen_sql=None,
            executed_sql=None,
            rows=[],
            confidence=gen.confidence,
            engine_backend="rule" if gen.confidence > 0 else None,
            duration_ms=int((time.time() - started) * 1000),
            status_="failed",
            error_message=gen.error or "无法生成SQL",
            conversation_id=req.conversation_id,
        )
        _audit_query(
            db,
            current_user=current_user,
            record_id=rec_id,
            question=req.question,
            status_="failed",
            row_count=0,
            duration_ms=int((time.time() - started) * 1000),
            error_message=gen.error or "无法生成SQL",
        )
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
        rec_id = _persist_query_record(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            question=req.question,
            gen_sql=gen.sql,
            executed_sql=None,
            rows=[],
            confidence=gen.confidence,
            engine_backend="rule",
            duration_ms=int((time.time() - started) * 1000),
            status_="blocked",
            error_message=str(exc),
            conversation_id=req.conversation_id,
        )
        _audit_query(
            db,
            current_user=current_user,
            record_id=rec_id,
            question=req.question,
            status_="blocked",
            row_count=0,
            duration_ms=int((time.time() - started) * 1000),
            error_message=str(exc),
        )
        return QueryResponse(
            sql=gen.sql, rows=[], columns=[], explanation=str(exc), confidence=gen.confidence
        )

    # 执行 SQL，结果硬性限制 100 行
    rows: list[dict[str, Any]] = []
    columns: list[str] = []
    error_message: Optional[str] = None
    status_ = "success"
    try:
        res = db.execute(text(sql))
        rows = [dict(r._mapping) for r in res.fetchall()][:100]
        columns = list(res.keys())
    except SQLAlchemyError as exc:
        error_message = f"执行失败: {exc}"
        status_ = "failed"

    duration_ms = int((time.time() - started) * 1000)
    rec_id = _persist_query_record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        question=req.question,
        gen_sql=gen.sql,
        executed_sql=sql,
        rows=rows,
        confidence=gen.confidence,
        engine_backend="rule",
        duration_ms=duration_ms,
        status_=status_,
        error_message=error_message,
        conversation_id=req.conversation_id,
    )
    _audit_query(
        db,
        current_user=current_user,
        record_id=rec_id,
        question=req.question,
        status_=status_,
        row_count=len(rows),
        duration_ms=duration_ms,
        error_message=error_message,
    )

    return QueryResponse(
        sql=sql,
        rows=rows,
        columns=columns,
        explanation=gen.explanation if error_message is None else error_message,
        confidence=gen.confidence,
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
    tenant_id = tenant_of(current_user)
    user_id = str(current_user["user_id"])
    started = time.time()
    engine = NL2SQLEngine(db)
    # 板块F（多轮）：按会话加载历史
    history = _load_conversation_history(db, req.conversation_id)
    gen = engine.generate_sql(req.question, history=history)

    # 无法生成 SQL
    if not gen.sql:
        rec_id = _persist_query_record(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            question=req.question,
            gen_sql=None,
            executed_sql=None,
            rows=[],
            confidence=gen.confidence,
            engine_backend="rule" if gen.confidence > 0 else None,
            duration_ms=int((time.time() - started) * 1000),
            status_="failed",
            error_message=gen.error or "无法生成SQL",
            conversation_id=req.conversation_id,
        )
        _audit_query(
            db,
            current_user=current_user,
            record_id=rec_id,
            question=req.question,
            status_="failed",
            row_count=0,
            duration_ms=int((time.time() - started) * 1000),
            error_message=gen.error or "无法生成SQL",
        )
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
        rec_id = _persist_query_record(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            question=req.question,
            gen_sql=gen.sql,
            executed_sql=None,
            rows=[],
            confidence=gen.confidence,
            engine_backend="rule",
            duration_ms=int((time.time() - started) * 1000),
            status_="blocked",
            error_message=str(exc),
            conversation_id=req.conversation_id,
        )
        _audit_query(
            db,
            current_user=current_user,
            record_id=rec_id,
            question=req.question,
            status_="blocked",
            row_count=0,
            duration_ms=int((time.time() - started) * 1000),
            error_message=str(exc),
        )
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
    rows: list[dict[str, Any]] = []
    error: Optional[str] = None
    status_ = "success"
    try:
        res = db.execute(text(sql))
        rows = [dict(r._mapping) for r in res.fetchall()][:100]
    except SQLAlchemyError as exc:
        rows = []
        error = f"执行失败: {exc}"
        status_ = "failed"

    duration_ms = int((time.time() - started) * 1000)
    rec_id = _persist_query_record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        question=req.question,
        gen_sql=gen.sql,
        executed_sql=sql,
        rows=rows,
        confidence=gen.confidence,
        engine_backend="rule",
        duration_ms=duration_ms,
        status_=status_,
        error_message=error,
        conversation_id=req.conversation_id,
    )
    _audit_query(
        db,
        current_user=current_user,
        record_id=rec_id,
        question=req.question,
        status_=status_,
        row_count=len(rows),
        duration_ms=duration_ms,
        error_message=error,
    )

    return _ok({
        "question": req.question,
        "sql": sql,
        "data": rows,
        "execution_time_ms": duration_ms,
        "confidence": gen.confidence,
        "backend": "rule",
        "explanation": gen.explanation,
        "error": error,
    })


@router.get("/history")
def query_history(
    skip: int = 0,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """查询历史：优先从 QueryRecord 读取完整链路记录。

    QueryRecord 表为空时（旧数据），回退到从会话 user 消息中提取。
    """
    tenant_id = tenant_of(current_user)
    records = (
        db.query(QueryRecord)
        .filter(QueryRecord.tenant_id == tenant_id)
        .order_by(QueryRecord.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    if records:
        return [
            {
                "id": r.id,
                "question": r.question,
                "sql": r.sql_text,
                "status": r.status,
                "row_count": r.row_count,
                "confidence": r.confidence,
                "engine": r.engine,
                "error": r.error_message,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]

    # 回退：旧数据从 Message 表提取
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
