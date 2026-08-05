"""API 密钥管理路由 — 管理用户访问平台的 API Key.

提供 list / create / rotate / revoke / delete 能力。
创建与轮换时返回一次性明文 key（仅此一次），之后只存哈希。

对应前端：ApiKeysPage.tsx，调用 /api-keys 前缀。
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
try:
    from datetime import UTC
except ImportError:  # Python 3.10 lacks datetime.UTC; use timezone.utc
    from datetime import timezone
    UTC = timezone.utc
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from finpilot.api.deps import get_current_user, get_db_session
from finpilot.database.models import ApiKey

router = APIRouter(prefix="/api-keys", tags=["API Keys"])

# 明文 key 前缀，便于人工识别
_KEY_PREFIX = "fp_live_"


def _hash_key(plain: str) -> str:
    """SHA-256 哈希明文 key（与 deps.require_scope 一致）."""
    return hashlib.sha256(plain.encode()).hexdigest()


def _gen_plain_key() -> str:
    """生成新的明文 key：fp_live_ + 32 位随机 hex."""
    return f"{_KEY_PREFIX}{secrets.token_hex(16)}"


def _key_prefix_from_plain(plain: str) -> str:
    """从明文 key 提取展示前缀（前缀 + 前 8 位），用于列表识别."""
    return plain[: len(_KEY_PREFIX) + 8]


def _to_response(k: ApiKey) -> dict[str, Any]:
    """ORM 对象转响应字典（字段与前端 types/apiKey.ts 对齐）."""
    scopes_raw = k.scopes or ""
    scopes_list = [s.strip() for s in scopes_raw.split(",") if s.strip()]

    def _dt(v: datetime | None) -> str | None:
        return v.isoformat(sep=" ") if v else None

    return {
        "id": str(k.id),
        "tenant_id": getattr(k, "tenant_id", None) or "",
        "user_id": str(k.user_id) if k.user_id is not None else "",
        "name": k.name or "",
        "scopes": scopes_list,
        # 前端期望 is_active 为 "Y"/"N" 字符串（与部分列表页 badge 逻辑一致）
        "is_active": "Y" if k.is_active else "N",
        "last_used_at": _dt(k.last_used_at),
        "first_used_at": _dt(getattr(k, "first_used_at", None)),
        "usage_count": getattr(k, "usage_count", 0) or 0,
        "expires_at": _dt(getattr(k, "expires_at", None)),
        "rotated_from": str(k.rotated_from) if getattr(k, "rotated_from", None) else None,
        "created_at": _dt(k.created_at),
        "updated_at": _dt(getattr(k, "updated_at", None)),
        # 列表展示用前缀（非明文）
        "key_prefix": getattr(k, "key_prefix", None) or "",
    }


def _to_response_with_plain(k: ApiKey, plain: str) -> dict[str, Any]:
    """创建/轮换后响应：附带一次性明文 key."""
    resp = _to_response(k)
    resp["key"] = plain
    return resp


@router.get("")
def list_api_keys(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """列出当前用户的 API Key（分页）."""
    user_id = current_user.get("user_id")
    tenant_id = f"user_{user_id}" if user_id is not None else "default"

    q = db.query(ApiKey).filter(ApiKey.user_id == user_id)
    # 兼容 tenant_id 字段（若存在则过滤）
    if hasattr(ApiKey, "tenant_id"):
        q = q.filter(ApiKey.tenant_id == tenant_id)

    total = q.count()
    items = (
        q.order_by(ApiKey.created_at.desc())
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
            "items": [_to_response(k) for k in items],
        },
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_api_key(
    payload: dict,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """创建 API Key，返回一次性明文 key."""
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name 不能为空")

    scopes_input = payload.get("scopes")
    if isinstance(scopes_input, list):
        scopes = ",".join(str(s).strip() for s in scopes_input if str(s).strip())
    else:
        scopes = str(scopes_input or "").strip()

    expires_at: datetime | None = None
    expires_raw = payload.get("expires_at")
    if expires_raw:
        try:
            expires_at = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="expires_at 格式无效，需 ISO 8601",
            )

    user_id = current_user.get("user_id")
    tenant_id = f"user_{user_id}" if user_id is not None else "default"
    plain = _gen_plain_key()

    key = ApiKey(
        user_id=user_id,
        tenant_id=tenant_id,
        key_hash=_hash_key(plain),
        key_prefix=_key_prefix_from_plain(plain),
        name=name,
        is_active=True,
        scopes=scopes,
        usage_count=0,
        expires_at=expires_at,
    )
    db.add(key)
    try:
        db.commit()
        db.refresh(key)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"创建失败: {exc}"
        ) from exc

    # 审计埋点
    try:
        from finpilot.services.audit_service import log_action

        log_action(
            db=db,
            action="api_key.create",
            resource=f"api_key:{key.id}",
            user=current_user,
            reason=f"创建 API Key: {name}",
            commit=False,
            target_object_type="api_key",
            target_object_id=str(key.id),
            meta={"name": name, "scopes": scopes},
        )
    except Exception:  # noqa: BLE001
        pass

    return {"code": 0, "message": "ok", "data": _to_response_with_plain(key, plain)}


@router.post("/{key_id}/rotate")
def rotate_api_key(
    key_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """轮换 API Key：吊销旧 Key，创建新 Key 并关联 rotated_from."""
    old = db.get(ApiKey, key_id)
    if not old:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API Key 不存在")
    if old.user_id != current_user.get("user_id"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作他人 API Key")
    if not old.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该 Key 已吊销，无需轮换")

    plain = _gen_plain_key()
    new_key = ApiKey(
        user_id=old.user_id,
        tenant_id=getattr(old, "tenant_id", None),
        key_hash=_hash_key(plain),
        key_prefix=_key_prefix_from_plain(plain),
        name=old.name,
        is_active=True,
        scopes=old.scopes,
        usage_count=0,
        expires_at=old.expires_at,
        rotated_from=old.id,
    )
    db.add(new_key)
    # 吊销旧 Key
    old.is_active = False
    try:
        db.commit()
        db.refresh(new_key)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"轮换失败: {exc}"
        ) from exc

    try:
        from finpilot.services.audit_service import log_action

        log_action(
            db=db,
            action="api_key.rotate",
            resource=f"api_key:{new_key.id}",
            user=current_user,
            reason=f"轮换 API Key，旧 id={old.id}",
            commit=False,
            target_object_type="api_key",
            target_object_id=str(new_key.id),
            meta={"rotated_from": old.id},
        )
    except Exception:  # noqa: BLE001
        pass

    return {"code": 0, "message": "ok", "data": _to_response_with_plain(new_key, plain)}


@router.post("/{key_id}/revoke")
def revoke_api_key(
    key_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """吊销 API Key（软删除，保留记录但立即失效）."""
    key = db.get(ApiKey, key_id)
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API Key 不存在")
    if key.user_id != current_user.get("user_id"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作他人 API Key")
    if not key.is_active:
        return {"code": 0, "message": "ok", "data": _to_response(key)}

    key.is_active = False
    key.updated_at = datetime.now(UTC)
    try:
        db.commit()
        db.refresh(key)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"吊销失败: {exc}"
        ) from exc

    try:
        from finpilot.services.audit_service import log_action

        log_action(
            db=db,
            action="api_key.revoke",
            resource=f"api_key:{key.id}",
            user=current_user,
            reason="吊销 API Key",
            commit=False,
            target_object_type="api_key",
            target_object_id=str(key.id),
        )
    except Exception:  # noqa: BLE001
        pass

    return {"code": 0, "message": "ok", "data": _to_response(key)}


@router.delete("/{key_id}", status_code=status.HTTP_200_OK)
def delete_api_key(
    key_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """删除 API Key（硬删除，不可恢复）."""
    key = db.get(ApiKey, key_id)
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API Key 不存在")
    if key.user_id != current_user.get("user_id"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作他人 API Key")

    try:
        db.delete(key)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"删除失败: {exc}"
        ) from exc

    try:
        from finpilot.services.audit_service import log_action

        log_action(
            db=db,
            action="api_key.delete",
            resource=f"api_key:{key_id}",
            user=current_user,
            reason="删除 API Key",
            commit=False,
            target_object_type="api_key",
            target_object_id=str(key_id),
        )
    except Exception:  # noqa: BLE001
        pass

    return {"code": 0, "message": "ok", "data": {"id": str(key_id), "deleted": True}}
