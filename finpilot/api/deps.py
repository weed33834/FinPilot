# -*- coding: utf-8 -*-
"""公共依赖 - 会话管理、认证依赖、数据库会话。

生产级认证：
- Redis 持久化 session（进程重启不丢失）
- 密码用 argon2id 存储（安全级）
- 通过 HttpOnly cookie 传递 session_id，前端配合 withCredentials
"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from finpilot.core.security import hash_password, verify_password  # noqa: F401  保留 re-export 兼容旧导入
from finpilot.core.session import session_store

# cookie 名称（与前端 withCredentials 配合）
SESSION_COOKIE = "session_id"


async def create_session(user_id: int, email: str, role: str, name: Optional[str] = None, tenant_id: Optional[str] = None) -> str:
    """创建 Redis 会话，返回 session_id。"""
    user_data = {
        "user_id": user_id,
        "email": email,
        "role": role,
        "name": name,
    }
    if tenant_id:
        user_data["tenant_id"] = tenant_id
    return await session_store.create(user_data)


async def delete_session(session_id: str) -> None:
    """删除 Redis 会话。"""
    await session_store.delete(session_id)


async def get_current_user(request: Request) -> dict:
    """从 cookie 或 Authorization Bearer 提取 session_id，从 Redis 读取用户信息。

    支持两种认证方式（任选其一）：
    1. HttpOnly cookie ``session_id``（前端 withCredentials 自动带）
    2. ``Authorization: Bearer <session_id>`` 头（API 客户端 / curl 测试用）
    """
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            session_id = auth_header.split(" ", 1)[1].strip()
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或会话已过期",
        )
    user_data = await session_store.get(session_id)
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或会话已过期",
        )
    # 每次访问刷新 TTL
    await session_store.refresh(session_id)
    return user_data


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """要求当前用户为管理员，否则抛 403"""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user


def get_db_session():
    """获取 finpilot 数据库会话（FastAPI 依赖注入，请求结束自动关闭）"""
    from finpilot.database import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_scope(required_scope: str):
    """API Key + Scope 认证依赖工厂。

    认证方式：从 X-API-Key header 或 api_key query param 读取 API Key，
    查 api_keys 表校验密钥有效性，验证 scope 匹配后返回用户 dict。

    Returns dict: {user_id, email, role, name, tenant_id, api_key_id, api_key_name}
    """
    from datetime import datetime, timezone

    from fastapi import Query
    from sqlalchemy.orm import Session

    from finpilot.database.models import ApiKey

    async def _dependency(
        request: Request,
        db: Session = Depends(get_db_session),
        api_key_param: str | None = Query(default=None, alias="api_key"),
    ) -> dict:
        api_key_value = request.headers.get("X-API-Key")
        if not api_key_value and api_key_param:
            api_key_value = api_key_param

        if not api_key_value:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="缺少 API Key（请通过 X-API-Key header 或 ?api_key= 参数传入）",
            )

        import hashlib
        key_hash = hashlib.sha256(api_key_value.encode()).hexdigest()

        api_key = db.query(ApiKey).filter(
            ApiKey.key_hash == key_hash,
            ApiKey.is_active.is_(True),
        ).first()

        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的 API Key",
            )

        allowed = {s.strip() for s in (api_key.scopes or "").split(",") if s.strip()}
        if required_scope not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API Key 未授权 scope: {required_scope}",
            )

        user = api_key.user
        if not user:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API Key 未关联有效用户",
            )

        api_key.last_used_at = datetime.now(timezone.utc)
        db.commit()

        return {
            "user_id": user.id,
            "email": user.email,
            "role": getattr(user, "role", "user"),
            "name": getattr(user, "name", None),
            "tenant_id": getattr(user, "tenant_id", None),
            "api_key_id": api_key.id,
            "api_key_name": api_key.name,
        }

    return _dependency
