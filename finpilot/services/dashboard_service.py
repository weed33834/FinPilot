"""仪表盘聚合服务 — 为前端 DashboardPage 提供 summary 数据.

返回结构需对齐 ``frontend/src/pages/dashboard/constants.ts`` 中的
``DashboardSummary`` 接口：
- report_count / document_count / pending_approval_count
- recent_reports / recent_documents / recent_activities
- report_status_distribution / document_status_distribution
- approval_trend
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _safe_query(db: Session, model, *filters, limit: int | None = None):
    """安全查询：模型为 None 或异常时返回空列表"""
    if model is None:
        return []
    try:
        q = db.query(model)
        for f in filters:
            q = q.filter(f)
        if limit is not None:
            q = q.limit(limit)
        return q.all()
    except Exception as exc:
        logger.debug("dashboard_safe_query_failed model=%s err=%s", model, exc)
        return []


def _safe_count(db: Session, model, *filters) -> int:
    """安全计数：模型为 None 或异常时返回 0"""
    if model is None:
        return 0
    try:
        q = db.query(func.count(model.id))
        for f in filters:
            q = q.filter(f)
        return int(q.scalar() or 0)
    except Exception as exc:
        logger.debug("dashboard_safe_count_failed model=%s err=%s", model, exc)
        return 0


def _safe_group_count(db: Session, model, column) -> dict[str, int]:
    """安全分组计数：按 column 字段分组统计，返回 {value: count}"""
    if model is None or column is None:
        return {}
    try:
        rows = db.query(column, func.count(model.id)).group_by(column).all()
        return {str(k) if k is not None else "unknown": int(v or 0) for k, v in rows}
    except Exception as exc:
        logger.debug("dashboard_safe_group_count_failed err=%s", exc)
        return {}


def get_dashboard_summary(db: Session, user_id: str) -> dict[str, Any]:
    """聚合用户仪表盘数据 — 字段与前端 DashboardSummary 对齐."""
    # 延迟导入：部分模型可能未定义
    try:
        from finpilot.database.models import (
            Conversation,
            Document,
            Message,
            Report,
            AuditLog,
        )
    except ImportError:
        # 极端兜底：模型全部不可用时返回空结构
        return _empty_summary()

    # Report 统计（用户研报表）
    report_total = _safe_count(db, Report)
    report_pending = _safe_count(db, Report, Report.status == "processing")
    report_reviewing = _safe_count(db, Report, Report.status == "reviewing")
    report_approved = _safe_count(db, Report, Report.status == "approved")
    pending_approval_count = report_reviewing + report_approved

    # Document 统计
    document_count = _safe_count(db, Document)

    # 状态分布
    report_status_distribution = _safe_group_count(db, Report, Report.status)
    document_status_distribution = _safe_group_count(db, Document, Document.status)

    # 最近报告（最多 5 条）
    recent_reports: list[dict[str, Any]] = []
    for r in _safe_query(db, Report, limit=5):
        try:
            # 按创建时间倒序
            recent_reports.append({
                "id": str(r.id),
                "title": r.title or "未命名报告",
                "status": r.status or "draft",
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })
        except Exception:
            continue
    # 手动倒序（_safe_query 未加 order_by）
    recent_reports.reverse()

    # 最近文档（最多 5 条）
    recent_documents: list[dict[str, Any]] = []
    for d in _safe_query(db, Document, limit=5):
        try:
            recent_documents.append({
                "id": str(d.id),
                "filename": d.filename or "未命名文档",
                "status": d.status or "pending",
                "created_at": d.created_at.isoformat() if d.created_at else None,
            })
        except Exception:
            continue
    recent_documents.reverse()

    # 最近活动（从 AuditLog 读取，最多 10 条）
    recent_activities: list[dict[str, Any]] = []
    for log in _safe_query(db, AuditLog, limit=10):
        try:
            recent_activities.append({
                "id": str(log.id),
                "action": log.action or "unknown",
                "resource": "",
                "result": log.status or "ok",
                "created_at": log.created_at.isoformat() if log.created_at else None,
            })
        except Exception:
            continue
    recent_activities.reverse()

    # 审批趋势（近 7 天）— 简单返回空数组，前端会处理
    approval_trend: list[dict[str, Any]] = []

    return {
        "greeting": "欢迎回来",
        "report_count": report_total,
        "pending_approval_count": pending_approval_count,
        "document_count": document_count,
        "recent_reports": recent_reports,
        "recent_documents": recent_documents,
        "recent_activities": recent_activities,
        "report_status_distribution": report_status_distribution or {"draft": 0},
        "document_status_distribution": document_status_distribution or {"pending": 0},
        "approval_trend": approval_trend,
        # 扩展字段
        "processing_query_count": 0,
        "approved_report_count": report_approved,
        "total_approval_count": pending_approval_count,
        "parsed_document_count": _safe_count(db, Document, Document.status == "indexed"),
        "today_query_count": 0,
    }


def _empty_summary() -> dict[str, Any]:
    """模型全部不可用时的兜底返回 — 保证前端不会因 Object.entries(undefined) 崩溃"""
    return {
        "greeting": "欢迎回来",
        "report_count": 0,
        "pending_approval_count": 0,
        "document_count": 0,
        "recent_reports": [],
        "recent_documents": [],
        "recent_activities": [],
        "report_status_distribution": {"draft": 0},
        "document_status_distribution": {"pending": 0},
        "approval_trend": [],
        "processing_query_count": 0,
        "approved_report_count": 0,
        "total_approval_count": 0,
        "parsed_document_count": 0,
        "today_query_count": 0,
    }
