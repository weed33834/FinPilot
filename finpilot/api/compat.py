# -*- coding: utf-8 -*-
"""前端契约兼容路由层。

为什么需要这个文件：
- 前端 admin 页面（models.ts / agentConfigs.ts / searchEngines.ts / settings.ts / metrics.ts /
  contextManager.ts）使用的 URL 与 schema 是按更早一版后端写的；
- 现在后端只有 /llm-providers（provider+model 拆表），且没有 agent-configs / search-engines /
  settings / metrics / context 等模块；
- 直接 404 会让前端报“响应错误 / 网络错误”，且无法定位具体哪个端点出问题。

本文件提供三类兼容路由：
1. **适配器**：``/model-configs`` 把 llm_providers + llm_models 拍平成前端期望的扁平 schema，
   并把写操作代理回 llm_providers CRUD；
2. **占位路由**：``/agent-configs`` ``/search-engines`` ``/settings`` ``/metrics/*`` ``/context/*``
   返回空数据或基于 DB 的真实数据，让前端 admin 页能正常渲染而不是 404 崩溃；
3. **别名路由**：把前端调用错路径的请求重定向到正确端点。

为便于维护，原 1600+ 行的 compat.py 已按业务域拆分到：
- :mod:`finpilot.api.agent_configs`  —— ``/agent-configs``
- :mod:`finpilot.api.search_engines` —— ``/search-engines``
- :mod:`finpilot.api.system_settings` —— ``/settings``（含 ``/settings/health``）
- :mod:`finpilot.api.kpi_metrics` —— ``/metrics``
- :mod:`finpilot.api.context_manager` —— ``/context``

本文件仅保留：
- 共享辅助 ``_ok``（向后兼容外部 import）
- ``model_configs_router`` —— 拍平 LlmProvider + LlmModel 的适配器
- ``aliases_router`` —— 错误路径别名重定向
- ``register_compat_routes(api)`` —— 把上述子路由统一挂到主 API router

所有占位路由统一返回 ``{code, message, data}`` 包装，与前端 ``ApiResponse<T>`` 契约一致。
"""
from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from finpilot.database.crud import decode_api_key, encode_api_key
from finpilot.database.models import LlmModel, LlmProvider
from finpilot.llm.config import invalidate_cache

from ._compat_helpers import ok
from .deps import get_current_user, get_db_session, require_admin


# ===========================================================================
# /model-configs —— 拍平 llm_providers + llm_models，对齐前端 ModelConfigItem schema
# ===========================================================================

class ModelConfigCreatePayload(BaseModel):
    """前端 createModelConfig 入参（扁平 schema）"""
    provider: str
    model_name: str
    display_name: Optional[str] = None
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    is_default: bool = False
    is_active: bool = True
    parameters: Optional[dict] = None


class ModelConfigUpdatePayload(BaseModel):
    """前端 updateModelConfig 入参（全部字段可选）"""
    provider: Optional[str] = None
    model_name: Optional[str] = None
    display_name: Optional[str] = None
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None
    parameters: Optional[dict] = None


