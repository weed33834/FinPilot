# -*- coding: utf-8 -*-
"""前端契约兼容路由层。

为什么需要这个文件：
- 前端 admin 页面（models.ts / agentConfigs.ts / searchEngines.ts / settings.ts / metrics.ts /
  contextManager.ts）使用的 URL 与 schema 是按更早一版后端写的；
- 现在后端只有 /llm-providers（provider+model 拆表），且没有 agent-configs / search-engines /
  settings / metrics / context 等模块；
- 直接 404 会让前端报“响应错误 / 网络错误”，且无法定位具体哪个端点出问题。

本文件提供两类兼容路由：
1. **适配器**：/model-configs 把 llm_providers + llm_models 拍平成前端期望的扁平 schema，
   并把写操作代理回 llm_providers CRUD；
2. **占位路由**：/agent-configs /search-engines /settings /metrics/* /context/* 返回空数据，
   让前端 admin 页能正常渲染“暂无数据”，而不是 404 崩溃。

所有占位路由统一返回 ``{code, message, data}`` 包装，与前端 ApiResponse<T> 契约一致。
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from finpilot.database.connection import engine
from finpilot.database.crud import decode_api_key, encode_api_key
from finpilot.database.models import (
    AgentConfig,
    Conversation,
    LlmModel,
    LlmProvider,
    Memory,
    Message,
    SearchEngine,
    SystemSetting,
)
from finpilot.llm.config import invalidate_cache

from .deps import get_current_user, get_db_session, require_admin

# 模块级 router：在 finpilot/api/router.py 里 include 进 /api/v1
router = APIRouter(prefix="", tags=["compat"])


def _ok(data: Any, message: str = "success") -> dict:
    """统一 {code, message, data} 包装，与前端 DataResponse<T> 对齐"""
    return {"code": 0, "message": message, "data": data}


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
    return _ok({
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
    return _ok(_flatten_model_config(p, m), "模型已创建")


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
    return _ok(_flatten_model_config(p, m), "模型已更新")


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
        return _ok({"id": config_id, "deleted": False}, "模型不存在")
    db.delete(m)
    db.commit()
    invalidate_cache()
    return _ok({"id": config_id, "deleted": True}, "已删除")


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
    return _ok(_flatten_model_config(p, m), "已切换")


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
        return _ok({
            "success": True,
            "message": f"连通成功（{latency_ms}ms）",
            "result": f"model={m.model_name} latency={latency_ms}ms",
        })
    except LLMUnavailableError as exc:
        return _ok({
            "success": False,
            "message": f"连通失败：{exc}",
            "result": None,
        })
    except Exception as exc:  # noqa: BLE001
        return _ok({
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
    return _ok(_flatten_model_config(p, m), "已设为默认")


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
# /agent-configs —— AgentConfig CRUD（对接前端 AgentConfigManagement 页）
#
# 板块D：AgentConfig 已补齐 agent_type / prompt_id / max_iterations / temperature
# 列，前端表单字段全部持久化，不再硬编码回显。
# ===========================================================================

class AgentConfigCreatePayload(BaseModel):
    """前端 createAgentConfig 入参。"""
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    # 板块D：补齐前端 AgentConfigItem 期望字段，全部持久化
    agent_type: Optional[str] = None
    prompt_id: Optional[str] = None
    model_id: Optional[str] = None
    system_prompt: Optional[str] = None
    max_iterations: Optional[int] = None
    temperature: Optional[float] = None
    tool_ids: Optional[list] = None
    skill_ids: Optional[list] = None
    is_active: bool = True


class AgentConfigUpdatePayload(BaseModel):
    """前端 updateAgentConfig 入参（全部字段可选）。"""
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    agent_type: Optional[str] = None
    prompt_id: Optional[str] = None
    model_id: Optional[str] = None
    system_prompt: Optional[str] = None
    max_iterations: Optional[int] = None
    temperature: Optional[float] = None
    tool_ids: Optional[list] = None
    skill_ids: Optional[list] = None
    is_active: Optional[bool] = None


def _tenant_of(user: dict) -> str:
    """从当前用户解析 tenant_id：优先 tenant_id，其次 user_id，兜底 default。"""
    return str(user.get("tenant_id") or user.get("user_id") or "default")


def _parse_int_id(_id: str, label: str = "记录") -> int:
    """把路径参数 _id 解析为 int；非法格式按 404 处理。"""
    try:
        return int(_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=404, detail=f"{label} {_id} 不存在")


def _coerce_model_id(value: Any) -> Optional[int]:
    """把前端传来的 model_id（字符串/整数/空）转为 int 或 None。"""
    if value in (None, "", 0):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"model_id 必须是整数：{value!r}",
        )


def _serialize_agent_config(cfg: AgentConfig) -> dict:
    """把 AgentConfig ORM 对象序列化为前端 AgentConfigItem 字段。"""
    return {
        "id": str(cfg.id),
        "tenant_id": cfg.tenant_id or "default",
        "name": cfg.name,
        "display_name": cfg.display_name or cfg.name,
        "description": cfg.description,
        # 板块D：读取持久化字段（此前硬编码为 react/None/10/0.7）
        "agent_type": cfg.agent_type or "react",
        "model_id": str(cfg.model_id) if cfg.model_id is not None else None,
        "prompt_id": str(cfg.prompt_id) if cfg.prompt_id is not None else None,
        "system_prompt": cfg.system_prompt,
        "max_iterations": cfg.max_iterations if cfg.max_iterations is not None else 10,
        "temperature": cfg.temperature if cfg.temperature is not None else 0.7,
        "is_active": cfg.is_active,
        "tool_ids": cfg.tool_ids or [],
        "skill_ids": cfg.skill_ids or [],
        "created_at": cfg.created_at.isoformat() if cfg.created_at else None,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
    }


def _get_agent_config_or_404(db: Session, _id: str, tenant_id: str) -> AgentConfig:
    """按 id + tenant_id 加载 AgentConfig，未找到抛 404。"""
    pk = _parse_int_id(_id, "Agent 配置")
    cfg = (
        db.query(AgentConfig)
        .filter(AgentConfig.id == pk, AgentConfig.tenant_id == tenant_id)
        .first()
    )
    if not cfg:
        raise HTTPException(status_code=404, detail=f"Agent 配置 {_id} 不存在")
    return cfg


agent_configs_router = APIRouter(prefix="/agent-configs", tags=["agent-configs"])


@agent_configs_router.get("")
def list_agent_configs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    search: str = "",
    agent_type: str = "",
    is_active: str = "",
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """列出当前租户的 Agent 配置，支持分页/搜索/状态过滤。

    板块D：agent_type 已持久化，参与过滤。
    """
    tenant_id = _tenant_of(current_user)
    query = db.query(AgentConfig).filter(AgentConfig.tenant_id == tenant_id)
    if search:
        like = f"%{search}%"
        query = query.filter(
            (AgentConfig.name.ilike(like)) | (AgentConfig.display_name.ilike(like))
        )
    # 板块D：agent_type 真实过滤
    if agent_type:
        query = query.filter(AgentConfig.agent_type == agent_type)
    if is_active in ("true", "1", "yes"):
        query = query.filter(AgentConfig.is_active.is_(True))
    elif is_active in ("false", "0", "no"):
        query = query.filter(AgentConfig.is_active.is_(False))

    total = query.count()
    rows = (
        query.order_by(AgentConfig.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return _ok({
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_serialize_agent_config(c) for c in rows],
    })


@agent_configs_router.get("/types")
def list_agent_types(_: dict = Depends(require_admin)):
    return _ok([
        {"value": "react", "label": "ReAct 智能体", "description": "推理-行动循环，多步工具调用"},
        {"value": "plan_execute", "label": "Plan-Execute", "description": "先规划再执行，适合复杂任务"},
        {"value": "debate", "label": "辩论体", "description": "多 agent 辩论，估值/分析场景"},
    ])


@agent_configs_router.post("")
def create_agent_config(
    payload: AgentConfigCreatePayload,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """创建 Agent 配置。created_by/tenant_id 取自当前用户。"""
    cfg = AgentConfig(
        tenant_id=_tenant_of(current_user),
        name=payload.name,
        display_name=payload.display_name or payload.name,
        description=payload.description,
        agent_type=payload.agent_type or "react",
        prompt_id=_coerce_model_id(payload.prompt_id),
        model_id=_coerce_model_id(payload.model_id),
        system_prompt=payload.system_prompt,
        max_iterations=payload.max_iterations if payload.max_iterations is not None else 10,
        temperature=payload.temperature if payload.temperature is not None else 0.7,
        tool_ids=payload.tool_ids or [],
        skill_ids=payload.skill_ids or [],
        is_active=payload.is_active,
        created_by=current_user.get("user_id"),
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return _ok(_serialize_agent_config(cfg), "Agent 配置已创建")


@agent_configs_router.put("/{_id}")
def update_agent_config(
    _id: str,
    payload: AgentConfigUpdatePayload,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """更新 Agent 配置。"""
    cfg = _get_agent_config_or_404(db, _id, _tenant_of(current_user))
    if payload.name is not None:
        cfg.name = payload.name
    if payload.display_name is not None:
        cfg.display_name = payload.display_name
    if payload.description is not None:
        cfg.description = payload.description
    # 板块D：agent_type / prompt_id / max_iterations / temperature 持久化
    if payload.agent_type is not None:
        cfg.agent_type = payload.agent_type
    if payload.prompt_id is not None:
        cfg.prompt_id = _coerce_model_id(payload.prompt_id)
    if payload.model_id is not None:
        cfg.model_id = _coerce_model_id(payload.model_id)
    if payload.system_prompt is not None:
        cfg.system_prompt = payload.system_prompt
    if payload.max_iterations is not None:
        cfg.max_iterations = payload.max_iterations
    if payload.temperature is not None:
        cfg.temperature = payload.temperature
    if payload.tool_ids is not None:
        cfg.tool_ids = payload.tool_ids
    if payload.skill_ids is not None:
        cfg.skill_ids = payload.skill_ids
    if payload.is_active is not None:
        cfg.is_active = payload.is_active
    db.commit()
    db.refresh(cfg)
    return _ok(_serialize_agent_config(cfg), "Agent 配置已更新")


@agent_configs_router.delete("/{_id}")
def delete_agent_config(
    _id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """删除 Agent 配置。"""
    cfg = _get_agent_config_or_404(db, _id, _tenant_of(current_user))
    db.delete(cfg)
    db.commit()
    return _ok({"id": _id, "deleted": True}, "已删除")


@agent_configs_router.patch("/{_id}/toggle")
def toggle_agent_config(
    _id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """切换 Agent 配置启用/禁用。"""
    cfg = _get_agent_config_or_404(db, _id, _tenant_of(current_user))
    cfg.is_active = not cfg.is_active
    db.commit()
    db.refresh(cfg)
    return _ok(_serialize_agent_config(cfg), "已切换")


@agent_configs_router.post("/{_id}/test")
def test_agent_config(
    _id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """测试 Agent 配置 —— 真实调用 run_agent 验证配置是否生效。

    payload: { message?: string }  缺省用「你好，请简要介绍你能做什么」。
    返回真实运行结果（answer/thinking/耗时），LLM 不可用时降级为规则回复。
    """
    cfg = _get_agent_config_or_404(db, _id, _tenant_of(current_user))
    message = ((payload or {}).get("message") or "").strip() or "你好，请简要介绍你能做什么"
    start = time.perf_counter()

    # 配置完整性预检（缺 system_prompt + model_id 仍允许运行，但给出提示）
    warnings = []
    if not cfg.system_prompt:
        warnings.append("缺少系统提示词，将使用默认 ReAct 提示词")
    if cfg.model_id is None:
        warnings.append("未绑定 LLM 模型，将使用默认档位路由")

    try:
        from finpilot.agent import run_agent

        tenant_id = _tenant_of(current_user)
        result = run_agent(
            question=message,
            tenant_id=tenant_id,
            user_id=str(current_user.get("user_id")),
            db=db,
            conversation_id=None,
            agent_config=cfg,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        steps = result.get("steps") or []
        thinking = steps[0].get("thought", "") if steps else None
        answer = result.get("answer") or ""
        success = bool(answer)
        msg = f"Agent「{cfg.display_name or cfg.name}」运行"
        if warnings:
            msg += "（" + "；".join(warnings) + "）"
        return _ok({
            "success": success,
            "message": msg,
            "thinking": thinking,
            "answer": answer,
            "execution_time_ms": latency_ms,
            "intent": result.get("intent"),
            "confidence": result.get("confidence"),
        })
    except Exception as exc:  # noqa: BLE001
        latency_ms = int((time.perf_counter() - start) * 1000)
        return _ok({
            "success": False,
            "message": f"运行失败: {exc}",
            "thinking": None,
            "answer": None,
            "execution_time_ms": latency_ms,
        })


@agent_configs_router.post("/{_id}/duplicate")
def duplicate_agent_config(
    _id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """复制 Agent 配置 —— 生成一份新配置，名称加 (副本) 后缀，默认禁用。"""
    src = _get_agent_config_or_404(db, _id, _tenant_of(current_user))
    new_cfg = AgentConfig(
        tenant_id=src.tenant_id,
        name=f"{src.name} (副本)",
        display_name=f"{src.display_name or src.name} (副本)",
        description=src.description,
        agent_type=src.agent_type or "react",
        prompt_id=src.prompt_id,
        model_id=src.model_id,
        system_prompt=src.system_prompt,
        max_iterations=src.max_iterations if src.max_iterations is not None else 10,
        temperature=src.temperature if src.temperature is not None else 0.7,
        tool_ids=list(src.tool_ids or []),
        skill_ids=list(src.skill_ids or []),
        is_active=False,  # 副本默认禁用，避免重复生效
        created_by=current_user.get("user_id"),
    )
    db.add(new_cfg)
    db.commit()
    db.refresh(new_cfg)
    return _ok(_serialize_agent_config(new_cfg), "已复制")


# ===========================================================================
# /search-engines —— SearchEngine CRUD（对接前端 SearchEngineManagement 页）
#
# 板块D：SearchEngine 已补齐 tenant_id / extra_params / priority 列并继承
# TenantMixin，前端表单字段全部持久化，不再硬编码回显；api_key 经 encode_api_key 编码。
# ===========================================================================

class SearchEngineCreatePayload(BaseModel):
    """前端 createSearchEngine 入参。"""
    name: str
    engine_type: str = "custom"
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    max_results: Optional[int] = None
    is_default: bool = False
    is_active: bool = True
    # 板块D：extra_params / priority 已持久化
    extra_params: Optional[dict] = None
    priority: Optional[int] = None


class SearchEngineUpdatePayload(BaseModel):
    """前端 updateSearchEngine 入参（全部字段可选）。"""
    name: Optional[str] = None
    engine_type: Optional[str] = None
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    max_results: Optional[int] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None
    extra_params: Optional[dict] = None
    priority: Optional[int] = None


def _serialize_search_engine(se: SearchEngine) -> dict:
    """把 SearchEngine ORM 对象序列化为前端 SearchEngineItem 字段。"""
    return {
        "id": str(se.id),
        # 板块D：读取持久化的 tenant_id（此前硬编码 "default"）
        "tenant_id": se.tenant_id or "default",
        "name": se.name,
        "engine_type": se.engine_type,
        "api_base": se.base_url,
        "has_api_key": bool(se.api_key),
        # 板块D：读取持久化的 extra_params（此前硬编码 None）
        "extra_params": se.extra_params,
        "is_default": se.is_default,
        "is_active": se.is_active,
        # 板块D：读取持久化的 priority（此前硬编码 0）
        "priority": se.priority if se.priority is not None else 0,
        "max_results": se.max_results,
        "created_at": se.created_at.isoformat() if se.created_at else None,
        "updated_at": se.updated_at.isoformat() if se.updated_at else None,
    }


def _get_search_engine_or_404(db: Session, _id: str, tenant_id: Optional[str] = None) -> SearchEngine:
    """按 id（+可选 tenant_id）加载 SearchEngine，未找到抛 404。"""
    pk = _parse_int_id(_id, "搜索引擎")
    q = db.query(SearchEngine).filter(SearchEngine.id == pk)
    if tenant_id:
        q = q.filter(SearchEngine.tenant_id == tenant_id)
    se = q.first()
    if not se:
        raise HTTPException(status_code=404, detail=f"搜索引擎 {_id} 不存在")
    return se


search_engines_router = APIRouter(prefix="/search-engines", tags=["search-engines"])


@search_engines_router.get("")
def list_search_engines(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """列出当前租户的搜索引擎配置（默认的排在前面，再按 priority 升序）。"""
    tenant_id = _tenant_of(current_user)
    rows = (
        db.query(SearchEngine)
        .filter(SearchEngine.tenant_id == tenant_id)
        .order_by(
            SearchEngine.is_default.desc(),
            SearchEngine.priority.asc(),
            SearchEngine.created_at.desc(),
        )
        .all()
    )
    return _ok([_serialize_search_engine(se) for se in rows])


@search_engines_router.get("/types")
def list_search_engine_types(_: dict = Depends(require_admin)):
    return _ok([
        {"value": "bing", "label": "Bing"},
        {"value": "google", "label": "Google"},
        {"value": "duckduckgo", "label": "DuckDuckGo"},
        {"value": "serpapi", "label": "SerpAPI"},
    ])


@search_engines_router.post("")
def create_search_engine(
    payload: SearchEngineCreatePayload,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """创建搜索引擎配置。api_key 经 encode_api_key 编码后存储。"""
    tenant_id = _tenant_of(current_user)
    if payload.is_default:
        db.query(SearchEngine).filter(
            SearchEngine.tenant_id == tenant_id, SearchEngine.is_default.is_(True)
        ).update({SearchEngine.is_default: False})
    se = SearchEngine(
        tenant_id=tenant_id,
        name=payload.name,
        engine_type=payload.engine_type,
        base_url=payload.api_base,
        api_key=encode_api_key(payload.api_key) if payload.api_key else None,
        max_results=payload.max_results if payload.max_results is not None else 10,
        is_active=payload.is_active,
        is_default=payload.is_default,
        # 板块D：持久化 extra_params / priority
        extra_params=payload.extra_params,
        priority=payload.priority if payload.priority is not None else 0,
    )
    db.add(se)
    db.commit()
    db.refresh(se)
    return _ok(_serialize_search_engine(se), "搜索引擎已创建")


@search_engines_router.put("/{_id}")
def update_search_engine(
    _id: str,
    payload: SearchEngineUpdatePayload,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """更新搜索引擎配置。"""
    tenant_id = _tenant_of(current_user)
    se = _get_search_engine_or_404(db, _id, tenant_id)
    if payload.name is not None:
        se.name = payload.name
    if payload.engine_type is not None:
        se.engine_type = payload.engine_type
    if payload.api_base is not None:
        se.base_url = payload.api_base
    if payload.api_key:
        se.api_key = encode_api_key(payload.api_key)
    if payload.max_results is not None:
        se.max_results = payload.max_results
    if payload.is_active is not None:
        se.is_active = payload.is_active
    # 板块D：持久化 extra_params / priority
    if payload.extra_params is not None:
        se.extra_params = payload.extra_params
    if payload.priority is not None:
        se.priority = payload.priority
    if payload.is_default is not None:
        if payload.is_default:
            db.query(SearchEngine).filter(
                SearchEngine.id != se.id,
                SearchEngine.tenant_id == tenant_id,
                SearchEngine.is_default.is_(True),
            ).update({SearchEngine.is_default: False})
            se.is_default = True
        else:
            se.is_default = False
    db.commit()
    db.refresh(se)
    return _ok(_serialize_search_engine(se), "搜索引擎已更新")


@search_engines_router.delete("/{_id}")
def delete_search_engine(
    _id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """删除搜索引擎配置。"""
    se = _get_search_engine_or_404(db, _id, _tenant_of(current_user))
    db.delete(se)
    db.commit()
    return _ok({"id": _id, "deleted": True}, "已删除")


@search_engines_router.patch("/{_id}/toggle")
def toggle_search_engine(
    _id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """切换搜索引擎启用/禁用。"""
    se = _get_search_engine_or_404(db, _id, _tenant_of(current_user))
    se.is_active = not se.is_active
    db.commit()
    db.refresh(se)
    return _ok(_serialize_search_engine(se), "已切换")


@search_engines_router.put("/{_id}/set-default")
def set_default_search_engine(
    _id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """将指定搜索引擎设为默认（其余取消默认）。"""
    tenant_id = _tenant_of(current_user)
    se = _get_search_engine_or_404(db, _id, tenant_id)
    db.query(SearchEngine).filter(
        SearchEngine.id != se.id,
        SearchEngine.tenant_id == tenant_id,
        SearchEngine.is_default.is_(True),
    ).update({SearchEngine.is_default: False})
    se.is_default = True
    db.commit()
    db.refresh(se)
    return _ok(_serialize_search_engine(se), "已设为默认")


@search_engines_router.post("/{_id}/test")
def test_search_engine(
    _id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """测试搜索引擎 —— 返回模拟测试结果（不真实发起搜索请求）。"""
    se = _get_search_engine_or_404(db, _id, _tenant_of(current_user))
    start = time.perf_counter()
    latency_ms = int((time.perf_counter() - start) * 1000) + 88
    issues = []
    if not se.base_url:
        issues.append("缺少 API base URL")
    if not se.api_key and se.engine_type in ("google", "bing", "serpapi"):
        issues.append(f"{se.engine_type} 通常需要 API Key")
    if issues:
        return _ok({
            "success": False,
            "message": "配置可能不完整：" + "；".join(issues),
            "result_count": None,
            "first_snippet": None,
        })
    return _ok({
        "success": True,
        "message": f"搜索引擎「{se.name}」配置校验通过",
        "result_count": se.max_results,
        "first_snippet": f"模拟结果：{se.engine_type} @ {se.base_url}（max_results={se.max_results}）",
    })


# ===========================================================================
# /settings —— 系统设置（板块D：持久化到 system_settings 表，扁平字段对齐前端）
# ===========================================================================

settings_router = APIRouter(prefix="/settings", tags=["settings"])


# 系统设置默认值：对应前端 SystemSettingsData 扁平结构。
# GET 时若 DB 无对应 key，则用此默认值补齐，保证字段完整。
_DEFAULT_SETTINGS: dict[str, Any] = {
    "system_name": "FinPilot",
    "system_description": "企业财务 AI 分析平台",
    "default_model_id": None,
    "default_search_engine_id": None,
    "max_conversation_history": 20,
    "session_timeout_minutes": 10080,
    "rate_limit_per_minute": 100,
    "log_level": "INFO",
    "enable_telemetry": False,
    "sandbox_mode": "disabled",
    "max_file_upload_mb": 50,
}

# 布尔型 key —— 从 DB 反序列化时按布尔处理
_SETTING_BOOL_KEYS = {"enable_telemetry"}
# 整型 key —— 从 DB 反序列化时按整型处理
_SETTING_INT_KEYS = {
    "max_conversation_history",
    "session_timeout_minutes",
    "rate_limit_per_minute",
    "max_file_upload_mb",
}


def _load_settings(db: Session, tenant_id: str) -> dict[str, Any]:
    """从 system_settings 表加载设置，缺失 key 用默认值补齐。"""
    rows = db.query(SystemSetting).filter(SystemSetting.tenant_id == tenant_id).all()
    stored: dict[str, str | None] = {r.key: r.value for r in rows}

    result: dict[str, Any] = {}
    for key, default in _DEFAULT_SETTINGS.items():
        raw = stored.get(key)
        if raw is None or raw == "":
            result[key] = default
            continue
        try:
            decoded = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            decoded = raw
        # 类型规整
        if key in _SETTING_BOOL_KEYS:
            result[key] = bool(decoded)
        elif key in _SETTING_INT_KEYS:
            try:
                result[key] = int(decoded)
            except (TypeError, ValueError):
                result[key] = default
        else:
            result[key] = decoded
    return result


def _save_settings(db: Session, tenant_id: str, payload: dict, user_id: Any) -> None:
    """把 payload 中的 key 持久化到 system_settings 表（upsert）。"""
    for key, value in payload.items():
        if key not in _DEFAULT_SETTINGS:
            continue
        encoded = json.dumps(value)
        row = (
            db.query(SystemSetting)
            .filter(SystemSetting.tenant_id == tenant_id, SystemSetting.key == key)
            .first()
        )
        if row:
            row.value = encoded
            row.updated_by = user_id
        else:
            db.add(SystemSetting(
                tenant_id=tenant_id,
                key=key,
                value=encoded,
                updated_by=user_id,
            ))


@settings_router.get("")
def get_settings(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """读取系统设置（扁平 SystemSettingsData 结构，持久化在 system_settings 表）."""
    tenant_id = _tenant_of(current_user)
    return _ok(_load_settings(db, tenant_id))


@settings_router.put("")
def update_settings(
    payload: dict,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """保存系统设置 —— 仅接受 SystemSettingsData 已知 key，落库后回读返回."""
    tenant_id = _tenant_of(current_user)
    _save_settings(db, tenant_id, payload or {}, current_user.get("user_id"))
    db.commit()
    return _ok(_load_settings(db, tenant_id), "设置已保存")


@settings_router.get("/health")
def get_health(
    db: Session = Depends(get_db_session),
    _: dict = Depends(get_current_user),
):
    """健康检查 —— 返回 database / vector_store / default_llm / sandbox / search_engines 五个组件状态.

    前端 HealthStatus 期望嵌套结构，板块D 前此处只返回 {status, version, checked_at}
    导致前端访问 health.database 等均为 undefined。现按真实探测填充。
    """
    # 1. 数据库：SELECT 1 计时
    db_status = "healthy"
    db_latency = 0
    try:
        start = time.perf_counter()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_latency = int((time.perf_counter() - start) * 1000)
    except Exception:  # noqa: BLE001
        db_status = "unhealthy"

    # 2. 向量存储：基于 document_chunks 是否有 embedding 判断（best-effort）
    vs_status = "healthy"
    vs_message: Optional[str] = None
    try:
        insp = inspect(engine)
        if not insp.has_table("document_chunks"):
            vs_status = "unknown"
            vs_message = "document_chunks 表不存在"
        else:
            with engine.connect() as conn:
                total = conn.execute(text("SELECT COUNT(*) FROM document_chunks")).scalar()
                with_emb = conn.execute(
                    text("SELECT COUNT(*) FROM document_chunks WHERE embedding IS NOT NULL")
                ).scalar()
            if not total:
                vs_status = "empty"
                vs_message = "尚无文档分块，向量库未填充"
            elif not with_emb:
                vs_status = "degraded"
                vs_message = f"共 {total} 条分块，但无 embedding"
    except Exception as exc:  # noqa: BLE001
        vs_status = "unhealthy"
        vs_message = str(exc)

    # 3. 默认 LLM：查默认 provider + 其下首个激活模型
    llm_status = "unhealthy"
    llm_model_name = ""
    try:
        p = db.query(LlmProvider).filter(LlmProvider.is_default.is_(True)).first()
        if p:
            m = (
                db.query(LlmModel)
                .filter(LlmModel.provider_id == p.id, LlmModel.is_active.is_(True))
                .first()
            )
            if m:
                llm_status = "healthy"
                llm_model_name = m.model_name
            else:
                llm_status = "degraded"
                llm_model_name = f"{p.name}（无激活模型）"
        else:
            llm_status = "unhealthy"
            llm_model_name = "未配置默认供应商"
    except Exception:  # noqa: BLE001
        llm_status = "unhealthy"

    # 4. 沙箱：best-effort 读 sandbox_configs 表
    sandbox_status = "unknown"
    try:
        insp = inspect(engine)
        if insp.has_table("sandbox_configs"):
            from finpilot.database.models import SandboxConfig
            cfg = db.query(SandboxConfig).filter(SandboxConfig.is_active.is_(True)).first()
            sandbox_status = "enabled" if cfg else "disabled"
        else:
            sandbox_status = "disabled"
    except Exception:  # noqa: BLE001
        sandbox_status = "unknown"

    # 5. 搜索引擎：总数 / 激活数 / 默认名
    se_total = 0
    se_active = 0
    se_default_name = ""
    try:
        se_total = db.query(SearchEngine).count()
        se_active = db.query(SearchEngine).filter(SearchEngine.is_active.is_(True)).count()
        default_se = db.query(SearchEngine).filter(SearchEngine.is_default.is_(True)).first()
        se_default_name = default_se.name if default_se else "未配置"
    except Exception:  # noqa: BLE001
        pass

    overall = "healthy" if all([
        db_status == "healthy",
        vs_status in ("healthy", "empty", "unknown"),
        llm_status == "healthy",
    ]) else "degraded"

    return _ok({
        "status": overall,
        "database": {"status": db_status, "latency_ms": db_latency},
        "vector_store": {"status": vs_status, "message": vs_message},
        "default_llm": {"status": llm_status, "model_name": llm_model_name},
        "sandbox": {"status": sandbox_status},
        "search_engines": {
            "total": se_total,
            "active": se_active,
            "default_name": se_default_name,
        },
        "timestamp": datetime.now().isoformat(),
    }, "ok")


# ===========================================================================
# /metrics —— 指标分析页
#
# 前端 KpiDashboardPage.tsx 期望 schema（见 frontend/src/types/metric.ts）：
#   overview  -> { year, period, cards: KpiCardData[], generated_at }
#   trend     -> { metric, label, unit, series: TrendPoint[] }
#   comparison-> { year, periods: str[], metrics: MetricComparisonItem[] }
#   drill     -> { metric, label, year, total, items: DrillDownItem[] }
#
# 这里基于 year+period 用确定性公式生成稳定的模拟财务数据，让前端 KPI 看板
# 能真正渲染出来（同比/环比/趋势/对比/钻取），而不是 404 或 undefined 崩溃。
# ===========================================================================

metrics_router = APIRouter(prefix="/metrics", tags=["metrics"])

# 指标元数据：metric key -> (label, unit)
_METRIC_META: dict[str, tuple[str, str]] = {
    "revenue": ("营业收入", "元"),
    "net_profit": ("净利润", "元"),
    "gross_profit": ("毛利润", "元"),
    "total_assets": ("资产总额", "元"),
    "total_liabilities": ("负债总额", "元"),
    "net_assets": ("净资产", "元"),
    "operating_cash_flow": ("经营活动现金流", "元"),
    "ar_balance": ("应收账款", "元"),
    "ap_balance": ("应付账款", "元"),
    "inventory": ("存货", "元"),
}

# 每个指标的基准值（2020 年 Q1 的"起点"），后续按 year/period 增长
_BASE_VALUES: dict[str, float] = {
    "revenue": 1_000_000_000.0,
    "net_profit": 150_000_000.0,
    "gross_profit": 400_000_000.0,
    "total_assets": 3_000_000_000.0,
    "total_liabilities": 1_600_000_000.0,
    "net_assets": 1_400_000_000.0,
    "operating_cash_flow": 200_000_000.0,
    "ar_balance": 300_000_000.0,
    "ap_balance": 250_000_000.0,
    "inventory": 180_000_000.0,
}


def _period_index(period: str) -> int:
    """把期间字符串映射成 0-7 的索引：Q1=0, Q2=1, Q3=2, Q4=3, H1=4, H2=5, annual=6, 其他=7"""
    mapping = {"Q1": 0, "Q2": 1, "Q3": 2, "Q4": 3, "H1": 4, "H2": 5, "annual": 6}
    return mapping.get(period, 7)


def _metric_value(metric: str, year: int, period: str) -> float:
    """确定性生成 (metric, year, period) 的模拟值：基准 × 年增长 × 季节因子"""
    base = _BASE_VALUES.get(metric, 100_000_000.0)
    # 年增长：每年 +18%（线性增长），2020 为基年
    year_factor = (1.18 ** max(year - 2020, 0))
    # 季节因子：Q1=0.85, Q2=0.95, Q3=1.10, Q4=1.40, H1=1.80, H2=2.50, annual=4.30
    period_factor = {
        "Q1": 0.85, "Q2": 0.95, "Q3": 1.10, "Q4": 1.40,
        "H1": 1.80, "H2": 2.50, "annual": 4.30,
    }.get(period, 1.0)
    # 指标特有调整：负债/应收/应付/存货增长慢一些；净利润波动大
    metric_adj = {
        "net_profit": 0.92,           # 利润略低于平均
        "total_liabilities": 1.05,    # 负债略高
        "ar_balance": 1.08,           # 应收增长快
        "ap_balance": 1.03,
        "inventory": 0.98,
    }.get(metric, 1.0)
    return round(base * year_factor * period_factor * metric_adj, 2)


def _change_tuple(metric: str, year: int, period: str, lag_periods: int) -> dict | None:
    """构造同比 (lag=4) / 环比 (lag=1) 变化值，去年/上季数据不存在则返回 None"""
    periods_order = ["Q1", "Q2", "Q3", "Q4"]
    if period not in periods_order:
        return None
    idx = periods_order.index(period)
    target_idx = idx - lag_periods
    target_year = year
    if target_idx < 0:
        target_idx += 4
        target_year = year - 1
    if target_year < 2020:
        return None
    target_period = periods_order[target_idx]
    cur = _metric_value(metric, year, period)
    prev = _metric_value(metric, target_year, target_period)
    if prev == 0:
        return None
    change = round(cur - prev, 2)
    change_pct = round((cur - prev) / prev, 4)
    return {"value": cur, "change": change, "change_pct": change_pct}


@metrics_router.get("/overview")
def metrics_overview(year: int = 0, period: str = "", _: dict = Depends(get_current_user)):
    """KPI 概览：返回核心指标卡片，含同比/环比变化"""
    year = year or datetime.utcnow().year
    period = period or "Q3"
    cards = []
    for metric, (label, unit) in _METRIC_META.items():
        value = _metric_value(metric, year, period)
        cards.append({
            "metric": metric,
            "label": label,
            "value": value,
            "unit": unit,
            "yoy": _change_tuple(metric, year, period, 4),
            "qoq": _change_tuple(metric, year, period, 1),
        })
    return _ok({
        "year": year,
        "period": period,
        "cards": cards,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    })


@metrics_router.get("/comparison")
def metrics_comparison(
    year: int = 0,
    periods: str = "Q1,Q2,Q3,Q4",
    _: dict = Depends(get_current_user),
):
    """季度对比：返回每个指标在指定 periods 上的取值"""
    year = year or datetime.utcnow().year
    period_list = [p.strip() for p in periods.split(",") if p.strip()]
    items = []
    for metric, (label, unit) in _METRIC_META.items():
        values = {p: _metric_value(metric, year, p) for p in period_list}
        items.append({
            "metric": metric,
            "label": label,
            "unit": unit,
            "values": values,
        })
    return _ok({
        "year": year,
        "periods": period_list,
        "metrics": items,
    })


@metrics_router.get("/{metric}/trend")
def metrics_trend(
    metric: str,
    years: str = "",
    _: dict = Depends(get_current_user),
):
    """年度趋势：返回指标在指定年份的年度值序列"""
    label, unit = _METRIC_META.get(metric, (metric, "元"))
    year_list = []
    if years:
        for y in years.split(","):
            y = y.strip()
            if y.isdigit():
                year_list.append(int(y))
    if not year_list:
        cur = datetime.utcnow().year
        year_list = [cur - 2, cur - 1, cur]
    series = [
        {"year": y, "value": _metric_value(metric, y, "annual")}
        for y in year_list
    ]
    return _ok({
        "metric": metric,
        "label": label,
        "unit": unit,
        "series": series,
    })


@metrics_router.get("/{metric}/drill-down")
def metrics_drill_down(
    metric: str,
    year: int = 0,
    period: str = "",
    _: dict = Depends(get_current_user),
):
    """明细钻取：返回指标在该年四个季度的占比明细"""
    label, unit = _METRIC_META.get(metric, (metric, "元"))
    year = year or datetime.utcnow().year
    quarters = ["Q1", "Q2", "Q3", "Q4"]
    values = [_metric_value(metric, year, q) for q in quarters]
    total = round(sum(values), 2)
    items = []
    for q, v in zip(quarters, values):
        ratio = round(v / total, 4) if total else None
        items.append({"period": q, "value": v, "ratio": ratio})
    return _ok({
        "metric": metric,
        "label": label,
        "year": year,
        "total": total,
        "items": items,
    })


# ===========================================================================
# /context —— 上下文管理（板块D：占位补全 + 字段对齐 + 长期记忆持久化）
# ===========================================================================

context_router = APIRouter(prefix="/context", tags=["context"])


def _estimate_tokens(text: str) -> int:
    """估算文本 token 数.

    按字符类型分别计数：CJK 字符 ≈ 1 token/字，其余 ≈ 1 token/4 字符（约 0.25/字符）。
    比此前 ``chars * 1.5`` 更贴合实际 tokenizer 行为。
    """
    if not text:
        return 0
    cjk = 0
    other = 0
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff" or "\u3000" <= ch <= "\u303f" or "\uff00" <= ch <= "\uffef":
            cjk += 1
        else:
            other += 1
    return cjk + max(other // 4, 0)


@context_router.post("/count-tokens")
def count_tokens(payload: dict, _: dict = Depends(get_current_user)):
    """计算文本 token 数.

    板块D：字段对齐前端 TokenCountResult —— token_count / char_count / model。
    此前返回 tokens/chars 导致前端 token_count 永远显示 0。
    """
    text = payload.get("text", "") or ""
    model = payload.get("model")
    chars = len(text)
    return _ok({
        "token_count": _estimate_tokens(text),
        "char_count": chars,
        "model": model,
    })


@context_router.post("/optimize")
def optimize_context(payload: dict, _: dict = Depends(get_current_user)):
    """优化上下文 —— 保留 system_prompt，按 token 预算从末尾裁剪历史消息.

    板块D：字段对齐前端 OptimizeContextResult —— messages / system_prompt /
    estimated_tokens / truncated。此前原样返回 messages 且字段名错位。
    策略：预算 6000 token；保留 system_prompt 全文 + 最后若干条消息，
    超预算则从最早的消息开始丢弃，直到剩余 <= 预算。
    """
    messages = payload.get("messages", []) or []
    system_prompt = payload.get("system_prompt", "") or ""
    model = payload.get("model")  # noqa: F841  保留以备后续按模型分桶
    token_budget = 6000

    # system_prompt 占用
    system_tokens = _estimate_tokens(system_prompt)
    remaining_budget = max(token_budget - system_tokens, 0)

    # 倒序保留消息，超出预算的从最旧开始丢弃
    kept_reversed: list = []
    used = 0
    truncated = False
    for msg in reversed(messages):
        content = ""
        if isinstance(msg, dict):
            content = str(msg.get("content", ""))
        else:
            content = str(msg)
        t = _estimate_tokens(content)
        if used + t > remaining_budget:
            truncated = True
            break
        kept_reversed.append(msg)
        used += t

    optimized = list(reversed(kept_reversed))
    estimated_tokens = system_tokens + used
    return _ok({
        "messages": optimized,
        "system_prompt": system_prompt,
        "estimated_tokens": estimated_tokens,
        "truncated": truncated,
    })


def _serialize_memory(m: Memory) -> dict:
    """Memory ORM → 前端 MemoryItem 字段."""
    return {
        "id": str(m.id),
        "user_id": m.user_id,
        "category": m.category,
        "content": m.content,
        "importance": m.importance,
        "source_conversation_id": m.source_conversation_id,
        "created_at": m.created_at.isoformat(sep=" ") if m.created_at else None,
        "updated_at": m.updated_at.isoformat(sep=" ") if m.updated_at else None,
    }


@context_router.get("/memories")
def list_memories(
    user_id: str = Query("", description="按用户 ID 筛选"),
    category: str = Query("", description="按分类筛选"),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """列出长期记忆.

    板块D：真实读取 memories 表。前端 getMemories 期望 data 为数组（非分页对象），
    故直接返回 [MemoryItem]。按重要性降序 + 创建时间降序，限制条数。
    """
    tenant_id = _tenant_of(current_user)
    q = db.query(Memory).filter(Memory.tenant_id == tenant_id)
    if user_id:
        q = q.filter(Memory.user_id == user_id)
    if category:
        q = q.filter(Memory.category == category)
    rows = (
        q.order_by(Memory.importance.desc().nullslast(), Memory.created_at.desc())
        .limit(limit)
        .all()
    )
    return _ok([_serialize_memory(m) for m in rows])


@context_router.post("/memories/search")
def search_memories(
    payload: dict,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """语义搜索长期记忆.

    板块D：基于 content LIKE 关键词搜索（无向量索引时的 best-effort）。
    前端 searchMemories 期望 data 为数组，故返回 [MemoryItem]。
    """
    query = (payload.get("query", "") or "").strip()
    tenant_id = _tenant_of(current_user)
    q = db.query(Memory).filter(Memory.tenant_id == tenant_id)
    if query:
        q = q.filter(Memory.content.ilike(f"%{query}%"))
    rows = (
        q.order_by(Memory.importance.desc().nullslast(), Memory.created_at.desc())
        .limit(100)
        .all()
    )
    return _ok([_serialize_memory(m) for m in rows])


@context_router.delete("/memories/{memory_id}")
def delete_memory(
    memory_id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """删除一条长期记忆.

    板块D：真实删除 memories 表记录。前端 deleteMemory 期望 data 为 {deleted: boolean}。
    """
    tenant_id = _tenant_of(current_user)
    pk = _parse_int_id(memory_id, "记忆")
    m = (
        db.query(Memory)
        .filter(Memory.id == pk, Memory.tenant_id == tenant_id)
        .first()
    )
    if not m:
        raise HTTPException(status_code=404, detail=f"记忆 {memory_id} 不存在")
    db.delete(m)
    db.commit()
    return _ok({"deleted": True})


@context_router.get("/stats")
def context_stats(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """上下文使用统计.

    板块D：字段对齐前端 ContextStats —— total_memories / total_conversations /
    avg_tokens_per_conversation。此前返回 total_tokens_used/token_limit/usage_ratio
    前端无法消费。
    """
    tenant_id = _tenant_of(current_user)
    total_memories = db.query(Memory).filter(Memory.tenant_id == tenant_id).count()
    total_conversations = (
        db.query(Conversation).filter(Conversation.tenant_id == tenant_id).count()
    )
    # 平均 token/会话：基于 messages.tokens_in + tokens_out 聚合
    avg_tokens = 0.0
    try:
        from sqlalchemy import func as _func
        # Message 无 tenant_id，通过 conversation 关联过滤
        total_tokens_row = (
            db.query(
                _func.coalesce(_func.sum(Message.tokens_in), 0)
                + _func.coalesce(_func.sum(Message.tokens_out), 0)
            )
            .join(Conversation, Conversation.id == Message.conversation_id)
            .filter(Conversation.tenant_id == tenant_id)
            .scalar()
        )
        total_tokens = int(total_tokens_row or 0)
        if total_conversations > 0:
            avg_tokens = round(total_tokens / total_conversations, 2)
    except Exception:  # noqa: BLE001
        avg_tokens = 0.0

    return _ok({
        "total_memories": total_memories,
        "total_conversations": total_conversations,
        "avg_tokens_per_conversation": avg_tokens,
    })


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
    return _ok([
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
    """把所有兼容路由挂载到主 API router 上"""
    api.include_router(model_configs_router)
    api.include_router(agent_configs_router)
    api.include_router(search_engines_router)
    api.include_router(settings_router)
    api.include_router(metrics_router)
    api.include_router(context_router)
    api.include_router(aliases_router)
