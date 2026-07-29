# -*- coding: utf-8 -*-
"""``/agent-configs`` —— AgentConfig CRUD（对接前端 AgentConfigManagement 页）。

板块D：AgentConfig 已补齐 agent_type / prompt_id / max_iterations / temperature
列，前端表单字段全部持久化，不再硬编码回显。

本模块从原 ``compat.py`` 拆分而来，行为与原 ``agent_configs_router`` 完全一致。
"""
from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from finpilot.database.models import AgentConfig

from ._compat_helpers import coerce_model_id, ok, parse_int_id, tenant_of
from .deps import get_db_session, require_admin

router = APIRouter(prefix="/agent-configs", tags=["agent-configs"])


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
    pk = parse_int_id(_id, "Agent 配置")
    cfg = (
        db.query(AgentConfig)
        .filter(AgentConfig.id == pk, AgentConfig.tenant_id == tenant_id)
        .first()
    )
    if not cfg:
        raise HTTPException(status_code=404, detail=f"Agent 配置 {_id} 不存在")
    return cfg


@router.get("")
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
    tenant_id = tenant_of(current_user)
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
    return ok({
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_serialize_agent_config(c) for c in rows],
    })


@router.get("/types")
def list_agent_types(_: dict = Depends(require_admin)):
    return ok([
        {"value": "react", "label": "ReAct 智能体", "description": "推理-行动循环，多步工具调用"},
        {"value": "plan_execute", "label": "Plan-Execute", "description": "先规划再执行，适合复杂任务"},
        {"value": "debate", "label": "辩论体", "description": "多 agent 辩论，估值/分析场景"},
    ])


@router.post("")
def create_agent_config(
    payload: AgentConfigCreatePayload,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """创建 Agent 配置。created_by/tenant_id 取自当前用户。"""
    cfg = AgentConfig(
        tenant_id=tenant_of(current_user),
        name=payload.name,
        display_name=payload.display_name or payload.name,
        description=payload.description,
        agent_type=payload.agent_type or "react",
        prompt_id=coerce_model_id(payload.prompt_id),
        model_id=coerce_model_id(payload.model_id),
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
    return ok(_serialize_agent_config(cfg), "Agent 配置已创建")


@router.put("/{_id}")
def update_agent_config(
    _id: str,
    payload: AgentConfigUpdatePayload,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """更新 Agent 配置。"""
    cfg = _get_agent_config_or_404(db, _id, tenant_of(current_user))
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
        cfg.prompt_id = coerce_model_id(payload.prompt_id)
    if payload.model_id is not None:
        cfg.model_id = coerce_model_id(payload.model_id)
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
    return ok(_serialize_agent_config(cfg), "Agent 配置已更新")


@router.delete("/{_id}")
def delete_agent_config(
    _id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """删除 Agent 配置。"""
    cfg = _get_agent_config_or_404(db, _id, tenant_of(current_user))
    db.delete(cfg)
    db.commit()
    return ok({"id": _id, "deleted": True}, "已删除")


@router.patch("/{_id}/toggle")
def toggle_agent_config(
    _id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """切换 Agent 配置启用/禁用。"""
    cfg = _get_agent_config_or_404(db, _id, tenant_of(current_user))
    cfg.is_active = not cfg.is_active
    db.commit()
    db.refresh(cfg)
    return ok(_serialize_agent_config(cfg), "已切换")


@router.post("/{_id}/test")
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
    cfg = _get_agent_config_or_404(db, _id, tenant_of(current_user))
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

        tenant_id = tenant_of(current_user)
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
        return ok({
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
        return ok({
            "success": False,
            "message": f"运行失败: {exc}",
            "thinking": None,
            "answer": None,
            "execution_time_ms": latency_ms,
        })


@router.post("/{_id}/duplicate")
def duplicate_agent_config(
    _id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """复制 Agent 配置 —— 生成一份新配置，名称加 (副本) 后缀，默认禁用。"""
    src = _get_agent_config_or_404(db, _id, tenant_of(current_user))
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
    return ok(_serialize_agent_config(new_cfg), "已复制")
