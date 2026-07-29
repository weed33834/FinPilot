# -*- coding: utf-8 -*-
"""认证路由 - session cookie 认证 + 2FA + 登录限速（与前端 authStore 契约对齐）.

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

import io
from datetime import datetime, timedelta, timezone

import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from finpilot.core.crypto import decrypt as crypto_decrypt, encrypt as crypto_encrypt
from finpilot.core.logging import get_logger
from finpilot.core.session import session_store
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
from .rate_limit import limiter
from .schemas import LoginRequest, RegisterRequest

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# 账号维度锁定：5 次失败 → 锁定 15 分钟
LOGIN_MAX_FAILURES = 5
LOGIN_LOCKOUT_MINUTES = 15


def _ok(data, message: str = "ok", code: int = 0):
    """统一 {code, message, data} 包装"""
    return {"code": code, "message": message, "data": data}


def _resolve_user_identifier(login_req: LoginRequest):
    """username 字段可能是邮箱或用户名，统一解析为 email 用于查表"""
    return login_req.email or login_req.username


async def _get_redis_or_none():
    """获取 Redis 连接，不可用时返回 None（优雅降级，不崩溃）。"""
    try:
        from finpilot.core.session import _check_redis
        if not _check_redis():
            return None
        r = await session_store._get_redis()
        return r
    except Exception:
        return None


async def _check_account_locked(email: str) -> str | None:
    """检查账号是否被锁定。返回 None 表示未锁定，否则返回错误信息。"""
    r = await _get_redis_or_none()
    if r is None:
        return None  # Redis 不可用时跳过限速
    key = f"login_lockout:{email}"
    locked_until = await r.get(key)
    if locked_until:
        try:
            until = datetime.fromisoformat(locked_until)
            if until > datetime.now(timezone.utc):
                remaining = int((until - datetime.now(timezone.utc)).total_seconds() / 60) + 1
                return f"账号已锁定，请 {remaining} 分钟后重试"
        except (ValueError, TypeError):
            pass
    return None


async def _record_login_failure(email: str) -> None:
    """记录登录失败，达到阈值则锁定。"""
    r = await _get_redis_or_none()
    if r is None:
        return  # Redis 不可用时跳过限速
    key = f"login_failures:{email}"
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, LOGIN_LOCKOUT_MINUTES * 60)
    if count >= LOGIN_MAX_FAILURES:
        lock_until = (datetime.now(timezone.utc) + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)).isoformat()
        await r.setex(f"login_lockout:{email}", LOGIN_LOCKOUT_MINUTES * 60, lock_until)
        logger.warning("account_locked", email=email, failures=count)


async def _clear_login_failures(email: str) -> None:
    """登录成功后清除失败计数和锁定。"""
    r = await _get_redis_or_none()
    if r is None:
        return
    await r.delete(f"login_failures:{email}", f"login_lockout:{email}")


# ============== 登录 / 注册 / 登出 / 当前用户 ==============


@router.post("/login")
@limiter.limit("5/minute")
async def login(
    req: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session),
):
    """验证用户名/邮箱密码，设置 session cookie，返回 access_token（即 session_id）。

    限速：同一 IP 每分钟最多 5 次登录尝试。
    账号锁定：同一账号连续 5 次失败锁定 15 分钟。
    """
    email = _resolve_user_identifier(req)

    # 检查账号锁定
    lock_msg = await _check_account_locked(email)
    if lock_msg:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=lock_msg)

    user = crud.get_user_by_email(db, email)
    if not user or not user.password_hash:
        await _record_login_failure(email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")
    if not verify_password(req.password, user.password_hash)[0]:
        await _record_login_failure(email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")

    # 登录成功，清除失败记录
    await _clear_login_failures(email)

    session_id = await create_session(user.id, user.email, user.role, user.name)
    max_age = 30 * 24 * 60 * 60 if req.remember_me else 7 * 24 * 60 * 60
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_id,
        httponly=True,
        max_age=max_age,
        samesite="lax",
    )
    return _ok({
        "access_token": session_id,
        "token_type": "session",
        "expires_in": max_age,
        "requires_2fa": bool(user.totp_enabled),
    }, "登录成功")


@router.post("/register")
@limiter.limit("3/minute")
async def register(
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
    session_id = await create_session(user.id, user.email, user.role, user.name)
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
async def me(current_user: dict = Depends(get_current_user)):
    """返回当前用户信息（前端 fetchMe 期望 {data:{id,username,role}}）"""
    return _ok({
        "id": str(current_user.get("user_id", "")),
        "username": current_user.get("name") or current_user.get("email", ""),
        "email": current_user.get("email", ""),
        "role": current_user.get("role", "analyst"),
    })


@router.post("/logout")
async def logout(request: Request, response: Response):
    """清除 session"""
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        await delete_session(session_id)
    response.delete_cookie(SESSION_COOKIE)
    return _ok(None, "已退出登录")


# ============== 2FA TOTP 实现 ==============

TOTP_ISSUER = "FinPilot"
TOTP_SETUP_TTL = 300  # 5 分钟


def _get_user_orm(current_user: dict, db: Session):
    """从 session 中的 user_id 获取 User ORM 对象。"""
    from finpilot.database.models import User

    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无法识别用户")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return user


@router.post("/2fa/setup")
async def two_fa_setup(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """生成 TOTP secret，返回二维码 PNG。

    secret 暂存 Redis（5 分钟过期），验证通过后才写入数据库。
    Redis 不可用时返回 503。
    """
    user = _get_user_orm(current_user, db)
    if user.totp_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA 已启用，请先禁用再重新设置")

    secret = pyotp.random_base32()
    r = await _get_redis_or_none()
    if r is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="2FA 设置需要 Redis 服务，当前不可用",
        )
    await r.setex(f"2fa_setup:{user.id}", TOTP_SETUP_TTL, secret)

    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=user.email, issuer_name=TOTP_ISSUER)

    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return StreamingResponse(buf, media_type="image/png")


@router.post("/2fa/verify")
async def two_fa_verify(
    code: str = Query(..., description="TOTP 验证码"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """验证 TOTP 码，通过后持久化 secret 并启用 2FA。"""
    user = _get_user_orm(current_user, db)

    r = await _get_redis_or_none()
    if r is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="2FA 验证需要 Redis 服务，当前不可用",
        )
    secret = await r.get(f"2fa_setup:{user.id}")
    if not secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA 设置已过期，请重新发起 setup")

    totp = pyotp.TOTP(secret)
    if not totp.verify(code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码错误")

    user.totp_secret = crypto_encrypt(secret)
    user.totp_enabled = True
    db.commit()

    await r.delete(f"2fa_setup:{user.id}")

    return _ok({"totp_enabled": True}, "2FA 已启用")


@router.post("/2fa/disable")
async def two_fa_disable(
    payload: dict | None = None,
    code: str | None = Query(None, description="当前 TOTP 验证码（query 参数，向后兼容）"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """关闭 2FA.

    前端契约（SecurityPage.tsx）以 JSON body 传 ``{ password }``；
    旧契约以 query 参数传 ``?code=``（TOTP 验证码）。

    为兼容两种调用方式：
    - 若 body 含 ``password``：用密码验证身份后关闭 2FA；
    - 若 body 含 ``code`` 或 query 传 ``code``：用 TOTP 验证码验证后关闭 2FA。
    """
    user = _get_user_orm(current_user, db)
    if not user.totp_enabled or not user.totp_secret:
        raise HTTPException(status_code=400, detail="2FA 未启用")

    body = payload or {}
    password = (body.get("password") or "").strip()
    totp_code = (body.get("code") or code or "").strip()

    # 二选一验证：密码 或 TOTP 码
    if password:
        # verify_password 返回 (ok, new_hash) 元组，不可直接当布尔用
        ok, _ = verify_password(password, user.password_hash or "")
        if not ok:
            raise HTTPException(status_code=400, detail="密码错误")
    elif totp_code:
        totp = pyotp.TOTP(crypto_decrypt(user.totp_secret))
        if not totp.verify(totp_code):
            raise HTTPException(status_code=400, detail="验证码错误")
    else:
        raise HTTPException(
            status_code=422,
            detail="需提供 password（body）或 code（query/body）进行身份验证",
        )

    user.totp_secret = None
    user.totp_enabled = False
    db.commit()

    return _ok({"totp_enabled": False}, "2FA 已禁用")


@router.get("/2fa/status")
async def two_fa_status(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """返回当前用户 2FA 状态。"""
    user = _get_user_orm(current_user, db)
    return _ok({
        "totp_enabled": user.totp_enabled,
    })


# 兼容旧端点


@router.post("/2fa/enable")
async def two_fa_enable(
    code: str = Query(..., description="TOTP 验证码"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """兼容端点：同 /auth/2fa/verify。"""
    return await two_fa_verify(code=code, current_user=current_user, db=db)


@router.post("/verify-2fa")
async def verify_2fa(
    code: str = Query(..., description="TOTP 验证码"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """兼容端点：验证 2FA 码（用于登录后二次验证）。"""
    user = _get_user_orm(current_user, db)
    if not user.totp_enabled or not user.totp_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA 未启用")

    totp = pyotp.TOTP(crypto_decrypt(user.totp_secret))
    if not totp.verify(code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码错误")

    return _ok({"verified": True}, "2FA 验证通过")


# ============== 修改密码 ==============


@router.post("/change-password")
async def change_password(
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
    if not user or not verify_password(current_password, user.password_hash or "")[0]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="当前密码错误")
    user.password_hash = hash_password(new_password)
    db.commit()
    return _ok(None, "密码已修改")
