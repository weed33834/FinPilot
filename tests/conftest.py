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
    """将 finpilot.database.connection 重定向到内存 SQLite。

    关键：必须同步更新 ``finpilot.database`` 包级 re-export 的 engine/SessionLocal，
    否则 ``from finpilot.database import SessionLocal``（deps.get_db_session 用此）
    仍指向旧的文件 DB，导致测试查询到 ~/.finpilot/finpilot.db 的真实数据。
    """
    import finpilot.database as db_pkg
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

    # 同步包级 re-export，确保 ``from finpilot.database import SessionLocal`` 拿到内存版
    db_pkg.engine = conn.engine
    db_pkg.SessionLocal = conn.SessionLocal


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

    每次创建时先 drop 再 create 所有表，保证测试间数据彻底隔离
    （内存 SQLite 引擎为模块级单例，create_all 不会清理旧数据）。
    同时重置 session_store 的降级存储，避免会话跨测试残留。
    """
    from fastapi.testclient import TestClient

    from finpilot.api.router import app
    from finpilot.database import init_db
    from finpilot.database.connection import engine
    from finpilot.database.models import Base

    # 先清空再重建，确保每个测试拿到干净库
    Base.metadata.drop_all(bind=engine)
    init_db()

    # 重置 session_store 降级存储（清空跨测试残留会话）
    try:
        from finpilot.core.session import session_store

        if session_store._fallback is not None:
            session_store._fallback = None
    except Exception:  # noqa: BLE001
        pass

    # 重置限流计数器：limiter 为模块级单例，memory:// 存储跨测试累积，
    # 会导致第 4 个测试起 register（3/minute）被限速 429 → 用户未创建 → login 401
    try:
        from finpilot.api.rate_limit import limiter
        limiter.reset()
    except Exception:  # noqa: BLE001
        pass

    with TestClient(app) as tc:
        yield tc


@pytest.fixture(scope="function")
def db_session():
    """原始 SQLAlchemy 会话 — 用于直接操作数据库（与 client 共享同一内存引擎）。

    注意：不在此处 drop_all，否则会清掉同测试中 client fixture 已写入的数据。
    仅 init_db（create_all 幂等）保证表存在。
    """
    from finpilot.database import SessionLocal
    from finpilot.database import init_db

    init_db()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
