# -*- coding: utf-8 -*-
"""认证路由 - session cookie 认证 + 2FA 挑战流 + 登录限速（与前端契约对齐）.

前端契约（stores/authStore.ts / pages/SecurityPage.tsx / types/twoFactor.ts）：
- POST /auth/login           入参 {username, password, remember_me}
                             返回 {code, message, data: {access_token, token_type, expires_in, requires_2fa}}
                             若启用 2FA 且 Redis 可用：返回 {requires_2fa:true, challenge_token, challenge_expires_in}
                             （此时不签发 session，前端走二次验证）
- POST /auth/verify-2fa      入参 {challenge_token, totp_code?, backup_code?}
                             校验通过后签发 session 并 set-cookie，返回 {access_token, ...}
- GET  /auth/me              返回 {code, message, data: {id, username, role}}
- POST /auth/logout          返回 {code, message, data: null}
- POST /auth/register        入参 {email, password, name}（旧契约，保留兼容）
- POST /auth/change-password 入参 {current_password, new_password}

2FA 管理（SecurityPage）：
- GET  /auth/2fa/status       → {enabled, setup_in_progress}
- POST /auth/2fa/setup        → {secret, otpauth_uri, qr_svg}（qr_svg 为 SVG 字符串）
- POST /auth/2fa/enable       入参 {totp_code, password} → {backup_codes: string[]}
- POST /auth/2fa/disable      入参 {password} → ok
- POST /auth/2fa/backup-codes 入参 {password} → {backup_codes: string[]}（重新生成）

cookie 名 session_id，HttpOnly；access_token 字段值即为 session_id，
前端不直接使用 access_token（withCredentials 自动带 cookie）。

注：2FA 完整流程依赖 Redis（挑战令牌 / 备份码均存 Redis）。Redis 不可用时：
- 登录：降级跳过二次验证（记录警告），避免把启用 2FA 的用户彻底锁死；
- setup / enable / verify-2fa / backup-codes：返回 503。
"""
from __future__ import annotations

import hashlib
import io
import json
import secrets
from datetime import datetime, timedelta, timezone

import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from qrcode.image.svg import SvgImage
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

# 2FA 挑战令牌 / setup 密钥 TTL（秒）
CHALLENGE_TTL = 300
TOTP_SETUP_TTL = 300
TOTP_ISSUER = "FinPilot"
BACKUP_CODE_COUNT = 8


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


# ============== 备份码工具（Redis 存储 SHA256 哈希） ==============


def _generate_backup_codes() -> list[str]:
    """生成 8 个 XXXX-XXXX 格式的备份码。"""
    return [f"{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}" for _ in range(BACKUP_CODE_COUNT)]


def _hash_backup_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode()).hexdigest()


async def _save_backup_codes(r, user_id: int, codes: list[str]) -> None:
    """以 SHA256 哈希列表形式持久化备份码（明文仅返回给用户一次）。"""
    payload = json.dumps([_hash_backup_code(c) for c in codes])
    await r.set(f"2fa_backup:{user_id}", payload)


async def _consume_backup_code(r, user_id: int, code: str) -> bool:
    """核销一个备份码（命中即从列表移除，单次有效）。"""
    if not code:
        return False
    raw = await r.get(f"2fa_backup:{user_id}")
    if not raw:
        return False
    try:
        hashes = json.loads(raw)
    except (ValueError, TypeError):
        return False
    target = _hash_backup_code(code)
    if target not in hashes:
        return False
    hashes.remove(target)
    if hashes:
        await r.set(f"2fa_backup:{user_id}", json.dumps(hashes))
    else:
        await r.delete(f"2fa_backup:{user_id}")
    return True


def _set_session_cookie(response: Response, session_id: str, remember_me: bool) -> int:
    """统一设置 session cookie，返回 max_age。"""
    max_age = 30 * 24 * 60 * 60 if remember_me else 7 * 24 * 60 * 60
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_id,
        httponly=True,
        max_age=max_age,
        samesite="lax",
    )
    return max_age


# ============== 登录 / 注册 / 登出 / 当前用户 ==============


