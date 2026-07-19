"""提示词加载器 — 从 DB 加载 PromptTemplate，降级到硬编码默认值.

将管理后台配置的提示词模板接入 Agent 运行时，实现"可增删改查 + 运行时生效"。
支持按 tenant_id + template_type 查找激活的模板，未找到则使用硬编码默认。
"""

# TODO: requires finpilot.database.models.PromptTemplate
# TODO: requires finpilot.database.models.AgentConfig
# TODO: requires finpilot.llm.prompts (INTENT_CLASSIFICATION_*, PARAMETER_EXTRACTION_*)
# TODO: requires finpilot.llm.react_prompts (REACT_SYSTEM_TEMPLATE, REACT_USER_TEMPLATE)

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from finpilot.database.models import PromptTemplate

logger = logging.getLogger(__name__)

# 硬编码默认提示词（降级使用）— 懒加载，避免与 finpilot.llm 的循环导入
_DEFAULTS: dict[str, str] | None = None


def _get_defaults() -> dict[str, str]:
    """懒加载硬编码默认提示词.

    将 ``finpilot.llm.prompts`` / ``finpilot.llm.react_prompts`` 的导入推迟到首次调用，
    打破 ``prompt_loader → finpilot.llm → finpilot.llm.intent → prompt_loader`` 的循环依赖。
    在正常应用启动中，main.py 的路由导入顺序会先完整加载 ``finpilot.llm``，
    但当 prompt_engine 首次触发 prompt_loader 时，延迟导入可保证安全。
    """
    global _DEFAULTS
    if _DEFAULTS is not None:
        return _DEFAULTS

    from finpilot.llm.prompts import (
        INTENT_CLASSIFICATION_SYSTEM,
        INTENT_CLASSIFICATION_USER,
        INTENT_CLASSIFICATION_USER_WITH_HISTORY,
        PARAMETER_EXTRACTION_SYSTEM,
        PARAMETER_EXTRACTION_USER,
        PARAMETER_EXTRACTION_USER_WITH_HISTORY,
    )
    from finpilot.llm.react_prompts import REACT_SYSTEM_TEMPLATE, REACT_USER_TEMPLATE

    _DEFAULTS = {
        "intent_classification_system": INTENT_CLASSIFICATION_SYSTEM,
        "intent_classification_user": INTENT_CLASSIFICATION_USER,
        "intent_classification_user_with_history": INTENT_CLASSIFICATION_USER_WITH_HISTORY,
        "parameter_extraction_system": PARAMETER_EXTRACTION_SYSTEM,
        "parameter_extraction_user": PARAMETER_EXTRACTION_USER,
        "parameter_extraction_user_with_history": PARAMETER_EXTRACTION_USER_WITH_HISTORY,
        "react_system": REACT_SYSTEM_TEMPLATE,
        "react_user": REACT_USER_TEMPLATE,
    }
    return _DEFAULTS

# 提示词 key → DB template_type 映射
_KEY_TO_TYPE: dict[str, str] = {
    "intent_classification_system": "intent",
    "intent_classification_user": "intent",
    "intent_classification_user_with_history": "intent",
    "parameter_extraction_system": "parameter",
    "parameter_extraction_user": "parameter",
    "parameter_extraction_user_with_history": "parameter",
    "react_system": "react",
    "react_user": "react",
}

# 内存缓存: (tenant_id, key) → content，避免每次查 DB
_cache: dict[tuple[str, str], str] = {}
_CACHE_VERSION = 0


def _invalidate_cache() -> None:
    """清除缓存（管理后台更新提示词后调用）."""
    global _CACHE_VERSION
    _CACHE_VERSION += 1
    _cache.clear()


def get_prompt(
    key: str,
    tenant_id: str,
    db: Session | None = None,
) -> str:
    """按 key 加载提示词，优先从 DB 读取，降级到硬编码默认.

    Args:
        key: 提示词标识，如 'react_system' / 'intent_classification_system'
        tenant_id: 租户 ID，用于隔离不同租户的提示词
        db: 可选的数据库会话

    Returns:
        提示词模板字符串
    """
    cache_key = (tenant_id, key)
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    # 尝试从 DB 加载
    if db is not None:
        try:
            template_type = _KEY_TO_TYPE.get(key, key)
            # 按 name 精确查找，或按 type 找第一个激活的
            tpl = (
                db.query(PromptTemplate)
                .filter(
                    PromptTemplate.tenant_id == tenant_id,
                    PromptTemplate.template_type == template_type,
                    PromptTemplate.is_active.is_(True),
                )
                .order_by(PromptTemplate.updated_at.desc())
                .first()
            )
            if tpl and tpl.content:
                _cache[cache_key] = tpl.content
                return tpl.content
        except Exception as exc:  # noqa: BLE001
            logger.warning("prompt_loader_db_failed", key=key, error=str(exc))

    # 降级到硬编码默认
    default = _get_defaults().get(key, "")
    _cache[cache_key] = default
    return default


