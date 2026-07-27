# -*- coding: utf-8 -*-
"""SSO FastAPI 路由 — 挂载在 /api/v1/auth/sso 下。"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from finpilot.api.deps import SESSION_COOKIE, create_session, get_db_session
from finpilot.auth.sso import (
    build_authorize_url,
    exchange_code_for_token,
    extract_email,
    extract_name,
    fetch_user_info,
    get_provider_config,
    verify_state,
)
from finpilot.database import crud

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sso", tags=["SSO"])

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")


@router.get("/{provider}/login")
async def sso_login(provider: str):
    try:
        auth_url, _ = build_authorize_url(provider)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/{provider}/callback")
async def sso_callback(
    provider: str,
    code: str,
    state: str,
    response: Response,
    db: Session = Depends(get_db_session),
):
    try:
        get_provider_config(provider)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    try:
        verify_state(state, provider)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    try:
        access_token = await exchange_code_for_token(provider, code)
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    try:
        user_info = await fetch_user_info(provider, access_token)
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    email = extract_email(provider, user_info)
    name = extract_name(provider, user_info)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="无法从 Provider 获取用户邮箱，请确保 scope 包含 email",
        )

    user = crud.get_user_by_email(db, email)
    if not user:
        user = crud.create_user(
            db,
            email=email,
            password_hash="",
            name=name or email.split("@")[0],
            role="analyst",
        )
        logger.info("sso_user_created", extra={"provider": provider, "email": email, "user_id": user.id})

    session_id = await create_session(user.id, user.email, user.role, user.name)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_id,
        httponly=True,
        max_age=7 * 24 * 60 * 60,
        samesite="lax",
    )

    return RedirectResponse(url=f"{FRONTEND_URL}/?sso_login=success", status_code=302)
