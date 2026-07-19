# -*- coding: utf-8 -*-
"""运行记录路由 — 设置板块内置日志与运行轨迹模块.

提供运行日志的统计、列表、详情、删除、批量清理、导出能力，
以及"功能模块启用状态"和"问答交互汇总"两个聚合视图。

端点（统一前缀 /runtime-logs）：
- GET    /stats            总览统计（total / today / by_category / by_level / by_source / success_rate / recent_errors）
- GET    /module-status    各功能模块启用状态聚合
- GET    /conversations    问答交互汇总（基于 Conversation + Message 表）
- GET    /export           导出当前筛选范围为 JSON
- GET    /                 列表查询（分页 / 筛选 / 关键字）
- GET    /{log_id}         单条详情
- DELETE /{log_id}         删除单条
- DELETE /                 批量清理（按 category 或 before_days）

⚠️ 路由顺序：路径参数路由 /{log_id} 必须声明在子路径路由之后，否则会吞掉
   /stats、/module-status 等子路径。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from finpilot.api.deps import get_current_user, get_db_session
from finpilot.database.models import (
    Conversation,
    LlmModel,
    LlmProvider,
    McpServerConfig,
    Message,
    PromptTemplate,
    RuntimeLog,
    SandboxConfig,
    Skill,
    Tool,
)

router = APIRouter(prefix="/runtime-logs", tags=["Runtime Logs"])


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _to_str(value: object) -> str | None:
    """安全把 ORM 字段转为字符串（datetime / int / None 统一处理）."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    return str(value)


def _model_to_response(log: RuntimeLog) -> dict[str, Any]:
    """ORM 转 dict 响应，所有 int/datetime 显式转字符串避免 Pydantic ValidationError."""
    payload: Any = None
    if log.payload_json:
        try:
            payload = json.loads(log.payload_json)
        except (json.JSONDecodeError, TypeError):
            payload = log.payload_json
    return {
        "id": str(log.id),
        "tenant_id": log.tenant_id,
        "category": log.category,
        "level": log.level,
        "source": log.source,
        "event": log.event,
        "message": log.message,
        "payload": payload,
        "duration_ms": log.duration_ms,
        "status_code": log.status_code,
        "user_id": _to_str(log.user_id),
        "ip_address": log.ip_address,
        "session_id": log.session_id,
        "success": bool(log.success),
        "created_at": _to_str(log.created_at),
    }


def _apply_filters(
    query,
    *,
    category: str,
    source: str,
    level: str,
    success: str,
    session_id: str,
    keyword: str,
    start_time: str,
    end_time: str,
):
    """共用筛选逻辑：列表查询与导出复用."""
    if category:
        query = query.filter(RuntimeLog.category == category)
    if source:
        query = query.filter(RuntimeLog.source == source)
    if level:
        query = query.filter(RuntimeLog.level == level)
    if success == "true":
        query = query.filter(RuntimeLog.success.is_(True))
    elif success == "false":
        query = query.filter(RuntimeLog.success.is_(False))
    if session_id:
        query = query.filter(RuntimeLog.session_id == session_id)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            (RuntimeLog.message.ilike(like))
            | (RuntimeLog.event.ilike(like))
            | (RuntimeLog.source.ilike(like))
        )
    if start_time:
        try:
            dt_start = datetime.fromisoformat(start_time.replace("T", " "))
            query = query.filter(RuntimeLog.created_at >= dt_start)
        except ValueError:
            pass
    if end_time:
        try:
            dt_end = datetime.fromisoformat(end_time.replace("T", " "))
            query = query.filter(RuntimeLog.created_at <= dt_end)
        except ValueError:
            pass
    return query


# ---------------------------------------------------------------------------
# 子路径路由（必须先于 /{log_id} 声明）
# ---------------------------------------------------------------------------


@router.get("/stats")
def stats(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """总览统计：total / today / by_category / by_level / by_source / success_rate / recent_errors."""
    total = db.query(RuntimeLog).count()
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today = db.query(RuntimeLog).filter(RuntimeLog.created_at >= today_start).count()

    by_category_rows = (
        db.query(RuntimeLog.category, func.count(RuntimeLog.id))
        .group_by(RuntimeLog.category)
        .all()
    )
    by_level_rows = (
        db.query(RuntimeLog.level, func.count(RuntimeLog.id))
        .group_by(RuntimeLog.level)
        .all()
    )
    by_source_rows = (
        db.query(RuntimeLog.source, func.count(RuntimeLog.id))
        .group_by(RuntimeLog.source)
        .all()
    )

    success_count = db.query(RuntimeLog).filter(RuntimeLog.success.is_(True)).count()
    success_rate = round(success_count / total, 4) if total else 0.0

    recent_errors = (
        db.query(RuntimeLog)
        .filter(RuntimeLog.success.is_(False))
        .order_by(RuntimeLog.created_at.desc())
        .limit(10)
        .all()
    )

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "total": total,
            "today": today,
            "by_category": {cat or "unknown": cnt for cat, cnt in by_category_rows},
            "by_level": {lvl or "unknown": cnt for lvl, cnt in by_level_rows},
            "by_source": {src or "unknown": cnt for src, cnt in by_source_rows},
            "success_rate": success_rate,
            "recent_errors": [_model_to_response(e) for e in recent_errors],
        },
    }


