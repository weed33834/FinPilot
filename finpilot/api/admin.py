# -*- coding: utf-8 -*-
"""管理后台路由。

- GET /dashboard  返回平台统计数据（需管理员）
- GET /health     健康检查（无需认证）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from finpilot.database.models import Conversation, Document, Message

from .deps import get_db_session, require_admin
from .schemas import DashboardResponse

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/health")
def health():
    """健康检查（无需认证）"""
    return {"status": "ok"}


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """返回平台统计数据"""
    documents_count = db.query(Document).count()
    conversations_count = db.query(Conversation).count()
    # 以 user 角色消息数作为查询量近似
    queries_count = db.query(Message).filter(Message.role == "user").count()
    # 研报数从 FinPilot equity 数据库读取
    reports_count = _count_reports()
    return DashboardResponse(
        documents_count=documents_count,
        reports_count=reports_count,
        conversations_count=conversations_count,
        queries_count=queries_count,
    )


def _count_reports() -> int:
    """统计 FinPilot equity 研报请求数（表未初始化时返回 0）"""
    try:
        from finpilot_equity.web_app.database.connection import (
            SessionLocal as FinPilotSessionLocal,
        )
        from finpilot_equity.web_app.database.models import ReportRequest

        fp_db = FinPilotSessionLocal()
        try:
            return fp_db.query(ReportRequest).count()
        finally:
            fp_db.close()
    except (ImportError, SQLAlchemyError):
        return 0
