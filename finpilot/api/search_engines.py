# -*- coding: utf-8 -*-
"""``/search-engines`` —— SearchEngine CRUD（对接前端 SearchEngineManagement 页）。

板块D：SearchEngine 已补齐 tenant_id / extra_params / priority 列并继承
TenantMixin，前端表单字段全部持久化，不再硬编码回显；api_key 经 encode_api_key 编码。

本模块从原 ``compat.py`` 拆分而来，行为与原 ``search_engines_router`` 完全一致。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from finpilot.database.crud import encode_api_key
from finpilot.database.models import SearchEngine

from ._compat_helpers import ok, parse_int_id
from .deps import get_db_session, require_admin, tenant_of

router = APIRouter(prefix="/search-engines", tags=["search-engines"])


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
    pk = parse_int_id(_id, "搜索引擎")
    q = db.query(SearchEngine).filter(SearchEngine.id == pk)
    if tenant_id:
        q = q.filter(SearchEngine.tenant_id == tenant_id)
    se = q.first()
    if not se:
        raise HTTPException(status_code=404, detail=f"搜索引擎 {_id} 不存在")
    return se


@router.get("")
def list_search_engines(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """列出当前租户的搜索引擎配置（默认的排在前面，再按 priority 升序）。"""
    tenant_id = tenant_of(current_user)
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
    return ok([_serialize_search_engine(se) for se in rows])


@router.get("/types")
def list_search_engine_types(_: dict = Depends(require_admin)):
    return ok([
        {"value": "bing", "label": "Bing"},
        {"value": "google", "label": "Google"},
        {"value": "duckduckgo", "label": "DuckDuckGo"},
        {"value": "serpapi", "label": "SerpAPI"},
    ])


@router.post("")
def create_search_engine(
    payload: SearchEngineCreatePayload,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """创建搜索引擎配置。api_key 经 encode_api_key 编码后存储。"""
    tenant_id = tenant_of(current_user)
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
    return ok(_serialize_search_engine(se), "搜索引擎已创建")


@router.put("/{_id}")
def update_search_engine(
    _id: str,
    payload: SearchEngineUpdatePayload,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """更新搜索引擎配置。"""
    tenant_id = tenant_of(current_user)
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
    return ok(_serialize_search_engine(se), "搜索引擎已更新")


@router.delete("/{_id}")
def delete_search_engine(
    _id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """删除搜索引擎配置。"""
    se = _get_search_engine_or_404(db, _id, tenant_of(current_user))
    db.delete(se)
    db.commit()
    return ok({"id": _id, "deleted": True}, "已删除")


@router.patch("/{_id}/toggle")
def toggle_search_engine(
    _id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """切换搜索引擎启用/禁用。"""
    se = _get_search_engine_or_404(db, _id, tenant_of(current_user))
    se.is_active = not se.is_active
    db.commit()
    db.refresh(se)
    return ok(_serialize_search_engine(se), "已切换")


@router.put("/{_id}/set-default")
def set_default_search_engine(
    _id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """将指定搜索引擎设为默认（其余取消默认）。"""
    tenant_id = tenant_of(current_user)
    se = _get_search_engine_or_404(db, _id, tenant_id)
    db.query(SearchEngine).filter(
        SearchEngine.id != se.id,
        SearchEngine.tenant_id == tenant_id,
        SearchEngine.is_default.is_(True),
    ).update({SearchEngine.is_default: False})
    se.is_default = True
    db.commit()
    db.refresh(se)
    return ok(_serialize_search_engine(se), "已设为默认")


@router.post("/{_id}/test")
def test_search_engine(
    _id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """测试搜索引擎 —— 真实发起一次搜索请求验证配置是否可用。

    复用 agent.web_tools._run_search 的引擎分发逻辑，用固定测试词「FinPilot 财务分析」
    发起真实请求，返回首条结果摘要。配置缺失或请求失败时返回 success=False 与原因。
    """
    se = _get_search_engine_or_404(db, _id, tenant_of(current_user))
    issues = []
    if not se.base_url and se.engine_type != "bing":
        # bing 有官方默认 endpoint，其余需显式 base_url
        issues.append("缺少 API base URL")
    if not se.api_key and se.engine_type in ("google", "bing", "serpapi"):
        issues.append(f"{se.engine_type} 通常需要 API Key")
    if issues:
        return ok({
            "success": False,
            "message": "配置可能不完整：" + "；".join(issues),
            "result_count": None,
            "first_snippet": None,
        })

    # 真实发起搜索请求（复用 agent 联网工具的引擎分发逻辑）
    from finpilot.agent.web_tools import _run_search

    try:
        results = _run_search(se, "FinPilot 财务分析", se.max_results or 5)
    except Exception as exc:  # noqa: BLE001
        return ok({
            "success": False,
            "message": f"测试请求异常：{exc}",
            "result_count": 0,
            "first_snippet": None,
        })

    errors = [r for r in results if isinstance(r, dict) and "error" in r]
    clean = [r for r in results if isinstance(r, dict) and "error" not in r]
    if errors:
        return ok({
            "success": False,
            "message": errors[0]["error"],
            "result_count": 0,
            "first_snippet": None,
        })
    if not clean:
        return ok({
            "success": False,
            "message": "搜索未返回任何结果，请检查配置或更换查询词",
            "result_count": 0,
            "first_snippet": None,
        })

    first = clean[0]
    return ok({
        "success": True,
        "message": f"搜索引擎「{se.name}」配置可用，返回 {len(clean)} 条结果",
        "result_count": len(clean),
        "first_snippet": f"{first.get('title', '')} — {first.get('snippet', '')}",
    })
