# -*- coding: utf-8 -*-
"""FinPilot 配置中心 — 从 .env.local 加载，支持 pydantic 校验。"""
from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str = ""
    admin_password: str = ""
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "sqlite+aiosqlite:///./finpilot.db"
    secret_key: str = ""
    environment: str = "development"

    model_config = {
        "env_file": ".env.local",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