def _flatten_model_config(p: LlmProvider, m: LlmModel) -> dict:
    """把 (provider, model) 拍平为前端期望的 ModelConfigItem 字段"""
    return {
        "id": f"{p.id}:{m.id}",  # 复合 ID：provider_id:model_id
        "tenant_id": "default",
        "provider": p.name,
        "provider_type": p.provider_type,
        "model_name": m.model_name,
        "display_name": m.display_name or m.model_name,
        "api_base": p.base_url,
        "has_api_key": bool(p.api_key),
        "is_default": p.is_default,
        "is_active": m.is_active and p.is_active,
        "tier": m.tier or "medium",
        # 板块D：读取持久化的 parameters（temperature/max_tokens/top_p）
        "parameters": m.parameters or None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        # 板块D：LlmProvider 已补 updated_at 列
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


model_configs_router = APIRouter(prefix="/model-configs", tags=["model-configs"])


@model_configs_router.get("")
def list_model_configs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    search: str = "",
    provider: str = "",
    is_active: str = "",
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """列出所有 model-configs（拍平 provider+model）。

    支持 search（在 provider/model_name/display_name 中模糊匹配）、provider 过滤、is_active 过滤。
    """
    query = (
        db.query(LlmProvider, LlmModel)
        .join(LlmModel, LlmModel.provider_id == LlmProvider.id)
    )
    if search:
        like = f"%{search}%"
        query = query.filter(
            (LlmProvider.name.ilike(like))
            | (LlmModel.model_name.ilike(like))
            | (LlmModel.display_name.ilike(like))
        )
    if provider:
        query = query.filter(LlmProvider.name == provider)
    if is_active in ("true", "1", "yes"):
        query = query.filter(LlmModel.is_active.is_(True), LlmProvider.is_active.is_(True))
    elif is_active in ("false", "0", "no"):
        query = query.filter(LlmModel.is_active.is_(False))

    total = query.count()
    rows = (
        query.order_by(LlmProvider.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ok({
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_flatten_model_config(p, m) for (p, m) in rows],
    })


@model_configs_router.post("")
def create_model_config(
    payload: ModelConfigCreatePayload,
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """创建 model-config —— 复用已有 provider 或新建 provider，并挂一个 model 到其下。"""
    # 同名 provider 复用
    p = db.query(LlmProvider).filter(LlmProvider.name == payload.provider).first()
    if p is None:
        if payload.is_default:
            db.query(LlmProvider).filter(LlmProvider.is_default.is_(True)).update(
                {LlmProvider.is_default: False}
            )
        p = LlmProvider(
            name=payload.provider,
            provider_type="openai",
            base_url=payload.api_base,
            api_key=encode_api_key(payload.api_key) if payload.api_key else None,
            is_default=payload.is_default,
            is_active=True,
        )
        db.add(p)
        db.flush()
    else:
        # 已存在 provider：补字段（仅当传入新值时）
        if payload.api_base:
            p.base_url = payload.api_base
        if payload.api_key:
            p.api_key = encode_api_key(payload.api_key)
        if payload.is_default and not p.is_default:
            db.query(LlmProvider).filter(LlmProvider.id != p.id, LlmProvider.is_default.is_(True)).update(
                {LlmProvider.is_default: False}
            )
            p.is_default = True

    m = LlmModel(
        provider_id=p.id,
        model_name=payload.model_name,
        display_name=payload.display_name or payload.model_name,
        tier="medium",
        is_active=payload.is_active,
        # 板块D：持久化 parameters（temperature/max_tokens/top_p）
        parameters=payload.parameters,
    )
    db.add(m)
    db.commit()
    db.refresh(p)
    db.refresh(m)
    invalidate_cache()
    return ok(_flatten_model_config(p, m), "模型已创建")


@model_configs_router.put("/{config_id}")
def update_model_config(
    config_id: str,
    payload: ModelConfigUpdatePayload,
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """更新 model-config —— config_id 格式为 ``provider_id:model_id``"""
    p_id, m_id = _split_config_id(config_id)
    p = db.get(LlmProvider, p_id)
    m = db.get(LlmModel, m_id) if p else None
    if not p or not m:
        raise HTTPException(status_code=404, detail=f"模型配置 {config_id} 不存在")

    if payload.provider is not None:
        p.name = payload.provider
    if payload.api_base is not None:
        p.base_url = payload.api_base
    if payload.api_key:
        p.api_key = encode_api_key(payload.api_key)
    if payload.is_default is not None and payload.is_default:
        db.query(LlmProvider).filter(LlmProvider.id != p.id, LlmProvider.is_default.is_(True)).update(
            {LlmProvider.is_default: False}
        )
        p.is_default = True
    if payload.model_name is not None:
        m.model_name = payload.model_name
    if payload.display_name is not None:
        m.display_name = payload.display_name
    if payload.is_active is not None:
        m.is_active = payload.is_active
    # 板块D：持久化 parameters（temperature/max_tokens/top_p）
    if payload.parameters is not None:
        m.parameters = payload.parameters
    db.commit()
    db.refresh(p)
    db.refresh(m)
    invalidate_cache()
    return ok(_flatten_model_config(p, m), "模型已更新")


@model_configs_router.delete("/{config_id}")
def delete_model_config(
    config_id: str,
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """删除 model-config —— 只删 model 不删 provider（避免误删其他配置）"""
    p_id, m_id = _split_config_id(config_id)
    m = db.get(LlmModel, m_id)
    if not m:
        return ok({"id": config_id, "deleted": False}, "模型不存在")
    db.delete(m)
    db.commit()
    invalidate_cache()
    return ok({"id": config_id, "deleted": True}, "已删除")


@model_configs_router.patch("/{config_id}/toggle")
def toggle_model_config(
    config_id: str,
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """切换 model-config 启用/禁用"""
    p_id, m_id = _split_config_id(config_id)
    m = db.get(LlmModel, m_id)
    if not m:
        raise HTTPException(status_code=404, detail=f"模型配置 {config_id} 不存在")
    m.is_active = not m.is_active
    db.commit()
    db.refresh(m)
    p = db.get(LlmProvider, m.provider_id)
    return ok(_flatten_model_config(p, m), "已切换")


@model_configs_router.post("/{config_id}/test")
def test_model_config(
    config_id: str,
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """测试 model-config 连通性 —— 调用 LLMClient.verify_connection"""
    from finpilot.llm.client import LLMClient, LLMUnavailableError
    from finpilot.llm.config import LLMConfig

    p_id, m_id = _split_config_id(config_id)
    p = db.get(LlmProvider, p_id)
    m = db.get(LlmModel, m_id) if p else None
    if not p or not m:
        raise HTTPException(status_code=404, detail=f"模型配置 {config_id} 不存在")

    api_key = decode_api_key(p.api_key) if p.api_key else None
    config = LLMConfig(
        provider_type=p.provider_type,
        base_url=p.base_url,
        api_key=api_key,
        model_name=m.model_name,
        tier=m.tier or "medium",
    )
    start = time.perf_counter()
    try:
        client = LLMClient(config)
        client.verify_connection(max_tokens=8)
        latency_ms = int((time.perf_counter() - start) * 1000)
        return ok({
            "success": True,
            "message": f"连通成功（{latency_ms}ms）",
            "result": f"model={m.model_name} latency={latency_ms}ms",
        })
    except LLMUnavailableError as exc:
        return ok({
            "success": False,
            "message": f"连通失败：{exc}",
            "result": None,
        })
    except Exception as exc:  # noqa: BLE001
        return ok({
            "success": False,
            "message": f"未知异常：{type(exc).__name__}: {exc}",
            "result": None,
        })


@model_configs_router.post("/{config_id}/set-default")
def set_default_model_config(
    config_id: str,
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """设为默认 model-config —— 把对应 provider 标为默认"""
    p_id, m_id = _split_config_id(config_id)
    p = db.get(LlmProvider, p_id)
    if not p:
        raise HTTPException(status_code=404, detail=f"模型配置 {config_id} 不存在")
    db.query(LlmProvider).filter(LlmProvider.id != p.id, LlmProvider.is_default.is_(True)).update(
        {LlmProvider.is_default: False}
    )
    p.is_default = True
    db.commit()
    db.refresh(p)
    m = db.get(LlmModel, m_id)
    invalidate_cache()
    return ok(_flatten_model_config(p, m), "已设为默认")


def _split_config_id(config_id: str) -> tuple[int, int]:
    """把 ``provider_id:model_id`` 拆为 (int, int)；非法格式抛 400 让前端看见具体原因"""
    try:
        p_str, m_str = config_id.split(":", 1)
        return int(p_str), int(m_str)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"非法的模型配置 ID：{config_id}（应为 provider_id:model_id）",
        )


# ===========================================================================
# 别名路由 —— 把前端调用错路径的请求重定向到正确端点
# ===========================================================================

aliases_router = APIRouter(prefix="", tags=["aliases"])


@aliases_router.get("/dashboard/kpi")
def dashboard_kpi_alias(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """前端 dashboard 页调用 /dashboard/kpi，实际后端是 /dashboard/admin/stats"""
    from .dashboard import dashboard_stats
    return dashboard_stats(current_user=current_user, db=db)


@aliases_router.get("/queries/recent")
def queries_recent_alias(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """前端调用 /queries/recent，后端是 /queries/history"""
    from .queries import query_history
    return query_history(skip=0, limit=limit, db=db, current_user=current_user)


@aliases_router.get("/factor-mining/strategies")
def factor_mining_strategies_alias(current_user: dict = Depends(get_current_user)):
    """前端调用 /factor-mining/strategies，后端是 /factor-mining/factor-categories"""
    from .factor_mining import list_factor_categories
    return list_factor_categories(current_user=current_user)


@aliases_router.get("/valuation/models")
def valuation_models_alias(_: dict = Depends(get_current_user)):
    """前端调用 /valuation/models，后端没有该端点 —— 返回内置估值模型列表"""
    return ok([
        {"value": "dcf", "label": "DCF 现金流折现", "description": "自由现金流折现估值"},
        {"value": "ddm", "label": "DDM 股利折现", "description": "稳定股利股票估值"},
        {"value": "comps", "label": "可比公司", "description": "相对估值法"},
        {"value": "monte_carlo", "label": "蒙特卡洛", "description": "概率分布模拟"},
        {"value": "scenario", "label": "情景分析", "description": "多情景估值"},
    ])


@aliases_router.get("/reports/templates")
def reports_templates_alias(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """前端调用 /reports/templates，后端是 /report-templates"""
    from .report_templates import list_templates_api
    return list_templates_api(db=db, current_user=current_user, page=page, page_size=page_size)


# ===========================================================================
# 注册到主 router
# ===========================================================================

def register_compat_routes(api: APIRouter) -> None:
    """把所有兼容路由挂载到主 API router 上。

    包含本文件的 model_configs / aliases，以及拆分到独立模块的
    agent_configs / search_engines / system_settings / kpi_metrics / context_manager。
    """
    # 本地 router
    api.include_router(model_configs_router)
    api.include_router(aliases_router)
    # 拆分出去的子模块 router（懒导入，避免顶层循环依赖）
    from .agent_configs import router as agent_configs_router
    from .context_manager import router as context_router
    from .kpi_metrics import router as metrics_router
    from .search_engines import router as search_engines_router
    from .system_settings import router as settings_router

    api.include_router(agent_configs_router)
    api.include_router(search_engines_router)
    api.include_router(settings_router)
    api.include_router(metrics_router)
    api.include_router(context_router)
