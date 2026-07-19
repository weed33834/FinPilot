# -*- coding: utf-8 -*-
"""公共依赖 - 会话管理、认证依赖、数据库会话。

简化版认证：
- 内存字典存 session（{session_id: {user_id, email, role, name}}），进程重启即失效
- 密码用 hashlib.sha256 存储（非生产级，仅演示）
- 通过 HttpOnly cookie 传递 session_id，前端配合 withCredentials
"""
from __future__ import annotations

import hashlib
import secrets
from typing import Optional

from fastapi import Depends, HTTPException, Request, status

# 内存会话表：session_id -> {user_id, email, role, name}
_sessions: dict[str, dict] = {}

# cookie 名称（与前端 withCredentials 配合）
SESSION_COOKIE = "session_id"


def hash_password(password: str) -> str:
    """sha256 哈希密码（简化版）"""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文密码与哈希是否一致"""
    return hash_password(plain) == hashed


def create_session(user_id: int, email: str, role: str, name: Optional[str] = None) -> str:
    """创建会话，返回 session_id 并存入内存表"""
    session_id = secrets.token_urlsafe(32)
    _sessions[session_id] = {
        "user_id": user_id,
        "email": email,
        "role": role,
        "name": name,
    }
    return session_id


def delete_session(session_id: str) -> None:
    """删除会话"""
    _sessions.pop(session_id, None)


def get_current_user(request: Request) -> dict:
    """从 cookie 或 Authorization Bearer 提取 session_id，返回当前用户信息；未登录抛 401.

    支持两种认证方式（任选其一）：
    1. HttpOnly cookie ``session_id``（前端 withCredentials 自动带）
    2. ``Authorization: Bearer <session_id>`` 头（API 客户端 / curl 测试用）
    """
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        # 回退到 Authorization: Bearer <token>
        auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            session_id = auth_header.split(" ", 1)[1].strip()
    if not session_id or session_id not in _sessions:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或会话已过期",
        )
    return _sessions[session_id]


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
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