def get_agent_config_prompt(
    agent_config_id: str | None,
    tenant_id: str,
    db: Session | None = None,
    prompt_field: str = "system_prompt",
) -> str | None:
    """从 AgentConfig 加载提示词.

    Args:
        agent_config_id: Agent 配置 ID，None 则返回 None
        tenant_id: 租户 ID
        db: 数据库会话
        prompt_field: 'system_prompt' 或 'prompt_id' 关联的模板内容

    Returns:
        提示词内容，None 表示未配置
    """
    if not agent_config_id or db is None:
        return None

    try:
        from finpilot.database.models import AgentConfig

        config = (
            db.query(AgentConfig)
            .filter(
                AgentConfig.id == agent_config_id,
                AgentConfig.tenant_id == tenant_id,
                AgentConfig.is_active.is_(True),
            )
            .first()
        )
        if not config:
            return None

        # 优先使用 system_prompt 覆盖
        if prompt_field == "system_prompt" and config.system_prompt:
            return config.system_prompt

        # 从关联的 prompt_id 加载模板
        if config.prompt_id:
            tpl = (
                db.query(PromptTemplate)
                .filter(
                    PromptTemplate.id == config.prompt_id,
                    PromptTemplate.is_active.is_(True),
                )
                .first()
            )
            if tpl and tpl.content:
                return tpl.content
    except Exception as exc:  # noqa: BLE001
        logger.warning("agent_config_prompt_failed", agent_config_id=agent_config_id, error=str(exc))

    return None


def render_prompt(template: str, variables: dict[str, Any]) -> str:
    """渲染提示词模板，支持条件模板与 {variable} 占位符.

    委托给提示词引擎：先渲染 ``{% if %}``/``{% for %}`` 条件逻辑，
    再替换 ``{variable}`` 占位符。仅替换已知变量，未知占位符原样保留，
    兼容不含条件逻辑的旧模板。

    Args:
        template: 含 {variable} 占位符 / 条件标签的模板
        variables: 变量字典

    Returns:
        渲染后的字符串
    """
    try:
        from finpilot.services.prompt_engine import (
            render_conditionals,
            substitute_variables,
        )

        rendered = render_conditionals(template, variables)
        return substitute_variables(rendered, variables)
    except Exception as exc:  # noqa: BLE001
        logger.warning("prompt_render_failed", error=str(exc))
        # 降级：简单字符串替换，保证可用性
        result = template
        for key, val in variables.items():
            result = result.replace(f"{{{key}}}", str(val))
        return result


def get_prompt_advanced(
    key: str,
    tenant_id: str,
    variables: dict[str, Any] | None = None,
    db: Session | None = None,
) -> str:
    """高级渲染入口 — 走提示词引擎完整流程.

    依次执行：A/B 分流 → 加载内容 → 条件渲染 → few-shot 注入 → 变量替换。
    与 ``get_prompt`` 的区别：``get_prompt`` 仅返回原始模板字符串，
    本方法返回可直接投喂 LLM 的最终提示词。

    Args:
        key: 提示词标识
        tenant_id: 租户 ID
        variables: 渲染变量
        db: 数据库会话

    Returns:
        渲染后的最终提示词字符串
    """
    from finpilot.services.prompt_engine import render_prompt_advanced

    return render_prompt_advanced(key, tenant_id, variables or {}, db)


def list_prompt_types() -> list[dict[str, str]]:
    """返回支持的提示词类型列表."""
    return [
        {"type": "general", "description": "通用提示词"},
        {"type": "intent", "description": "意图识别提示词"},
        {"type": "parameter", "description": "参数提取提示词"},
        {"type": "react", "description": "ReAct 推理提示词"},
        {"type": "query", "description": "查询分析提示词"},
        {"type": "report", "description": "报告生成提示词"},
        {"type": "audit", "description": "审计分析提示词"},
        {"type": "custom", "description": "自定义提示词"},
    ]


def seed_default_prompts(tenant_id: str, db: Session) -> None:
    """为租户初始化默认系统提示词模板（仅首次）.

    Args:
        tenant_id: 租户 ID
        db: 数据库会话
    """
    existing = db.query(PromptTemplate).filter(
        PromptTemplate.tenant_id == tenant_id,
        PromptTemplate.is_system.is_(True),
    ).count()
    if existing > 0:
        return

    defaults = [
        ("意图识别系统提示词", "intent", "INTENT_CLASSIFICATION_SYSTEM", _get_defaults()["intent_classification_system"]),
        ("ReAct 系统提示词", "react", "REACT_SYSTEM", _get_defaults()["react_system"]),
        ("参数提取系统提示词", "parameter", "PARAMETER_EXTRACTION_SYSTEM", _get_defaults()["parameter_extraction_system"]),
    ]
    for name, tpl_type, name_key, content in defaults:
        tpl = PromptTemplate(
            tenant_id=tenant_id,
            name=name,
            description=f"系统默认 {name}",
            template_type=tpl_type,
            content=content,
            variables=json.dumps([], ensure_ascii=False),
            is_system=True,
            is_active=True,
        )
        db.add(tpl)
    db.commit()
    logger.info("seeded_default_prompts", tenant_id=tenant_id, count=len(defaults))
