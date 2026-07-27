# -*- coding: utf-8 -*-
"""pytest 全局 fixtures — 为所有单元测试提供隔离的 TestClient + 内存 SQLite。

核心策略：
1. 在导入 finpilot 模块之前，先 monkeypatch 数据库连接，将 SQLite 文件路径
   替换为 :memory:，避免污染用户真实数据库。
2. session_store 和 limiter 本身已内置降级到内存/SQLite :memory:，
   测试环境无需额外处理。
3. 每个测试函数获得独立的 TestClient + 全新数据库表。
"""
from __future__ import annotations

import pytest


# ── 在导入任何 finpilot 模块之前打补丁 ──
def _patch_database():
    """将 finpilot.database.connection 重定向到内存 SQLite。"""
    import finpilot.database.connection as conn

    # 覆盖为内存数据库
    conn.DATABASE_URL = "sqlite:///:memory:"

    # 重新创建引擎（内存 SQLite 需要 check_same_thread=False）
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    conn.engine = create_engine(
        conn.DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    # 重建 SessionLocal
    from sqlalchemy.orm import sessionmaker
    conn.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=conn.engine)


def _patch_auth_redis():
    """将 auth 模块中的 Redis 连接函数补丁为始终返回 None。

    避免 Redis 异步连接在 pytest 事件循环切换中引发 RuntimeError。
    slowapi 限流器已降级到 memory://，此补丁仅影响登录账号级锁定功能。
    """
    import finpilot.api.auth as auth_mod

    async def _redis_none():
        return None

    auth_mod._get_redis_or_none = _redis_none


_patch_database()
_patch_auth_redis()


@pytest.fixture(scope="function")
def client():
    """FastAPI TestClient — 每个测试函数独立的客户端实例。

    每次创建时重建所有数据库表，保证测试隔离。
    """
    from fastapi.testclient import TestClient

    from finpilot.api.router import app
    from finpilot.database import init_db

    # 重建数据库表（内存 SQLite，每次 fixture 全新）
    init_db()

    with TestClient(app) as tc:
        yield tc


@pytest.fixture(scope="function")
def db_session():
    """原始 SQLAlchemy 会话 — 用于直接操作数据库。"""
    from finpilot.database import SessionLocal
    from finpilot.database import init_db

    init_db()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
