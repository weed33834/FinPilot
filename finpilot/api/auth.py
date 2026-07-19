# -*- coding: utf-8 -*-
"""认证路由 - session cookie 认证（与前端 authStore 契约对齐）.

前端契约（stores/authStore.ts）：
- POST /auth/login    入参 {username, password, remember_me}
                      返回 {code, message, data: {access_token, token_type, expires_in, requires_2fa}}
- GET  /auth/me       返回 {code, message, data: {id, username, role}}
- POST /auth/logout   返回 {code, message, data: null}
- POST /auth/register 入参 {email, password, name}（旧契约，保留兼容）

cookie 名 session_id，HttpOnly；access_token 字段值即为 session_id，
前端不直接使用 access_token（withCredentials 自动带 cookie）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from finpilot.database import crud

from .deps import (
    SESSION_COOKIE,
    create_session,
    delete_session,
    get_current_user,
    get_db_session,
    hash_password,
    verify_password,
)
from .schemas import LoginRequest, RegisterRequest

router = APIRouter(prefix="/auth", tags=["auth"])


def _ok(data, message: str = "ok", code: int = 0):
    """统一 {code, message, data} 包装"""
    return {"code": code, "message": message, "data": data}


def _resolve_user_identifier(login_req: LoginRequest):
    """username 字段可能是邮箱或用户名，统一解析为 email 用于查表"""
    # 优先使用显式 email，否则把 username 当 email 处理
    return login_req.email or login_req.username


@router.post("/login")
def login(
    req: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session),
):
    """验证用户名/邮箱密码，设置 session cookie，返回 access_token（即 session_id）"""
    email = _resolve_user_identifier(req)
    user = crud.get_user_by_email(db, email)
    if not user or not user.password_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")
    if not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")

    # 创建内存会话并写入 HttpOnly cookie
    session_id = create_session(user.id, user.email, user.role, user.name)
    max_age = 30 * 24 * 60 * 60 if req.remember_me else 7 * 24 * 60 * 60
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_id,
        httponly=True,
        max_age=max_age,
        samesite="lax",
    )
    # access_token = session_id，前端 withCredentials 会自动带 cookie，
    # access_token 字段仅用于满足前端 LoginData 契约
    return _ok({
        "access_token": session_id,
        "token_type": "session",
        "expires_in": max_age,
        "requires_2fa": False,
    }, "登录成功")


@router.post("/register")
def register(
    req: RegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session),
):
    """注册新用户，注册成功后自动登录"""
    if crud.get_user_by_email(db, req.email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该邮箱已注册")

    user = crud.create_user(
        db,
        email=req.email,
        password_hash=hash_password(req.password),
        name=req.name,
    )
    session_id = create_session(user.id, user.email, user.role, user.name)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_id,
        httponly=True,
        max_age=7 * 24 * 60 * 60,
        samesite="lax",
    )
    return _ok({
        "access_token": session_id,
        "token_type": "session",
        "expires_in": 7 * 24 * 60 * 60,
        "requires_2fa": False,
    }, "注册成功")


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    """返回当前用户信息（前端 fetchMe 期望 {data:{id,username,role}}）"""
    return _ok({
        "id": str(current_user.get("user_id", "")),
        "username": current_user.get("name") or current_user.get("email", ""),
        "email": current_user.get("email", ""),
        "role": current_user.get("role", "analyst"),
    })


@router.post("/logout")
def logout(request: Request, response: Response):
    """清除 session"""
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        delete_session(session_id)
    response.delete_cookie(SESSION_COOKIE)
    return _ok(None, "已退出登录")


# ============== 2FA 占位接口 ==============
# 前端 SecurityPage 调用 /auth/2fa/setup 等，后端暂未实现 2FA，
# 这里返回 404/501 让前端 SecurityPage 显示"未启用"
@router.post("/2fa/setup")
def two_fa_setup(current_user: dict = Depends(get_current_user)):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="2FA 暂未启用")


@router.post("/2fa/enable")
def two_fa_enable(current_user: dict = Depends(get_current_user)):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="2FA 暂未启用")


@router.post("/2fa/disable")
def two_fa_disable(current_user: dict = Depends(get_current_user)):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="2FA 暂未启用")


@router.post("/verify-2fa")
def verify_2fa():
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="2FA 暂未启用")


@router.post("/change-password")
def change_password(
    payload: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """修改当前用户密码 — 入参 {current_password, new_password}"""
    current_password = payload.get("current_password") or payload.get("currentPassword")
    new_password = payload.get("new_password") or payload.get("newPassword")
    if not current_password or not new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="参数缺失")
    user = crud.get_user_by_email(db, current_user.get("email", ""))
    if not user or not verify_password(current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="当前密码错误")
    user.password_hash = hash_password(new_password)
    db.commit()
    return _ok(None, "密码已修改")
