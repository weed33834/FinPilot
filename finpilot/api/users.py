# -*- coding: utf-8 -*-
"""用户管理路由（管理员）。

响应统一包裹为 ``{code, message, data}`` 格式，与前端 useCrudResource 契约对齐。

- GET    /            分页列出用户
- POST   /            创建用户
- PUT    /{id}        更新用户信息
- DELETE /{id}        删除用户
- POST   /{id}/reset-password  重置用户密码
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from finpilot.database import crud
from finpilot.database.models import User

from .deps import get_db_session, hash_password, require_admin

router = APIRouter(prefix="/users", tags=["users"])


def _ok(data: Any, message: str = "success") -> dict:
    return {"code": 0, "message": message, "data": data}


def _user_dict(u: User) -> dict:
    """ORM -> 前端 User 结构（types/user.ts: { id, username, email, role, is_active, created_at }）。

    username 取 name 字段（业务用名），email 保留。
    is_active 以 'Y'/'N' 字符串返回，与前端 zod schema 对齐。
    """
    return {
        "id": str(u.id),
        "username": u.name or u.email or "",
        "email": u.email,
        "role": u.role or "viewer",
        "is_active": "Y" if u.is_active else "N",
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


@router.get("")
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """分页列出所有用户"""
    query = db.query(User).order_by(User.id.asc())
    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return _ok({
        "items": [_user_dict(u) for u in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.post("")
def create_user(
    payload: dict,
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """创建用户。

    前端 UsersPage 表单字段：username, email, password, role, is_active。
    """
    username = (payload.get("username") or "").strip()
    email = (payload.get("email") or "").strip() or None
    password = (payload.get("password") or "").strip()
    role = (payload.get("role") or "viewer").strip()
    is_active = str(payload.get("is_active", "Y")).upper() == "Y"

    if not username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名不能为空")
    if not password or len(password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码至少 8 位")

    # email 缺失时用 username 生成占位 email（crud 要求 email 唯一）
    if not email:
        email = f"{username}@finpilot.local"

    # 唯一性检查
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邮箱已被使用")

    try:
        user = crud.create_user(
            db,
            email=email,
            password_hash=hash_password(password),
            name=username,
            role=role,
        )
        # is_active 默认 True，如需关闭则显式更新
        if not is_active:
            user.is_active = False
            db.commit()
            db.refresh(user)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"创建失败: {exc}"
        ) from exc
    return _ok(_user_dict(user), "用户创建成功")


@router.put("/{user_id}")
def update_user(
    user_id: int,
    payload: dict,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """更新用户信息（不含密码，密码走 /reset-password）"""
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    if "username" in payload and payload["username"]:
        u.name = payload["username"]
    if "email" in payload and payload["email"]:
        new_email = payload["email"].strip()
        if new_email != u.email:
            # 唯一性检查
            if db.query(User).filter(User.email == new_email, User.id != user_id).first():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邮箱已被使用")
            u.email = new_email
    if "role" in payload and payload["role"]:
        u.role = payload["role"]
    if "is_active" in payload:
        u.is_active = str(payload["is_active"]).upper() == "Y"
    try:
        db.commit()
        db.refresh(u)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"更新失败: {exc}"
        ) from exc
    return _ok(_user_dict(u), "用户信息已更新")


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """删除用户（不允许删除自己）"""
    if str(current_user.get("user_id")) == str(user_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不允许删除当前登录用户")
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    try:
        db.delete(u)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"删除失败: {exc}"
        ) from exc
    return _ok(None, "用户已删除")


@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: int,
    payload: dict,
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """重置用户密码"""
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    new_password = (payload.get("password") or "").strip()
    if not new_password or len(new_password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码至少 8 位")
    u.password_hash = hash_password(new_password)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"重置失败: {exc}"
        ) from exc
    return _ok(None, "密码已重置")
