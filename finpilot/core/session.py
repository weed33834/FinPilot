# -*- coding: utf-8 -*-
"""会话存储 — Redis 主存储 + SQLite 降级方案。

主存储：Redis（需 Redis 服务或 Memurai 兼容实现）
降级方案：当 Redis 不可用时，自动降级到 SQLite 内存方案，
         保证后端不会崩溃，进程重启后会话丢失。
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid

from .config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Redis 可用性检测（仅一次，避免每次请求都尝试连接）
# ---------------------------------------------------------------------------
_redis_available: bool | None = None


def _check_redis() -> bool:
    """检测 Redis 是否可用（单次检测，结果缓存）。"""
    global _redis_available
    if _redis_available is not None:
        return _redis_available

    try:
        import redis.asyncio  # noqa: F401  仅检测 redis 包是否可导入

        _redis_available = True
        return True
    except ImportError:
        logger.warning("redis 包未安装，会话存储降级为 SQLite 内存模式")
        _redis_available = False
        return False


# ---------------------------------------------------------------------------
# SQLite 降级存储
# ---------------------------------------------------------------------------
class _SQLiteSessionStore:
    """基于 SQLite 的内存会话存储（Redis 不可用时的降级方案）。

    注意：此实现使用内存数据库（:memory:），进程重启后所有会话丢失。
    生产环境建议配置 Redis 或使用持久化 SQLite 文件。
    """

    def __init__(self, ttl: int = 86400):
        self.ttl = ttl
        self._db = sqlite3.connect(":memory:", check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS sessions ("
            "  session_id TEXT PRIMARY KEY,"
            "  user_data TEXT,"
            "  created_at REAL"
            ")"
        )
        self._db.commit()

    async def _cleanup_expired(self):
        """清理过期会话。"""
        cutoff = time.time() - self.ttl
        self._db.execute("DELETE FROM sessions WHERE created_at < ?", (cutoff,))
        self._db.commit()

    async def create(self, user_data: dict) -> str:
        session_id = str(uuid.uuid4())
        self._db.execute(
            "INSERT INTO sessions (session_id, user_data, created_at) VALUES (?, ?, ?)",
            (session_id, json.dumps(user_data, default=str), time.time()),
        )
        self._db.commit()
        logger.debug("SQLite session created: %s", session_id)
        return session_id

    async def get(self, session_id: str) -> dict | None:
        await self._cleanup_expired()
        row = self._db.execute(
            "SELECT user_data FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    async def delete(self, session_id: str) -> None:
        self._db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        self._db.commit()
        logger.debug("SQLite session deleted: %s", session_id)

    async def refresh(self, session_id: str) -> None:
        self._db.execute(
            "UPDATE sessions SET created_at = ? WHERE session_id = ?",
            (time.time(), session_id),
        )
        self._db.commit()

    async def close(self) -> None:
        self._db.close()


# ---------------------------------------------------------------------------
# Redis 主存储
# ---------------------------------------------------------------------------
class RedisSessionStore:
    """基于 Redis 的会话存储，TTL 默认 86400 秒（24 小时）。

    提供 create / get / delete / refresh / close 五个核心方法，
    使用 ``session:{session_id}`` 作为 Redis key 前缀。

    当 Redis 不可用时，自动降级到 _SQLiteSessionStore。
    """

    def __init__(self, redis_url: str = "", ttl: int = 86400):
        self.ttl = ttl
        self.redis_url = redis_url or settings.redis_url
        self._redis = None
        self._fallback: _SQLiteSessionStore | None = None

    async def _get_redis(self):
        """获取 Redis 连接，不可用时返回 None 触发降级。"""
        if not _check_redis():
            return None
        if self._redis is None:
            try:
                import redis.asyncio as aioredis  # noqa: F401
                self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
                # 快速 ping 检测连接
                await self._redis.ping()
                logger.info("Redis 会话存储已连接: %s", self.redis_url)
            except Exception:
                logger.warning(
                    "Redis 连接失败 (%s)，会话存储降级为 SQLite 内存模式",
                    self.redis_url,
                )
                self._redis = None
                return None
        return self._redis

    async def _get_store(self):
        """返回可用的存储后端（Redis 优先，不可用时 SQLite）。"""
        r = await self._get_redis()
        if r is not None:
            return r
        if self._fallback is None:
            self._fallback = _SQLiteSessionStore(self.ttl)
            logger.warning("已激活 SQLite 内存会话存储（降级模式）")
        return self._fallback

    async def create(self, user_data: dict) -> str:
        session_id = str(uuid.uuid4())
        r = await self._get_redis()
        if r is not None:
            await r.setex(
                f"session:{session_id}",
                self.ttl,
                json.dumps(user_data, default=str),
            )
            logger.debug("Session created: %s", session_id)
        else:
            store = await self._get_store()
            session_id = await store.create(user_data)
        return session_id

    async def get(self, session_id: str) -> dict | None:
        r = await self._get_redis()
        if r is not None:
            data = await r.get(f"session:{session_id}")
            return json.loads(data) if data else None
        store = await self._get_store()
        return await store.get(session_id)

    async def delete(self, session_id: str) -> None:
        r = await self._get_redis()
        if r is not None:
            await r.delete(f"session:{session_id}")
            logger.debug("Session deleted: %s", session_id)
        else:
            store = await self._get_store()
            await store.delete(session_id)

    async def refresh(self, session_id: str) -> None:
        r = await self._get_redis()
        if r is not None:
            await r.expire(f"session:{session_id}", self.ttl)
        else:
            store = await self._get_store()
            await store.refresh(session_id)

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None
        if self._fallback:
            await self._fallback.close()
            self._fallback = None


# 全局单例
session_store = RedisSessionStore()
