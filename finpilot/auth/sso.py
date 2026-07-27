# -*- coding: utf-8 -*-
"""企业 SSO — OAuth 2.0 Authorization Code Flow 纯逻辑层。

不含 FastAPI 依赖，可被 API 层安全导入（避免循环引用）。
"""
from __future__ import annotations

import logging
import os
import secrets
import urllib.parse
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

REDIRECT_BASE = os.getenv("SSO_REDIRECT_BASE", "http://localhost:8000").rstrip("/")

PROVIDERS: dict[str, dict] = {
    "google": {
        "name": "Google",
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid email profile",
        "client_id_env": "SSO_GOOGLE_CLIENT_ID",
        "client_secret_env": "SSO_GOOGLE_CLIENT_SECRET",
    },
    "github": {
        "name": "GitHub",
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
        "scope": "user:email",
        "client_id_env": "SSO_GITHUB_CLIENT_ID",
        "client_secret_env": "SSO_GITHUB_CLIENT_SECRET",
    },
    "microsoft": {
        "name": "Microsoft",
        "authorize_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "userinfo_url": "https://graph.microsoft.com/v1.0/me",
        "scope": "openid email profile User.Read",
        "client_id_env": "SSO_MICROSOFT_CLIENT_ID",
        "client_secret_env": "SSO_MICROSOFT_CLIENT_SECRET",
    },
}

_state_store: dict[str, dict] = {}


def get_provider_config(provider: str) -> dict:
    cfg = PROVIDERS.get(provider)
    if not cfg:
        raise ValueError(f"不支持的 SSO Provider: {provider}。可选: google, github, microsoft")
    client_id = os.getenv(cfg["client_id_env"])
    client_secret = os.getenv(cfg["client_secret_env"])
    if not client_id or not client_secret:
        raise ValueError(f"{cfg['name']} SSO 未配置（缺少 {cfg['client_id_env']} / {cfg['client_secret_env']}）")
    return cfg


def build_authorize_url(provider: str) -> tuple[str, str]:
    """生成 OAuth 授权 URL，返回 (url, state)。"""
    cfg = get_provider_config(provider)
    state = secrets.token_urlsafe(32)
    redirect_uri = f"{REDIRECT_BASE}/api/v1/auth/sso/{provider}/callback"
    _state_store[state] = {"provider": provider, "created_at": datetime.now(timezone.utc)}
    params = {
        "client_id": os.getenv(cfg["client_id_env"]),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": cfg["scope"],
        "state": state,
    }
    if provider == "microsoft":
        params["response_mode"] = "query"
    auth_url = f"{cfg['authorize_url']}?{urllib.parse.urlencode(params)}"
    return auth_url, state


def verify_state(state: str, provider: str) -> None:
    stored = _state_store.pop(state, None)
    if not stored:
        raise ValueError("无效的 state 参数，可能已过期或被重放攻击")
    if stored.get("provider") != provider:
        raise ValueError("state 中的 provider 不匹配")


async def exchange_code_for_token(provider: str, code: str) -> str:
    cfg = get_provider_config(provider)
    redirect_uri = f"{REDIRECT_BASE}/api/v1/auth/sso/{provider}/callback"
    token_data = {
        "client_id": os.getenv(cfg["client_id_env"]),
        "client_secret": os.getenv(cfg["client_secret_env"]),
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        token_resp = await client.post(cfg["token_url"], data=token_data, headers={"Accept": "application/json"})
        if token_resp.status_code != 200:
            logger.error("sso_token_failed", provider=provider, status=token_resp.status_code)
            raise RuntimeError(f"Token 交换失败: {cfg['name']} 返回 {token_resp.status_code}")
        token_json = token_resp.json()
        access_token = token_json.get("access_token")
        if not access_token:
            raise RuntimeError("未从 Provider 获取到 access_token")
        return access_token


async def fetch_user_info(provider: str, access_token: str) -> dict:
    cfg = get_provider_config(provider)
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        user_resp = await client.get(
            cfg["userinfo_url"],
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if user_resp.status_code != 200:
            logger.error("ssoso_userinfo_failed", provider=provider, status=user_resp.status_code)
            raise RuntimeError(f"获取用户信息失败: {cfg['name']} 返回 {user_resp.status_code}")
        return user_resp.json()


def extract_email(provider: str, user_info: dict) -> str | None:
    if provider == "github":
        email = user_info.get("email")
        if email:
            return email
        login = user_info.get("login", "")
        return f"{login}@github.user" if login else None
    if provider in ("google", "microsoft"):
        return user_info.get("email") or user_info.get("mail") or user_info.get("userPrincipalName")
    return user_info.get("email")


def extract_name(provider: str, user_info: dict) -> str | None:
    if provider == "github":
        return user_info.get("name") or user_info.get("login")
    if provider in ("google", "microsoft"):
        return user_info.get("name") or user_info.get("displayName")
    return user_info.get("name")
