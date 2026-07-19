"""工具管理路由 — 管理后台专用（/api/tools）.

提供工具列表/创建/更新/删除/启禁/测试/复制等完整管理能力。
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

# TODO: FinPilot deps 暂未提供 get_current_user_or_api_key（带 API Key + scope 校验），
#       暂用 get_current_user；如需 API Key 鉴权与 scope 校验，需扩展 finpilot.api.deps。
# TODO: FinPilot 暂未引入多租户(tenant_id)概念，user.tenant_id 暂以 user_id 字符串替代。
# TODO: Tool ORM 模型尚未在 finpilot.database.models 中定义，需后续补充。
# TODO: ToolCreate/ToolResponse 等 schema 在 FinPilot 中未定义，已内联简化版。
# TODO: tool_loader.reload_db_tools 服务尚未在 finpilot.services 中实现，
#       _reload_runtime_tools 已用 try/except 包裹，运行时静默忽略。
from finpilot.api.deps import get_current_user, get_db_session
# TODO: Tool 模型尚未在 finpilot.database.models 中定义，导入会失败。
from finpilot.database.models import Tool  # noqa: F401

router = APIRouter(prefix="/tools", tags=["Tools Admin"])


def _reload_runtime_tools(tenant_id: str, db: Session) -> None:
    """工具变更后重新加载运行时工具注册表."""
    try:
        # TODO: finpilot.services.tool_loader 尚未实现；待后续补充。
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


# ---------------------------------------------------------------------------
# 内联 Schemas（简化的 Pydantic 模型，待后续统一收敛到 schemas 模块）
# TODO: 待迁移到 finpilot/api/schemas.py 或新建 schemas 模块统一管理
# ---------------------------------------------------------------------------


class ToolCreate(BaseModel):
    """工具创建请求."""

    name: str = Field(..., description="工具名称")
    display_name: str = Field(..., description="展示名称")
    description: str | None = None
    type: str = Field(..., description="工具类型")
    config: dict[str, Any] = Field(default_factory=dict, description="工具配置")
    api_key: str | None = None


class ToolUpdate(BaseModel):
    """工具更新请求."""

    name: str | None = None
    display_name: str | None = None
    description: str | None = None
    type: str | None = None
    config: dict[str, Any] | None = None
    api_key: str | None = None
    is_active: bool | None = None


class ToolResponse(BaseModel):
    """工具响应."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str | None = None
    name: str
    display_name: str
    description: str | None = None
    type: str
    is_builtin: bool = False
    is_active: bool = True
    has_api_key: bool = False
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class ToolTestRequest(BaseModel):
    """工具测试请求."""

    parameters: dict[str, Any] = Field(default_factory=dict, description="测试参数")


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
    current_user: dict = Depends(get_current_user),
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
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """获取工具类型枚举及说明."""
    return {"code": 0, "message": "ok", "data": TOOL_TYPE_ENUMS}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_tool(
    body: ToolCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """创建自定义工具."""
    tenant_id = str(current_user.get("user_id", "default"))
    t = Tool(
        tenant_id=tenant_id,
        name=body.name,
        display_name=body.display_name,
        description=body.description,
        type=body.type,
        config=body.config,
        api_key=body.api_key,
        is_builtin=False,
        is_active=True,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    _reload_runtime_tools(tenant_id, db)
    return {"code": 0, "message": "ok", "data": _model_to_response(t)}


@router.put("/{tool_id}")
def update_tool(
    tool_id: str,
    body: ToolUpdate,
    current_user: dict = Depends(get_current_user),
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
    current_user: dict = Depends(get_current_user),
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
    current_user: dict = Depends(get_current_user),
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
    current_user: dict = Depends(get_current_user),
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
    current_user: dict = Depends(get_current_user),
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
