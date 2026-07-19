# -*- coding: utf-8 -*-
"""LLM 供应商与模型管理路由（管理员）。

响应统一包装为 ``{code, message, data}`` 格式，与前端 ``DataResponse<T>`` 契约对齐。

供应商：
- GET    /                          列出所有供应商（分页）
- POST   /                          创建供应商
- PUT    /{id}                      更新供应商
- DELETE /{id}                      删除供应商（级联删除其下模型）
- POST   /{id}/test                 测试供应商连通性

模型：
- GET    /{provider_id}/models      列出该供应商下所有模型
- POST   /{provider_id}/models      在该供应商下创建模型
- PUT    /models/{model_id}         更新模型
- DELETE /models/{model_id}         删除模型

api_key 在数据库中以 base64 编码存储（沿用 crud.encode_api_key）；
返回时仅暴露 has_api_key，不回传明文密钥。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from finpilot.database.crud import decode_api_key, encode_api_key
from finpilot.database.models import LlmModel, LlmProvider
from finpilot.llm.config import invalidate_cache

from .deps import get_db_session, require_admin
from .schemas import LlmProviderRequest

router = APIRouter(prefix="/llm-providers", tags=["llm-providers"])


# ---------------------------------------------------------------------------
# 响应包装工具：统一 {code, message, data} 格式（与前端 DataResponse<T> 对齐）
# ---------------------------------------------------------------------------
def _ok(data: Any, message: str = "success") -> dict:
    return {"code": 0, "message": message, "data": data}


def _provider_dict(p: LlmProvider) -> dict:
    """供应商 ORM -> dict（不回传明文 api_key）。

    last_tested_at / last_test_ok / last_test_message 后端不持久化，
    返回 None 让前端显示「未测试」；测试后前端会用响应数据更新本地状态。
    """
    return {
        "id": str(p.id),
        "name": p.name,
        "provider_type": p.provider_type,
        "base_url": p.base_url,
        "is_default": p.is_default,
        "is_active": p.is_active,
        "has_api_key": bool(p.api_key),
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": None,
        "last_tested_at": None,
        "last_test_ok": None,
        "last_test_message": None,
    }


def _model_dict(m: LlmModel) -> dict:
    """模型 ORM -> dict"""
    return {
        "id": str(m.id),
        "provider_id": str(m.provider_id),
        "model_name": m.model_name,
        "display_name": m.display_name or m.model_name,
        "tier": m.tier,
        "is_active": m.is_active,
        "created_at": None,
        "updated_at": None,
    }


# ---------------------------------------------------------------------------
# 供应商 CRUD
# ---------------------------------------------------------------------------
@router.get("")
def list_providers(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """列出所有 LLM 供应商（分页，默认一页 100 条）"""
    query = db.query(LlmProvider).order_by(LlmProvider.created_at.desc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return _ok({
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_provider_dict(p) for p in items],
    })


@router.post("")
def create_provider(
    req: LlmProviderRequest,
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """创建 LLM 供应商（支持一并创建模型）"""
    if req.is_default:
        db.query(LlmProvider).filter(LlmProvider.is_default.is_(True)).update(
            {LlmProvider.is_default: False}
        )
    p = LlmProvider(
        name=req.name,
        provider_type=req.provider_type,
        base_url=req.base_url,
        api_key=encode_api_key(req.api_key) if req.api_key else None,
        is_default=req.is_default,
        is_active=True,
    )
    db.add(p)
    db.flush()  # 拿到 p.id
    for m in req.models:
        db.add(LlmModel(
            provider_id=p.id,
            model_name=m.model_name,
            display_name=m.display_name or m.model_name,
            tier=m.tier or "medium",
            is_active=bool(m.is_active),
        ))
    db.commit()
    db.refresh(p)
    invalidate_cache()
    return _ok(_provider_dict(p), "供应商已创建")


@router.put("/{provider_id}")
def update_provider(
    provider_id: int,
    req: LlmProviderRequest,
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """更新 LLM 供应商（如提交了 models 字段，则全量替换该供应商下的模型）"""
    p = db.get(LlmProvider, provider_id)
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="供应商不存在")
    if req.is_default:
        db.query(LlmProvider).filter(
            LlmProvider.id != provider_id, LlmProvider.is_default.is_(True)
        ).update({LlmProvider.is_default: False})
    p.name = req.name
    p.provider_type = req.provider_type
    p.base_url = req.base_url
    # 仅在传入新 api_key 时更新，避免被清空
    if req.api_key:
        p.api_key = encode_api_key(req.api_key)
    p.is_default = req.is_default
    # 全量替换模型（仅在请求体携带 models 字段时；空列表也会清空）
    if req.models:
        db.query(LlmModel).filter(LlmModel.provider_id == provider_id).delete()
        for m in req.models:
            db.add(LlmModel(
                provider_id=provider_id,
                model_name=m.model_name,
                display_name=m.display_name or m.model_name,
                tier=m.tier or "medium",
                is_active=bool(m.is_active),
            ))
    db.commit()
    db.refresh(p)
    invalidate_cache()
    return _ok(_provider_dict(p), "供应商已更新")


@router.delete("/{provider_id}")
def delete_provider(
    provider_id: int,
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """删除 LLM 供应商（级联删除其下模型）"""
    p = db.get(LlmProvider, provider_id)
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="供应商不存在")
    db.delete(p)
    db.commit()
    invalidate_cache()
    return _ok(None, "已删除")


@router.post("/{provider_id}/test")
def test_provider(
    provider_id: int,
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """测试供应商连通性：构造 LLMClient 发送一次最小请求"""
    from finpilot.llm.client import LLMClient, LLMUnavailableError
    from finpilot.llm.config import LLMConfig

    p = db.get(LlmProvider, provider_id)
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="供应商不存在")
    # 取该供应商下首个激活模型，无则用占位模型名
    model = (
        db.query(LlmModel)
        .filter(LlmModel.provider_id == p.id, LlmModel.is_active.is_(True))
        .first()
    )
    model_name = model.model_name if model else "gpt-4o-mini"
    api_key = decode_api_key(p.api_key) if p.api_key else None
    config = LLMConfig(
        provider_type=p.provider_type,
        base_url=p.base_url,
        api_key=api_key,
        model_name=model_name,
    )

    tested_at = datetime.now().isoformat()
    start = __import__("time").perf_counter()
    try:
        client = LLMClient(config)
        # 用 verify_connection 而非 chat —— 前者不会触发 demo fallback，
        # 保证 401/网络错误等真实失败被如实上报给前端。
        client.verify_connection(max_tokens=10)
        latency_ms = int((__import__("time").perf_counter() - start) * 1000)
        return _ok({
            "ok": True,
            "message": "连通正常",
            "latency_ms": latency_ms,
            "tested_at": tested_at,
        })
    except LLMUnavailableError as exc:
        latency_ms = int((__import__("time").perf_counter() - start) * 1000)
        return _ok({
            "ok": False,
            "message": str(exc),
            "latency_ms": latency_ms,
            "tested_at": tested_at,
        })


# ---------------------------------------------------------------------------
# 模型 CRUD（挂载在 /llm-providers 下，但路径独立）
# ---------------------------------------------------------------------------
@router.get("/{provider_id}/models")
def list_models(
    provider_id: int,
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """列出指定供应商下的所有模型"""
    if not db.get(LlmProvider, provider_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="供应商不存在")
    items = (
        db.query(LlmModel)
        .filter(LlmModel.provider_id == provider_id)
        .order_by(LlmModel.id.asc())
        .all()
    )
    return _ok({"items": [_model_dict(m) for m in items]})


@router.post("/{provider_id}/models")
def create_model(
    provider_id: int,
    payload: dict,
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """在指定供应商下创建模型"""
    if not db.get(LlmProvider, provider_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="供应商不存在")
    model_name = (payload.get("model_name") or "").strip()
    if not model_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="model_name 不能为空")
    m = LlmModel(
        provider_id=provider_id,
        model_name=model_name,
        display_name=(payload.get("display_name") or model_name).strip(),
        tier=payload.get("tier") or "medium",
        is_active=bool(payload.get("is_active", True)),
    )
    db.add(m)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"创建失败: {exc}") from exc
    db.refresh(m)
    invalidate_cache()
    return _ok(_model_dict(m), "模型已创建")


@router.put("/models/{model_id}")
def update_model(
    model_id: int,
    payload: dict,
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """更新模型"""
    m = db.get(LlmModel, model_id)
    if not m:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模型不存在")
    if "model_name" in payload and payload["model_name"]:
        m.model_name = payload["model_name"]
    if "display_name" in payload and payload["display_name"]:
        m.display_name = payload["display_name"]
    elif "display_name" in payload:
        m.display_name = m.model_name
    if "tier" in payload and payload["tier"]:
        m.tier = payload["tier"]
    if "is_active" in payload:
        m.is_active = bool(payload["is_active"])
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"更新失败: {exc}") from exc
    db.refresh(m)
    invalidate_cache()
    return _ok(_model_dict(m), "模型已更新")


@router.delete("/models/{model_id}")
def delete_model(
    model_id: int,
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """删除模型"""
    m = db.get(LlmModel, model_id)
    if not m:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模型不存在")
    db.delete(m)
    db.commit()
    invalidate_cache()
    return _ok(None, "模型已删除")