@router.post("/login")
@limiter.limit("5/minute")
async def login(
    req: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session),
):
    """验证用户名/邮箱密码。

    - 未启用 2FA：直接签发 session；
    - 启用 2FA 且 Redis 可用：返回 challenge_token，不签发 session，前端走 /auth/verify-2fa；
    - 启用 2FA 但 Redis 不可用：降级直接签发 session（避免锁死用户），记录警告。

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
    ok, new_hash = verify_password(req.password, user.password_hash)
    if not ok:
        await _record_login_failure(email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")
    # 哈希参数升级：密码正确但哈希参数是旧版本的，透明升级后持久化
    if new_hash:
        user.password_hash = new_hash
        db.commit()

    # 登录成功，清除失败记录
    await _clear_login_failures(email)

    # 2FA 挑战流：不签发 session，返回 challenge_token
    if user.totp_enabled:
        r = await _get_redis_or_none()
        if r is None:
            logger.warning("2FA 用户登录但 Redis 不可用，降级跳过二次验证", email=email)
            session_id = await create_session(user.id, user.email, user.role, user.name)
            max_age = _set_session_cookie(response, session_id, req.remember_me)
            return _ok({
                "access_token": session_id,
                "token_type": "session",
                "expires_in": max_age,
                "requires_2fa": True,
            }, "登录成功（2FA 已降级）")

        challenge_token = secrets.token_urlsafe(32)
        challenge_data = json.dumps({
            "user_id": user.id,
            "email": user.email,
            "role": user.role,
            "name": user.name,
            "remember_me": bool(req.remember_me),
        })
        await r.setex(f"2fa_challenge:{challenge_token}", CHALLENGE_TTL, challenge_data)
        return _ok({
            "requires_2fa": True,
            "challenge_token": challenge_token,
            "challenge_expires_in": CHALLENGE_TTL,
        }, "需要二次验证")

    # 正常登录：签发 session
    session_id = await create_session(user.id, user.email, user.role, user.name)
    max_age = _set_session_cookie(response, session_id, req.remember_me)
    return _ok({
        "access_token": session_id,
        "token_type": "session",
        "expires_in": max_age,
        "requires_2fa": False,
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
    _set_session_cookie(response, session_id, remember_me=False)
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


class Verify2FARequest(BaseModel):
    """登录二次验证请求体（前端 authStore.verify2fa 契约）。"""
    challenge_token: str
    totp_code: str | None = None
    backup_code: str | None = None


class Enable2FARequest(BaseModel):
    """启用 2FA 请求体（前端 SecurityPage 契约）。"""
    totp_code: str
    password: str


class PasswordRequest(BaseModel):
    """需要密码确认的请求体（关闭 2FA / 重新生成备份码）。"""
    password: str


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


@router.post("/verify-2fa")
async def verify_2fa(
    req: Verify2FARequest,
    response: Response,
    db: Session = Depends(get_db_session),
):
    """登录二次验证：校验 challenge_token + TOTP/备份码，通过后签发 session。

    无需 get_current_user（用户尚未登录），凭 challenge_token 识别身份。
    """
    r = await _get_redis_or_none()
    if r is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="二次验证需要 Redis 服务，当前不可用",
        )

    raw = await r.get(f"2fa_challenge:{req.challenge_token}")
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证会话已过期，请重新登录")
    try:
        info = json.loads(raw)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证会话异常，请重新登录")

    from finpilot.database.models import User

    user = db.query(User).filter(User.id == info.get("user_id")).first()
    if not user or not user.totp_enabled or not user.totp_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA 未启用或状态异常")

    verified = False
    if req.totp_code:
        totp = pyotp.TOTP(crypto_decrypt(user.totp_secret))
        try:
            verified = totp.verify(req.totp_code)
        except Exception:  # noqa: BLE001
            verified = False
    if not verified and req.backup_code:
        verified = await _consume_backup_code(r, user.id, req.backup_code)

    if not verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码错误或已失效",
        )

    # 挑战令牌一次性，立即作废
    await r.delete(f"2fa_challenge:{req.challenge_token}")

    session_id = await create_session(user.id, user.email, user.role, user.name)
    max_age = _set_session_cookie(response, session_id, bool(info.get("remember_me")))
    return _ok({
        "access_token": session_id,
        "token_type": "session",
        "expires_in": max_age,
        "requires_2fa": False,
    }, "登录成功")


@router.get("/2fa/status")
async def two_fa_status(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """返回当前用户 2FA 状态（前端 TwoFAStatus 契约：enabled / setup_in_progress）。"""
    user = _get_user_orm(current_user, db)
    setup_in_progress = False
    r = await _get_redis_or_none()
    if r is not None:
        setup_in_progress = bool(await r.exists(f"2fa_setup:{user.id}"))
    return _ok({
        "enabled": bool(user.totp_enabled),
        "setup_in_progress": setup_in_progress,
    })


@router.post("/2fa/setup")
async def two_fa_setup(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """生成 TOTP secret，返回 SVG 二维码 + otpauth_uri + secret（前端 TwoFASetup 契约）。

    secret 暂存 Redis（5 分钟过期），enable 验证通过后才写入数据库。
    """
    user = _get_user_orm(current_user, db)
    if user.totp_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA 已启用，请先禁用再重新设置")

    r = await _get_redis_or_none()
    if r is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="2FA 设置需要 Redis 服务，当前不可用",
        )

    secret = pyotp.random_base32()
    await r.setex(f"2fa_setup:{user.id}", TOTP_SETUP_TTL, secret)

    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=user.email, issuer_name=TOTP_ISSUER)

    img = qrcode.make(uri, image_factory=SvgImage)
    buf = io.BytesIO()
    img.save(buf)
    qr_svg = buf.getvalue().decode("utf-8")

    return _ok({
        "secret": secret,
        "otpauth_uri": uri,
        "qr_svg": qr_svg,
    })


@router.post("/2fa/enable")
async def two_fa_enable(
    req: Enable2FARequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """启用 2FA：密码 + TOTP 双因子校验，通过后持久化 secret 并生成备份码。

    返回前端 BackupCodesResponse 契约（备份码明文仅此一次返回）。
    """
    user = _get_user_orm(current_user, db)
    if user.totp_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA 已启用")

    r = await _get_redis_or_none()
    if r is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="2FA 启用需要 Redis 服务，当前不可用",
        )

    # 密码二次确认
    ok, new_hash = verify_password(req.password, user.password_hash or "")
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码错误")
    if new_hash:
        user.password_hash = new_hash
        db.commit()

    secret = await r.get(f"2fa_setup:{user.id}")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA 设置已过期，请重新发起 setup",
        )

    totp = pyotp.TOTP(secret)
    if not totp.verify(req.totp_code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码错误")

    user.totp_secret = crypto_encrypt(secret)
    user.totp_enabled = True
    db.commit()

    await r.delete(f"2fa_setup:{user.id}")

    # 生成一次性备份码
    codes = _generate_backup_codes()
    await _save_backup_codes(r, user.id, codes)
    return _ok({"backup_codes": codes}, "2FA 已启用")


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
        ok, new_hash = verify_password(password, user.password_hash or "")
        if not ok:
            raise HTTPException(status_code=400, detail="密码错误")
        if new_hash:
            user.password_hash = new_hash
            db.commit()
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

    # 清理残留备份码
    r = await _get_redis_or_none()
    if r is not None:
        await r.delete(f"2fa_backup:{user.id}")

    return _ok({"totp_enabled": False}, "2FA 已禁用")


@router.post("/2fa/backup-codes")
async def two_fa_backup_codes(
    req: PasswordRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """重新生成备份码（需密码确认）。旧备份码立即失效。"""
    user = _get_user_orm(current_user, db)
    if not user.totp_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA 未启用")

    ok, new_hash = verify_password(req.password, user.password_hash or "")
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码错误")
    if new_hash:
        user.password_hash = new_hash
        db.commit()

    r = await _get_redis_or_none()
    if r is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="备份码服务需要 Redis，当前不可用",
        )

    codes = _generate_backup_codes()
    await _save_backup_codes(r, user.id, codes)
    return _ok({"backup_codes": codes}, "备份码已重新生成")


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
    # 密码强度校验：最少 8 位，至少包含字母和数字
    if len(new_password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码长度不能少于8位")
    import re
    if not re.search(r'[A-Za-z]', new_password) or not re.search(r'[0-9]', new_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码必须包含字母和数字")
    user = crud.get_user_by_email(db, current_user.get("email", ""))
    ok, _ = verify_password(current_password, user.password_hash or "")
    if not user or not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="当前密码错误")
    # 直接写入新密码哈希（新 argon2 参数自动生效，无需单独升级旧哈希）
    user.password_hash = hash_password(new_password)
    db.commit()
    return _ok(None, "密码已修改")
