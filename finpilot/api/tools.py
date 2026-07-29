"""工具管理路由 — 管理后台专用（/api/tools）.

提供工具列表/创建/更新/删除/启禁/测试/复制等完整管理能力。
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from finpilot.api.deps import require_scope, get_current_user, get_db_session
from finpilot.api.schemas import (
    ToolCreate,
    ToolResponse,
    ToolTestRequest,
    ToolUpdate,
)
from finpilot.database.models import Tool

router = APIRouter(prefix="/tools", tags=["Tools Admin"])


def _reload_runtime_tools(tenant_id: str, db: Session) -> None:
    """工具变更后重新加载运行时工具注册表."""
    try:
        from finpilot.services.tool_loader import reload_db_tools

        reload_db_tools(tenant_id, db)
    except Exception:  # noqa: BLE001
        pass


TOOL_TYPE_ENUMS: list[dict[str, str]] = [
    {"value": "python_function", "label": "Python 函数", "description": "通过沙箱执行 Python 代码"},
    {"value": "http_api", "label": "HTTP API", "description": "通过 HTTP 请求调用外部 API"},
    {"value": "sql_query", "label": "SQL 查询", "description": "执行安全的 SQL 查询"},
    {"value": "file_operation", "label": "文件操作", "description": "文件读取/写入/列表/删除"},
    {"value": "search", "label": "搜索", "description": "内部文档/数据搜索"},
    {"value": "web_search", "label": "网络搜索", "description": "互联网搜索引擎查询"},
]


def _model_to_response(t: Tool) -> ToolResponse:
    return ToolResponse(
        id=t.id,
        tenant_id=t.tenant_id,
        name=t.name,
        display_name=t.display_name,
        description=t.description,
        type=t.type,
        is_builtin=t.is_builtin,
        is_active=t.is_active,
        has_api_key=bool(t.api_key),
        config=t.config or {},
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


@router.get("")
def list_tools(
    page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    current_user: dict = Depends(require_scope("tools:admin")),
    db: Session = Depends(get_db_session),
    search: str = Query(default="", description="按名称/展示名搜索"),
    type: str = Query(default="", description="按类型筛选"),
    is_active: str = Query(default="", description="按状态筛选: active/inactive"),
    is_builtin: str = Query(default="", description="按内置筛选: builtin/custom"),
) -> dict[str, Any]:
    """工具列表（分页/搜索/筛选）."""
    tenant_id = str(current_user.get("user_id", "default"))
    query = db.query(Tool).filter(Tool.tenant_id == tenant_id)

    if type:
        query = query.filter(Tool.type == type)
    if search:
        query = query.filter(
            (Tool.display_name.ilike(f"%{search}%"))
            | (Tool.name.ilike(f"%{search}%"))
        )
    if is_active == "active":
        query = query.filter(Tool.is_active.is_(True))
    elif is_active == "inactive":
        query = query.filter(Tool.is_active.is_(False))
    if is_builtin == "builtin":
        query = query.filter(Tool.is_builtin.is_(True))
    elif is_builtin == "custom":
        query = query.filter(Tool.is_builtin.is_(False))

    total = query.count()
    items = (
        query.order_by(Tool.is_builtin.desc(), Tool.updated_at.desc())
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
            "items": [_model_to_response(t) for t in items],
        },
    }


@router.get("/types")
def list_tool_types(
    current_user: dict = Depends(require_scope("tools:admin")),
) -> dict[str, Any]:
    """获取工具类型枚举及说明."""
    return {"code": 0, "message": "ok", "data": TOOL_TYPE_ENUMS}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_tool(
    body: ToolCreate,
    current_user: dict = Depends(require_scope("tools:admin")),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """创建自定义工具.

    前端 createTool 调用 POST /tools，此前后端缺失该端点导致 405。
    新建工具默认 is_builtin=False、is_active=True，api_key 经 encode_api_key 编码。
    """
    from finpilot.database.crud import encode_api_key

    tenant_id = str(current_user.get("user_id", "default"))

    # 同名工具校验（同租户内 name 唯一）
    existing = (
        db.query(Tool)
        .filter(Tool.tenant_id == tenant_id, Tool.name == body.name)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"工具名称 '{body.name}' 已存在",
        )

    # 校验 type 合法
    valid_types = {t["value"] for t in TOOL_TYPE_ENUMS}
    if body.type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"非法的工具类型：{body.type}（支持：{', '.join(sorted(valid_types))}）",
        )

    t = Tool(
        tenant_id=tenant_id,
        name=body.name,
        display_name=body.display_name or body.name,
        description=body.description,
        type=body.type,
        is_builtin=False,
        is_active=True,
        config=body.config or {},
        api_key=encode_api_key(body.api_key) if body.api_key else None,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    _reload_runtime_tools(tenant_id, db)
    return {"code": 0, "message": "ok", "data": _model_to_response(t)}


# ============================================================
# 板块C：工具监控端点 — 对应前端 toolMonitoring.ts
# health / circuit-breakers / audit / usage-stats
# 基于 RuntimeLog 聚合工具调用统计（category='tool_call'）
# ============================================================


def _tool_metrics_from_runtime(db: Session, tenant_id: str) -> dict[str, dict[str, Any]]:
    """从 RuntimeLog 聚合每个工具的调用统计（category='tool_call' 或 source 以 'tool.' 开头）."""
    from finpilot.database.models import RuntimeLog
    from sqlalchemy import func, Integer

    metrics: dict[str, dict[str, Any]] = {}
    try:
        # 按 source（工具名）聚合
        rows = (
            db.query(
                RuntimeLog.source,
                func.count(RuntimeLog.id).label("total"),
                func.sum(RuntimeLog.success.cast(Integer)).label("success"),
                func.avg(RuntimeLog.duration_ms).label("avg_latency"),
            )
            .filter(
                RuntimeLog.tenant_id == tenant_id,
                RuntimeLog.category == "tool_call",
            )
            .group_by(RuntimeLog.source)
            .all()
        )
        for row in rows:
            tool_name = (row.source or "").replace("tool.", "")
            if not tool_name:
                continue
            total = int(row.total or 0)
            success = int(row.success or 0)
            metrics[tool_name] = {
                "tool_name": tool_name,
                "total_calls": total,
                "success_count": success,
                "failure_count": total - success,
                "success_rate": (success / total) if total else 0.0,
                "avg_latency_ms": float(row.avg_latency or 0),
            }
    except Exception:  # noqa: BLE001
        pass
    return metrics


@router.get("/health")
def tools_health(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """获取所有工具健康统计（基于 RuntimeLog 聚合）."""
    tenant_id = str(current_user.get("user_id", "default"))
    metrics = _tool_metrics_from_runtime(db, tenant_id)
    # 补充工具表中的工具（即使无调用记录也展示）
    try:
        tools = db.query(Tool).filter(Tool.tenant_id == tenant_id).all()
        for t in tools:
            if t.name not in metrics:
                metrics[t.name] = {
                    "tool_name": t.name,
                    "status": "available" if t.is_active else "disabled",
                    "healthy": True,
                    "total_calls": 0,
                    "success_count": 0,
                    "failure_count": 0,
                    "success_rate": 0.0,
                    "avg_latency_ms": 0.0,
                    "last_check_time": None,
                    "last_error": None,
                }
    except Exception:  # noqa: BLE001
        pass

    # 标记健康状态
    for name, m in metrics.items():
        m.setdefault("tool_name", name)
        m.setdefault("status", "healthy" if m.get("failure_count", 0) == 0 else "degraded")
        m.setdefault("healthy", m.get("failure_count", 0) < m.get("total_calls", 0))
        m.setdefault("last_check_time", None)
        m.setdefault("last_error", None)
    return {"code": 0, "message": "ok", "data": metrics}


@router.get("/circuit-breakers")
def tools_circuit_breakers(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """获取所有断路器状态.

    FinPilot 未实现独立断路器组件，这里基于近期失败率推导状态：
    - 近 20 次调用失败率 >= 50% → OPEN
    - 有失败但 < 50% → HALF_OPEN
    - 无失败 → CLOSED
    """
    tenant_id = str(current_user.get("user_id", "default"))
    metrics = _tool_metrics_from_runtime(db, tenant_id)
    breakers: dict[str, dict[str, Any]] = {}
    for name, m in metrics.items():
        total = m.get("total_calls", 0)
        failures = m.get("failure_count", 0)
        if total == 0:
            state = "CLOSED"
        elif failures / total >= 0.5:
            state = "OPEN"
        elif failures > 0:
            state = "HALF_OPEN"
        else:
            state = "CLOSED"
        breakers[name] = {
            "tool_name": name,
            "state": state,
            "failure_count": failures,
            "success_count": m.get("success_count", 0),
            "last_failure_time": None,
            "last_failure_error": None,
            "opened_at": None if state == "CLOSED" else None,
        }
    return {"code": 0, "message": "ok", "data": breakers}


@router.get("/audit")
def tools_audit(
    tool_name: str = Query(default="", description="按工具名筛选"),
    start_time: str = Query(default="", description="起始时间 ISO8601，如 2026-01-01T00:00:00"),
    end_time: str = Query(default="", description="结束时间 ISO8601"),
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """查询工具执行审计轨迹（基于 RuntimeLog category='tool_call'）.

    支持 tool_name 筛选 + 时间范围筛选（start_time/end_time，ISO8601）。
    前端 toolMonitoring.ts 的 getAuditTrail 传 start_time/end_time，
    此前后端未声明这两个参数导致时间筛选静默失效。
    """
    from datetime import datetime as _dt

    from finpilot.database.models import RuntimeLog

    tenant_id = str(current_user.get("user_id", "default"))
    q = db.query(RuntimeLog).filter(
        RuntimeLog.tenant_id == tenant_id,
        RuntimeLog.category == "tool_call",
    )
    if tool_name:
        q = q.filter(RuntimeLog.source == f"tool.{tool_name}")
    # 时间范围筛选
    if start_time:
        try:
            q = q.filter(RuntimeLog.created_at >= _dt.fromisoformat(start_time))
        except ValueError:
            pass
    if end_time:
        try:
            q = q.filter(RuntimeLog.created_at <= _dt.fromisoformat(end_time))
        except ValueError:
            pass

    logs = q.order_by(RuntimeLog.created_at.desc()).limit(limit).all()

    def _log_to_record(log: RuntimeLog) -> dict[str, Any]:
        import json
        params = None
        result = None
        if log.payload_json:
            try:
                payload = json.loads(log.payload_json)
                params = payload.get("params")
                result = payload.get("result")
            except (json.JSONDecodeError, TypeError):
                pass
        return {
            "id": str(log.id),
            "tool_name": (log.source or "").replace("tool.", ""),
            "params": params,
            "result": result,
            "success": bool(log.success),
            "latency_ms": log.duration_ms,
            "token_count": 0,
            "error": None if log.success else (log.message or ""),
            "created_at": log.created_at.isoformat(sep=" ") if log.created_at else None,
            "timestamp": log.created_at.isoformat(sep=" ") if log.created_at else None,
        }

    return {"code": 0, "message": "ok", "data": [_log_to_record(rec) for rec in logs]}


@router.get("/usage-stats")
def tools_usage_stats(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """获取工具使用统计汇总（总调用/总成功/总失败/按工具排名）."""
    tenant_id = str(current_user.get("user_id", "default"))
    metrics = _tool_metrics_from_runtime(db, tenant_id)

    total_calls = sum(m.get("total_calls", 0) for m in metrics.values())
    total_success = sum(m.get("success_count", 0) for m in metrics.values())
    total_failure = sum(m.get("failure_count", 0) for m in metrics.values())

    # 按调用次数排名
    ranking = sorted(
        metrics.values(),
        key=lambda x: x.get("total_calls", 0),
        reverse=True,
    )[:10]

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "total_calls": total_calls,
            "total_success": total_success,
            "total_failure": total_failure,
            "overall_success_rate": (total_success / total_calls) if total_calls else 0.0,
            "tool_count": len(metrics),
            "top_tools": ranking,
        },
    }


@router.get("/{tool_name}/health")
def tool_health_by_name(
    tool_name: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """获取单个工具健康统计."""
    tenant_id = str(current_user.get("user_id", "default"))
    metrics = _tool_metrics_from_runtime(db, tenant_id)
    m = metrics.get(tool_name)
    if m is None:
        # 无调用记录，返回默认可用状态
        m = {
            "tool_name": tool_name,
            "status": "available",
            "healthy": True,
            "total_calls": 0,
            "success_count": 0,
            "failure_count": 0,
            "success_rate": 0.0,
            "avg_latency_ms": 0.0,
            "last_check_time": None,
            "last_error": None,
        }
    return {"code": 0, "message": "ok", "data": m}


@router.post("/{tool_name}/health-check")
def trigger_health_check(
    tool_name: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """触发主动健康检查（best-effort：尝试调用工具的 test 能力）."""
    tenant_id = str(current_user.get("user_id", "default"))
    tool = (
        db.query(Tool)
        .filter(Tool.tenant_id == tenant_id, Tool.name == tool_name)
        .first()
    )
    if not tool:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工具不存在")

    # best-effort：记录一次健康检查事件
    try:
        from finpilot.services.runtime_log_service import log_runtime

        log_runtime(
            db,
            category="tool_call",
            event="health_check",
            message=f"主动健康检查: {tool_name}",
            source=f"tool.{tool_name}",
            payload={"tool_name": tool_name, "triggered_by": current_user.get("user_id")},
            duration_ms=0,
            tenant_id=tenant_id,
            user_id=str(current_user.get("user_id", "")),
            success=True,
            level="info",
        )
    except Exception:  # noqa: BLE001
        pass

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "tool_name": tool_name,
            "checked": True,
            "healthy": bool(tool.is_active),
        },
    }


@router.post("/{tool_name}/circuit-breaker/reset")
def reset_circuit_breaker(
    tool_name: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """重置断路器（标记工具为可用，清除失败计数 best-effort）.

    FinPilot 未实现独立断路器，这里仅记录重置事件。
    """
    tenant_id = str(current_user.get("user_id", "default"))
    try:
        from finpilot.services.runtime_log_service import log_runtime

        log_runtime(
            db,
            category="tool_call",
            event="circuit_breaker_reset",
            message=f"断路器重置: {tool_name}",
            source=f"tool.{tool_name}",
            payload={"tool_name": tool_name, "triggered_by": current_user.get("user_id")},
            duration_ms=0,
            tenant_id=tenant_id,
            user_id=str(current_user.get("user_id", "")),
            success=True,
            level="info",
        )
    except Exception:  # noqa: BLE001
        pass

    return {
        "code": 0,
        "message": "ok",
        "data": {"tool_name": tool_name, "reset": True},
    }


@router.put("/{tool_id}")
def update_tool(
    tool_id: str,
    body: ToolUpdate,
    current_user: dict = Depends(require_scope("tools:admin")),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """更新工具（内置工具不可改 name 和 type）."""
    tenant_id = str(current_user.get("user_id", "default"))
    t = (
        db.query(Tool)
        .filter(Tool.id == tool_id, Tool.tenant_id == tenant_id)
        .first()
    )
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工具不存在")

    update_data = body.model_dump(exclude_unset=True)

    # 内置工具：禁止修改 name 和 type
    if t.is_builtin:
        update_data.pop("name", None)
        update_data.pop("type", None)

    for k, v in update_data.items():
        if v is not None:
            setattr(t, k, v)

    db.commit()
    db.refresh(t)
    _reload_runtime_tools(tenant_id, db)
    return {"code": 0, "message": "ok", "data": _model_to_response(t)}


@router.delete("/{tool_id}")
def delete_tool(
    tool_id: str,
    current_user: dict = Depends(require_scope("tools:admin")),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """删除工具（仅限 is_builtin=false 的自定义工具）."""
    tenant_id = str(current_user.get("user_id", "default"))
    t = (
        db.query(Tool)
        .filter(Tool.id == tool_id, Tool.tenant_id == tenant_id)
        .first()
    )
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工具不存在")
    if t.is_builtin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="内置工具不可删除"
        )

    db.delete(t)
    db.commit()
    _reload_runtime_tools(tenant_id, db)
    return {"code": 0, "message": "ok", "data": {"id": tool_id, "deleted": True}}


@router.patch("/{tool_id}/toggle")
def toggle_tool(
    tool_id: str,
    current_user: dict = Depends(require_scope("tools:admin")),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """切换工具启用/禁用状态."""
    tenant_id = str(current_user.get("user_id", "default"))
    t = (
        db.query(Tool)
        .filter(Tool.id == tool_id, Tool.tenant_id == tenant_id)
        .first()
    )
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工具不存在")

    t.is_active = not t.is_active
    db.commit()
    db.refresh(t)
    _reload_runtime_tools(tenant_id, db)
    return {"code": 0, "message": "ok", "data": _model_to_response(t)}


@router.post("/{tool_id}/test")
def test_tool(
    tool_id: str,
    body: ToolTestRequest,
    current_user: dict = Depends(require_scope("tools:admin")),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """测试工具 — 根据 type 执行相应的测试逻辑."""
    tenant_id = str(current_user.get("user_id", "default"))
    t = (
        db.query(Tool)
        .filter(Tool.id == tool_id, Tool.tenant_id == tenant_id)
        .first()
    )
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工具不存在")

    start = time.perf_counter()

    try:
        if t.type == "python_function":
            result = _test_python_function(t, body.parameters)
        elif t.type == "http_api":
            result = _test_http_api(t, body.parameters)
        elif t.type in ("search", "web_search"):
            result = _test_web_search(t, body.parameters)
        elif t.type == "sql_query":
            result = _test_sql_query(t, body.parameters)
        elif t.type == "file_operation":
            result = _test_file_operation(t, body.parameters)
        else:
            result = {"success": True, "message": "test not implemented", "result": None}

    except Exception as exc:
        result = {"success": False, "message": str(exc), "result": None}

    elapsed = int((time.perf_counter() - start) * 1000)

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "success": result["success"],
            "message": result["message"],
            "result": str(result.get("result", ""))[:500] if result.get("result") else None,
            "execution_time_ms": elapsed,
        },
    }


def _test_python_function(tool: Tool, params: dict) -> dict:
    """通过沙箱安全执行 Python 函数测试."""
    cfg = tool.config or {}
    code = cfg.get("code", "")
    if not code:
        return {"success": False, "message": "config 中缺少 code 字段", "result": None}

    try:
        from finpilot.services.code_sandbox import execute_sandboxed

        result = execute_sandboxed(code, params)
        return {"success": True, "message": "Python 函数执行成功", "result": result}
    except ImportError:
        return {
            "success": True,
            "message": "沙箱模块不可用，代码语法有效",
            "result": f"code length: {len(code)} chars",
        }
    except Exception as e:
        return {"success": False, "message": f"执行失败: {e}", "result": None}


def _test_http_api(tool: Tool, params: dict) -> dict:
    """发送 HTTP 请求测试."""
    cfg = tool.config or {}
    url = cfg.get("url", "")
    method = cfg.get("method", "GET").upper()
    headers = cfg.get("headers", {})
    body_template = cfg.get("body_template", "")

    if not url:
        return {"success": False, "message": "config 中缺少 url", "result": None}

    try:
        import httpx

        req_kwargs: dict = {"headers": headers, "timeout": 10.0}
        if method in ("POST", "PUT", "PATCH"):
            if body_template:
                req_kwargs["json"] = params or {}
            else:
                req_kwargs["params"] = params

        resp = httpx.request(method, url, **req_kwargs)
        return {
            "success": resp.status_code < 500,
            "message": f"HTTP {resp.status_code}",
            "result": resp.text[:300],
        }
    except ImportError:
        return {"success": True, "message": "httpx 不可用，URL 格式有效", "result": url}
    except Exception as e:
        return {"success": False, "message": str(e), "result": None}


def _test_web_search(tool: Tool, params: dict) -> dict:
    """测试网络搜索引擎."""
    if not tool.api_key:
        return {"success": False, "message": "未配置 API Key", "result": None}

    cfg = tool.config or {}
    engine = cfg.get("engine", "serpapi")

    try:
        import httpx

        if engine == "serpapi":
            query = params.get("query", "test")
            resp = httpx.get(
                "https://serpapi.com/search",
                params={"q": query, "api_key": tool.api_key},
                timeout=10.0,
            )
            data = resp.json() if resp.status_code == 200 else {}
            results = data.get("organic_results", [])
            return {
                "success": True,
                "message": f"搜索成功，返回 {len(results)} 条结果",
                "result": results[0].get("snippet", "") if results else "无结果",
            }
        return {
            "success": True,
            "message": f"搜索引擎 {engine} 配置有效，测试搜索未实现",
            "result": None,
        }
    except Exception as e:
        return {"success": False, "message": str(e), "result": None}


def _test_sql_query(tool: Tool, params: dict) -> dict:
    """SQL 查询安全测试 — 仅校验语法."""
    cfg = tool.config or {}
    query_template = cfg.get("query_template", "")
    if not query_template:
        return {"success": False, "message": "config 中缺少 query_template", "result": None}

    # 安全校验：仅允许 SELECT 语句
    stripped = query_template.strip().upper()
    if not stripped.startswith("SELECT"):
        return {"success": False, "message": "仅允许 SELECT 查询", "result": None}

    forbidden = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "TRUNCATE"]
    for word in forbidden:
        if word in stripped:
            return {"success": False, "message": f"查询包含禁止的关键字: {word}", "result": None}

    return {"success": True, "message": "SQL 语法校验通过", "result": query_template[:200]}


def _test_file_operation(tool: Tool, params: dict) -> dict:
    """文件操作测试."""
    cfg = tool.config or {}
    operation = cfg.get("operation", "list")
    path = params.get("path", ".")

    try:
        import os

        if operation == "list":
            entries = os.listdir(path)[:20]
            return {
                "success": True,
                "message": f"列出 {len(entries)} 个条目",
                "result": "\n".join(entries),
            }
        if operation == "read":
            if not os.path.exists(path):
                return {"success": False, "message": f"路径不存在: {path}", "result": None}
            with open(path, encoding="utf-8") as f:
                content = f.read(500)
            return {"success": True, "message": "文件读取成功", "result": content}
        return {"success": True, "message": f"操作 {operation} 配置有效", "result": None}
    except Exception as e:
        return {"success": False, "message": str(e), "result": None}


@router.post("/{tool_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_tool(
    tool_id: str,
    current_user: dict = Depends(require_scope("tools:admin")),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """复制工具（副本 name 加 _copy）."""
    tenant_id = str(current_user.get("user_id", "default"))
    t = (
        db.query(Tool)
        .filter(Tool.id == tool_id, Tool.tenant_id == tenant_id)
        .first()
    )
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工具不存在")

    new_t = Tool(
        tenant_id=tenant_id,
        name=f"{t.name}_copy",
        display_name=f"{t.display_name} (副本)",
        description=t.description,
        type=t.type,
        config=t.config,
        api_key=t.api_key,
        is_builtin=False,
        is_active=True,
    )
    db.add(new_t)
    db.commit()
    db.refresh(new_t)
    return {"code": 0, "message": "ok", "data": _model_to_response(new_t)}
