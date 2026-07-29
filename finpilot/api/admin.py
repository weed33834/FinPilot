# -*- coding: utf-8 -*-
"""管理后台路由。

- GET /dashboard  返回平台统计数据（需管理员）
- GET /health     健康检查（无需认证）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from finpilot.database.models import Conversation, Document, Message, Report

from .deps import get_db_session, require_admin
from .schemas import DashboardResponse

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/health")
def health():
    """健康检查（无需认证）"""
    return {"status": "ok"}


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """返回平台统计数据"""
    documents_count = db.query(Document).count()
    conversations_count = db.query(Conversation).count()
    # 以 user 角色消息数作为查询量近似
    queries_count = db.query(Message).filter(Message.role == "user").count()
    # 研报数：统一从主库 Report 表读取（跨租户汇总，管理员视角）
    reports_count = db.query(Report).count()
    return DashboardResponse(
        documents_count=documents_count,
        reports_count=reports_count,
        conversations_count=conversations_count,
        queries_count=queries_count,
    )