@router.get("/module-status")
def module_status(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """聚合各功能模块启用状态（从各资源表统计 is_active）.

    注意：ReportSubscription / ReportTemplate 用 "Y"/"N" 字符串而非 bool，
    为避免类型混乱，这两类不纳入 module-status 统计。
    """
    modules: list[dict[str, Any]] = []
    for name, model, label in [
        ("llm_providers", LlmProvider, "LLM 供应商"),
        ("llm_models", LlmModel, "LLM 模型"),
        ("tools", Tool, "工具"),
        ("skills", Skill, "技能"),
        ("mcp_servers", McpServerConfig, "MCP 服务器"),
        ("sandbox_configs", SandboxConfig, "沙箱配置"),
        ("prompt_templates", PromptTemplate, "提示词模板"),
    ]:
        total = db.query(model).count()
        active = db.query(model).filter(model.is_active == True).count()  # noqa: E712
        modules.append({
            "key": name,
            "label": label,
            "total": total,
            "active": active,
            "inactive": total - active,
        })
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "modules": modules,
            "checked_at": datetime.now().isoformat(sep=" "),
        },
    }


@router.get("/conversations")
def conversations(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """问答交互汇总（基于 Conversation + Message 表）."""
    total_convs = db.query(Conversation).count()
    total_msgs = db.query(Message).count()
    user_msgs = db.query(Message).filter(Message.role == "user").count()
    assistant_msgs = db.query(Message).filter(Message.role == "assistant").count()
    recent = (
        db.query(Message)
        .order_by(Message.created_at.desc())
        .limit(20)
        .all()
    )
    recent_items = [
        {
            "id": str(m.id),
            "conversation_id": str(m.conversation_id),
            "role": m.role,
            "content": (m.content or "")[:200],
            "created_at": m.created_at.isoformat(sep=" ") if m.created_at else None,
        }
        for m in recent
    ]
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "total_conversations": total_convs,
            "total_messages": total_msgs,
            "user_messages": user_msgs,
            "assistant_messages": assistant_msgs,
            "recent": recent_items,
        },
    }


@router.get("/export")
def export_logs(
    category: str = Query(default=""),
    source: str = Query(default=""),
    level: str = Query(default=""),
    success: str = Query(default=""),
    session_id: str = Query(default=""),
    keyword: str = Query(default=""),
    start_time: str = Query(default=""),
    end_time: str = Query(default=""),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """导出当前筛选范围为 JSON（与 list 相同参数）."""
    query = db.query(RuntimeLog)
    query = _apply_filters(
        query,
        category=category,
        source=source,
        level=level,
        success=success,
        session_id=session_id,
        keyword=keyword,
        start_time=start_time,
        end_time=end_time,
    )
    items = query.order_by(RuntimeLog.created_at.desc()).limit(5000).all()
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "exported_at": datetime.now().isoformat(sep=" "),
            "count": len(items),
            "items": [_model_to_response(it) for it in items],
        },
    }


@router.get("")
def list_logs(
    category: str = Query(default=""),
    source: str = Query(default=""),
    level: str = Query(default=""),
    success: str = Query(default=""),
    session_id: str = Query(default=""),
    keyword: str = Query(default=""),
    start_time: str = Query(default=""),
    end_time: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """列表查询（分页 / 筛选 / 关键字）."""
    query = db.query(RuntimeLog)
    query = _apply_filters(
        query,
        category=category,
        source=source,
        level=level,
        success=success,
        session_id=session_id,
        keyword=keyword,
        start_time=start_time,
        end_time=end_time,
    )
    total = query.count()
    items = (
        query.order_by(RuntimeLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "items": [_model_to_response(it) for it in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.delete("")
def batch_clear_logs(
    category: str = Query(default="", description="按分类清理（空则忽略）"),
    before_days: int = Query(default=0, ge=0, description="清理 N 天前的日志（0 表示不按时间清理）"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """批量清理（按 category 或 before_days），返回 {deleted_count}."""
    if not category and not before_days:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请至少提供 category 或 before_days 之一",
        )
    query = db.query(RuntimeLog)
    if category:
        query = query.filter(RuntimeLog.category == category)
    if before_days:
        cutoff = datetime.now() - timedelta(days=before_days)
        query = query.filter(RuntimeLog.created_at < cutoff)
    deleted_count = query.count()
    query.delete(synchronize_session=False)
    db.commit()
    return {
        "code": 0,
        "message": "ok",
        "data": {"deleted_count": deleted_count},
    }


# ---------------------------------------------------------------------------
# 路径参数路由 — 必须在所有子路径路由之后
# ---------------------------------------------------------------------------


@router.get("/{log_id}")
def get_log(
    log_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """单条详情."""
    log = db.get(RuntimeLog, int(log_id)) if log_id.isdigit() else None
    if not log:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="日志不存在")
    return {"code": 0, "message": "ok", "data": _model_to_response(log)}


@router.delete("/{log_id}")
def delete_log(
    log_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """删除单条."""
    log = db.get(RuntimeLog, int(log_id)) if log_id.isdigit() else None
    if not log:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="日志不存在")
    db.delete(log)
    db.commit()
    return {"code": 0, "message": "ok", "data": None}
