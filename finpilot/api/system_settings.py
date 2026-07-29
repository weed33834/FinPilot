# -*- coding: utf-8 -*-
"""``/settings`` —— 系统设置（板块D：持久化到 system_settings 表，扁平字段对齐前端）。

本模块从原 ``compat.py`` 拆分而来，行为与原 ``settings_router`` 完全一致。
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from finpilot.database.connection import engine
from finpilot.database.models import LlmModel, LlmProvider, SearchEngine, SystemSetting

from ._compat_helpers import ok, tenant_of
from .deps import get_current_user, get_db_session, require_admin

router = APIRouter(prefix="/settings", tags=["settings"])


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


@router.get("")
def get_settings(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """读取系统设置（扁平 SystemSettingsData 结构，持久化在 system_settings 表）."""
    tenant_id = tenant_of(current_user)
    return ok(_load_settings(db, tenant_id))


@router.put("")
def update_settings(
    payload: dict,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """保存系统设置 —— 仅接受 SystemSettingsData 已知 key，落库后回读返回."""
    tenant_id = tenant_of(current_user)
    _save_settings(db, tenant_id, payload or {}, current_user.get("user_id"))
    db.commit()
    return ok(_load_settings(db, tenant_id), "设置已保存")


@router.get("/health")
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

    return ok({
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
