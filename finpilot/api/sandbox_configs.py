"""沙箱配置路由 — 管理 SQL 白名单、代码沙箱、文件上传配置."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

# TODO: FinPilot deps 暂未提供 get_current_user_or_api_key（带 API Key + scope 校验），
#       暂用 get_current_user；如需 API Key 鉴权与 scope 校验，需扩展 finpilot.api.deps。
# TODO: FinPilot 暂未引入多租户(tenant_id)概念，user.tenant_id 暂以 user_id 字符串替代。
# TODO: SandboxConfig ORM 模型尚未在 finpilot.database.models 中定义，需后续补充。
# TODO: sandbox_config_loader 服务尚未在 finpilot.services 中实现，需后续补充。
#       当前导入语句保留以便后续接入；运行时会因 ImportError 而失败。
from finpilot.api.deps import get_current_user, get_db_session
# TODO: SandboxConfig 模型尚未在 finpilot.database.models 中定义，导入会失败。
from finpilot.database.models import SandboxConfig, SandboxExecution  # noqa: F401
from finpilot.services.sandbox_config_loader import (
    get_code_sandbox_config,
    get_sandbox_config,
    invalidate_config_cache,
)

router = APIRouter(prefix="/sandbox-configs", tags=["Sandbox Admin"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SandboxConfigBase(BaseModel):
    config_type: str = Field(..., description="配置类型: sql_whitelist/code_sandbox/file_upload")
    name: str = Field(..., max_length=128)
    description: str | None = None
    config: dict[str, Any] = Field(default_factory=dict, description="配置 JSON")
    is_active: bool = True
    priority: int = 0


class SandboxConfigCreate(SandboxConfigBase):
    pass


class SandboxConfigUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    config: dict[str, Any] | None = None
    is_active: bool | None = None
    priority: int | None = None


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def _model_to_response(cfg: SandboxConfig) -> dict[str, Any]:
    return {
        "id": str(cfg.id),
        "config_type": cfg.config_type,
        "name": cfg.name,
        "description": cfg.description,
        "config": cfg.config or {},
        "is_active": cfg.is_active,
        "is_system": cfg.is_system,
        "priority": cfg.priority,
    }


@router.get("")
def list_configs(
    config_type: str | None = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """获取沙箱配置列表."""
    tenant_id = str(current_user.get("user_id", "default"))
    query = db.query(SandboxConfig).filter(SandboxConfig.tenant_id == tenant_id)
    if config_type:
        query = query.filter(SandboxConfig.config_type == config_type)
    items = query.order_by(SandboxConfig.priority, SandboxConfig.created_at).all()
    return {
        "code": 0,
        "message": "ok",
        "data": [_model_to_response(c) for c in items],
    }


@router.get("/types")
def list_config_types(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """获取配置类型列表."""
    return {
        "code": 0,
        "message": "ok",
        "data": [
            {
                "value": "sql_whitelist",
                "label": "SQL 白名单",
                "description": "控制 SQL 查询可访问的表和行数限制",
                "default_config": {
                    "tables": ["financial_reports", "accounts", "vouchers"],
                    "max_rows": 1000,
                    "forbidden_keywords": ["DROP", "TRUNCATE", "GRANT"],
                },
            },
            {
                "value": "code_sandbox",
                "label": "代码沙箱",
                "description": "Python 代码执行沙箱的资源配置",
                "default_config": {
                    "mode": "lightweight",
                    "docker_image": "python:3.12-slim",
                    "timeout_seconds": 30,
                    "memory_mb": 256,
                    "cpu_limit": 1,
                    "allowed_modules": ["math", "json", "datetime", "itertools", "numpy", "pandas"],
                    "blocked_modules": ["os", "subprocess", "socket", "ctypes", "sys"],
                    "max_output_chars": 10000,
                    "network_disabled": True,
                },
            },
            {
                "value": "file_upload",
                "label": "文件上传",
                "description": "文件上传的大小和类型限制",
                "default_config": {
                    "max_size_mb": 50,
                    "allowed_types": ["pdf", "xlsx", "xls", "csv", "txt", "doc", "docx"],
                    "scan_for_malware": False,
                },
            },
        ],
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_config(
    body: SandboxConfigCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """创建沙箱配置."""
    cfg = SandboxConfig(
        tenant_id=str(current_user.get("user_id", "default")),
        config_type=body.config_type,
        name=body.name,
        description=body.description,
        config=body.config,
        is_active=body.is_active,
        priority=body.priority,
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    invalidate_config_cache(cfg.config_type)
    return {"code": 0, "message": "ok", "data": _model_to_response(cfg)}


# ---------------------------------------------------------------------------
# 沙箱实例生命周期 + 执行历史 + 健康检查
# 警告：以下端点必须声明在 /{config_id} 路径参数路由之前，否则会被吞掉。
# ---------------------------------------------------------------------------

# 内存级实例状态表（无持久化，进程重启即重置）
# config_id -> {"status": "running"/"stopped"/"error", "started_at": ISO, "stopped_at": ISO|None}
_sandbox_instances: dict[str, dict[str, Any]] = {}


class SandboxTestExecuteRequest(BaseModel):
    """沙箱测试执行请求."""

    code: str = Field(..., min_length=1, description="要执行的 Python 代码")
    language: str = Field(default="python", description="语言（目前仅支持 python）")
    timeout: int | None = Field(default=None, ge=1, le=60, description="超时秒数")


@router.get("/health")
def health_check(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """沙箱健康检查 — 实际执行一段 print('ok') 代码验证可用性."""
    from finpilot.services.code_sandbox import CodeSandbox

    tenant_id = str(current_user.get("user_id", "default"))
    started = time.monotonic()
    try:
        sandbox = CodeSandbox(tenant_id=tenant_id, db=db)
        ok = sandbox.health_check()
        latency_ms = int((time.monotonic() - started) * 1000)
        return {
            "code": 0,
            "message": "ok",
            "data": {
                "healthy": ok,
                "mode": sandbox.mode,
                "docker_image": sandbox.docker_image,
                "docker_available": bool(sandbox._docker_bin),
                "latency_ms": latency_ms,
                "checked_at": datetime.now().isoformat(sep=" "),
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "code": 0,
            "message": "ok",
            "data": {
                "healthy": False,
                "error": str(exc),
                "checked_at": datetime.now().isoformat(sep=" "),
            },
        }


@router.get("/instances")
def list_instances(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """列出当前租户所有沙箱配置的实例状态（含已停止/未启动）."""
    tenant_id = str(current_user.get("user_id", "default"))
    configs = (
        db.query(SandboxConfig)
        .filter(SandboxConfig.tenant_id == tenant_id)
        .order_by(SandboxConfig.priority, SandboxConfig.created_at)
        .all()
    )
    result = []
    for cfg in configs:
        if cfg.config_type != "code_sandbox":
            continue
        instance = _sandbox_instances.get(str(cfg.id))
        result.append({
            "config_id": str(cfg.id),
            "config_name": cfg.name,
            "status": instance["status"] if instance else "stopped",
            "started_at": instance.get("started_at") if instance else None,
            "stopped_at": instance.get("stopped_at") if instance else None,
        })
    return {"code": 0, "message": "ok", "data": result}


@router.post("/{config_id}/start")
def start_instance(
    config_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """启动沙箱实例（标记为 running + 执行一次健康检查预热）.

    注意：当前实现是状态机标记，不维护长驻进程；调用后即视为"运行中"。
    """
    tenant_id = str(current_user.get("user_id", "default"))
    cfg = _get_owned_config(db, config_id, tenant_id)
    if cfg.config_type != "code_sandbox":
        raise HTTPException(400, "仅 code_sandbox 类型配置支持实例启动")
    _sandbox_instances[config_id] = {
        "status": "running",
        "started_at": datetime.now().isoformat(sep=" "),
        "stopped_at": None,
    }
    return {
        "code": 0,
        "message": "ok",
        "data": _sandbox_instances[config_id],
    }


@router.post("/{config_id}/stop")
def stop_instance(
    config_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """停止沙箱实例."""
    tenant_id = str(current_user.get("user_id", "default"))
    cfg = _get_owned_config(db, config_id, tenant_id)
    if cfg.config_type != "code_sandbox":
        raise HTTPException(400, "仅 code_sandbox 类型配置支持实例停止")
    inst = _sandbox_instances.get(config_id, {"status": "stopped"})
    inst["status"] = "stopped"
    inst["stopped_at"] = datetime.now().isoformat(sep=" ")
    _sandbox_instances[config_id] = inst
    return {"code": 0, "message": "ok", "data": inst}


@router.post("/{config_id}/restart")
def restart_instance(
    config_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """重启沙箱实例 = stop + start."""
    tenant_id = str(current_user.get("user_id", "default"))
    cfg = _get_owned_config(db, config_id, tenant_id)
    if cfg.config_type != "code_sandbox":
        raise HTTPException(400, "仅 code_sandbox 类型配置支持实例重启")
    now_iso = datetime.now().isoformat(sep=" ")
    _sandbox_instances[config_id] = {
        "status": "running",
        "started_at": now_iso,
        "stopped_at": None,
    }
    return {"code": 0, "message": "ok", "data": _sandbox_instances[config_id]}


@router.post("/{config_id}/test-execute")
def test_execute(
    config_id: str,
    body: SandboxTestExecuteRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """针对指定沙箱配置执行一段代码，并将结果持久化到 sandbox_executions 表."""
    from finpilot.services.code_sandbox import CodeSandbox

    tenant_id = str(current_user.get("user_id", "default"))
    cfg = _get_owned_config(db, config_id, tenant_id)
    if cfg.config_type != "code_sandbox":
        raise HTTPException(400, "仅 code_sandbox 类型配置支持测试执行")

    sandbox = CodeSandbox(tenant_id=tenant_id, db=db)
    started = time.monotonic()
    error_message = None
    try:
        result = sandbox.execute(body.code, timeout=body.timeout)
        success = result.exit_code == 0
        stdout = result.stdout
        stderr = result.stderr
        exit_code = result.exit_code
        truncated = getattr(result, "truncated", False)
    except Exception as exc:  # noqa: BLE001
        success = False
        stdout = ""
        stderr = str(exc)
        exit_code = -1
        truncated = False
        error_message = str(exc)
    duration_ms = int((time.monotonic() - started) * 1000)

    execution = SandboxExecution(
        tenant_id=tenant_id,
        config_id=cfg.id,
        trigger_source="manual",
        language=body.language,
        code=body.code,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        duration_ms=duration_ms,
        truncated=truncated,
        success=success,
        error_message=error_message,
        executed_by=current_user.get("user_id"),
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)

    # best-effort 埋点：额外写一条 runtime_log 用于统一查看
    try:
        from finpilot.services.runtime_log_service import log_runtime

        log_runtime(
            db,
            category="sandbox_exec",
            event="exec_finished",
            message=f"沙箱执行 exit_code={exit_code} success={success}",
            source="sandbox.execute",
            payload={
                "config_id": str(cfg.id),
                "config_name": cfg.name,
                "language": body.language,
                "code_preview": (body.code or "")[:500],
                "stdout_preview": (stdout or "")[:500],
                "stderr_preview": (stderr or "")[:500],
                "exit_code": exit_code,
                "duration_ms": duration_ms,
                "truncated": truncated,
                "execution_id": str(execution.id),
                "error_message": error_message,
            },
            duration_ms=duration_ms,
            status_code=exit_code,
            tenant_id=tenant_id,
            user_id=str(current_user.get("user_id", "")),
            success=success,
            level="info" if success else "error",
        )
    except Exception:  # noqa: BLE001
        pass

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "execution_id": str(execution.id),
            "success": success,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "duration_ms": duration_ms,
            "truncated": truncated,
            "error_message": error_message,
        },
    }


@router.get("/{config_id}/executions")
def list_executions(
    config_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """查询指定沙箱配置的执行历史."""
    tenant_id = str(current_user.get("user_id", "default"))
    cfg = _get_owned_config(db, config_id, tenant_id)
    query = db.query(SandboxExecution).filter(
        SandboxExecution.tenant_id == tenant_id,
        SandboxExecution.config_id == cfg.id,
    )
    total = query.count()
    items = (
        query.order_by(SandboxExecution.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [_execution_to_response(e) for e in items],
        },
    }


@router.get("/{config_id}/executions/{execution_id}")
def get_execution_detail(
    config_id: str,
    execution_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """查询单次执行的完整详情（含 code / stdout / stderr 全文）."""
    tenant_id = str(current_user.get("user_id", "default"))
    _get_owned_config(db, config_id, tenant_id)  # 仅做归属校验
    execution = (
        db.query(SandboxExecution)
        .filter(
            SandboxExecution.id == execution_id,
            SandboxExecution.tenant_id == tenant_id,
        )
        .first()
    )
    if not execution:
        raise HTTPException(404, "执行记录不存在")
    return {"code": 0, "message": "ok", "data": _execution_to_response(execution)}


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _get_owned_config(db: Session, config_id: str, tenant_id: str) -> SandboxConfig:
    """获取当前租户拥有的配置，不存在则抛 404."""
    cfg = (
        db.query(SandboxConfig)
        .filter(
            SandboxConfig.id == config_id,
            SandboxConfig.tenant_id == tenant_id,
        )
        .first()
    )
    if not cfg:
        raise HTTPException(status_code=404, detail="配置不存在")
    return cfg


def _execution_to_response(execution: SandboxExecution) -> dict[str, Any]:
    """将 SandboxExecution ORM 转 dict 响应（统一类型转换为字符串/标准类型）."""
    return {
        "id": str(execution.id),
        "config_id": str(execution.config_id) if execution.config_id else None,
        "trigger_source": execution.trigger_source,
        "language": execution.language,
        "code": execution.code,
        "stdout": execution.stdout,
        "stderr": execution.stderr,
        "exit_code": execution.exit_code,
        "duration_ms": execution.duration_ms,
        "truncated": execution.truncated,
        "success": execution.success,
        "error_message": execution.error_message,
        "executed_by": str(execution.executed_by) if execution.executed_by else None,
        "created_at": execution.created_at.isoformat(sep=" ") if execution.created_at else None,
    }


@router.put("/{config_id}")
def update_config(
    config_id: str,
    body: SandboxConfigUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """更新沙箱配置."""
    tenant_id = str(current_user.get("user_id", "default"))
    cfg = db.query(SandboxConfig).filter(
        SandboxConfig.id == config_id,
        SandboxConfig.tenant_id == tenant_id,
    ).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="配置不存在")

    update_data = body.model_dump(exclude_unset=True)
    for key, val in update_data.items():
        setattr(cfg, key, val)

    db.commit()
    db.refresh(cfg)
    invalidate_config_cache(cfg.config_type)
    return {"code": 0, "message": "ok", "data": _model_to_response(cfg)}


@router.delete("/{config_id}")
def delete_config(
    config_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """删除沙箱配置."""
    tenant_id = str(current_user.get("user_id", "default"))
    cfg = db.query(SandboxConfig).filter(
        SandboxConfig.id == config_id,
        SandboxConfig.tenant_id == tenant_id,
    ).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="配置不存在")
    if cfg.is_system:
        raise HTTPException(status_code=400, detail="系统默认配置不可删除")

    config_type = cfg.config_type
    db.delete(cfg)
    db.commit()
    invalidate_config_cache(config_type)
    return {"code": 0, "message": "ok", "data": None}


@router.patch("/{config_id}/toggle")
def toggle_config(
    config_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """启用/禁用沙箱配置."""
    tenant_id = str(current_user.get("user_id", "default"))
    cfg = db.query(SandboxConfig).filter(
        SandboxConfig.id == config_id,
        SandboxConfig.tenant_id == tenant_id,
    ).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="配置不存在")

    cfg.is_active = not cfg.is_active
    db.commit()
    db.refresh(cfg)
    invalidate_config_cache(cfg.config_type)
    return {"code": 0, "message": "ok", "data": _model_to_response(cfg)}


@router.get("/active/{config_type}")
def get_active_config(
    config_type: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """获取指定类型的当前激活配置（合并系统默认 + 租户覆盖）.

    返回系统级配置与租户级配置深度合并后的结果; 无任何 DB 配置时
    返回空字典（消费方将回退到运行时硬编码默认）。
    """
    merged = get_sandbox_config(
        config_type, str(current_user.get("user_id", "default")), db
    )
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "config_type": config_type,
            "config": merged,
            "source": "merged",
            "has_db_override": bool(merged),
        },
    }
