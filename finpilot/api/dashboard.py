"""仪表盘路由 — 用户仪表盘（/dashboard）+ 管理后台仪表盘（/dashboard/admin）.

前端 DashboardPage 调用 ``GET /dashboard/summary`` 获取用户汇总数据。
管理后台统计依赖多个扩展 ORM 模型（AgentConfig/ModelConfig/SearchEngine 等），
这些模型尚未全部定义时，相关统计返回 0 而非报错，保证仪表盘始终可用。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from finpilot.api.deps import get_current_user, get_db_session

# 部分扩展 ORM 模型可能尚未定义；缺失时置为 None，统计查询跳过并返回 0。
try:
    from finpilot.database.models import (  # noqa: F401
        AgentConfig,
        Conversation,
        ModelConfig,
        PromptTemplate,
        SearchEngine,
        Skill,
        Tool,
    )
except ImportError:
    AgentConfig = None  # type: ignore[assignment,misc]
    Conversation = None  # type: ignore[assignment,misc]
    ModelConfig = None  # type: ignore[assignment,misc]
    PromptTemplate = None  # type: ignore[assignment,misc]
    SearchEngine = None  # type: ignore[assignment,misc]
    Skill = None  # type: ignore[assignment,misc]
    Tool = None  # type: ignore[assignment,misc]

# 单独尝试导入 Conversation（核心模型，通常存在）
try:
    from finpilot.database.models import Conversation as _Conversation
    Conversation = _Conversation
except ImportError:
    pass


def _safe_count(db: Session, model: Any, *filters: Any) -> int:
    """安全计数：模型为 None 或查询异常时返回 0。"""
    if model is None:
        return 0
    try:
        q = db.query(func.count(model.id))
        for f in filters:
            q = q.filter(f)
        return q.scalar() or 0
    except Exception:
        return 0


# 用户仪表盘路由（前端 api 客户端 baseURL=/api/v1，最终路径 /api/v1/dashboard/summary）
user_router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

# 管理后台仪表盘路由（/api/v1/dashboard/admin/stats）
router = APIRouter(prefix="/dashboard/admin", tags=["Dashboard Admin"])


@user_router.get("/summary")
def dashboard_summary(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """获取用户仪表盘汇总数据（报表/文档/审批统计、最近活动等）."""
    try:
        from finpilot.services.dashboard_service import get_dashboard_summary

        summary = get_dashboard_summary(
            db, str(current_user.get("user_id", "default"))
        )
    except ImportError:
        summary = {}
    return {
        "code": 0,
        "message": "ok",
        "data": summary,
    }


@router.get("/stats")
def dashboard_stats(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """获取管理后台 Dashboard 统计数据。

    依赖多个扩展 ORM 模型；模型缺失时对应统计返回 0，保证接口始终可用。
    """
    tenant_id = str(current_user.get("user_id", "default"))
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    # 用大 try/except 包裹：任何模型缺失或查询异常都返回全 0 统计，避免 500。
    try:
        def _cnt(model, *filters):
            if model is None:
                return 0
            q = db.query(func.count(model.id))
            for f in filters:
                q = q.filter(f)
            return q.scalar() or 0

        model_total = _cnt(ModelConfig, ModelConfig.tenant_id == tenant_id)
        model_active = _cnt(ModelConfig, ModelConfig.tenant_id == tenant_id, ModelConfig.is_active.is_(True))
        prompt_total = _cnt(PromptTemplate, PromptTemplate.tenant_id == tenant_id)
        prompt_active = _cnt(PromptTemplate, PromptTemplate.tenant_id == tenant_id, PromptTemplate.is_active.is_(True))
        tool_total = _cnt(Tool, Tool.tenant_id == tenant_id)
        tool_active = _cnt(Tool, Tool.tenant_id == tenant_id, Tool.is_active.is_(True))
        skill_total = _cnt(Skill, Skill.tenant_id == tenant_id)
        skill_active = _cnt(Skill, Skill.tenant_id == tenant_id, Skill.is_active.is_(True))
        agent_total = _cnt(AgentConfig, AgentConfig.tenant_id == tenant_id)
        agent_active = _cnt(AgentConfig, AgentConfig.tenant_id == tenant_id, AgentConfig.is_active.is_(True))
        se_total = _cnt(SearchEngine)
        se_active = _cnt(SearchEngine, SearchEngine.is_active.is_(True))
        conv_total = _cnt(Conversation, Conversation.tenant_id == tenant_id) if Conversation else 0
        conv_today = 0
        if Conversation is not None:
            conv_today = (
                db.query(func.count(Conversation.id))
                .filter(Conversation.tenant_id == tenant_id, Conversation.created_at >= today_start)
                .scalar() or 0
            )
    except Exception:
        model_total = model_active = prompt_total = prompt_active = 0
        tool_total = tool_active = skill_total = skill_active = 0
        agent_total = agent_active = se_total = se_active = 0
        conv_total = conv_today = 0

    try:
        db.execute(func.now())
        db_ok = True
    except Exception:
        db_ok = False

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "models": {"total": model_total, "active": model_active, "default": ""},
            "prompts": {"total": prompt_total, "active": prompt_active},
            "tools": {"total": tool_total, "active": tool_active, "builtin": 0, "custom": tool_total},
            "skills": {"total": skill_total, "active": skill_active},
            "agents": {"total": agent_total, "active": agent_active},
            "search_engines": {"total": se_total, "active": se_active, "default": ""},
            "conversations": {"total": conv_total, "today": conv_today},
            "system_health": {"status": "healthy" if db_ok else "degraded", "uptime_hours": 0},
            "recent_conversations": [],
        },
    }
