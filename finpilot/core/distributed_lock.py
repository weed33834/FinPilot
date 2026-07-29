# -*- coding: utf-8 -*-
"""分布式锁 — Redis 主后端 + threading 降级方案。

用途：防止并发场景下的重复操作（同一文档重复索引、报告重复生成、
订阅重复执行等）。多副本部署时跨进程/跨实例安全。

降级策略：Redis 不可用时降级到进程内 ``threading.Lock``，仅保证单进程
安全（与 session_store / rate_limit 的降级思路一致），并在日志中告警。

用法::

    from finpilot.core.distributed_lock import distributed_lock

    with distributed_lock(f"doc:{doc_id}", timeout=60):
        # 临界区：索引文档 / 生成报告 / 重建索引
        ...

参数：
- ``key``：锁名（建议带业务前缀，如 ``doc:12`` / ``report:abc``）
- ``timeout``：持锁最长时间（秒），超时自动释放，防死锁
- ``blocking_timeout``：获取锁最大等待时间（秒），超时抛 ``LockAcquireError``
"""
from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Iterator

from .config import settings

logger = logging.getLogger(__name__)


class LockAcquireError(RuntimeError):
    """在 blocking_timeout 内未能获取锁时抛出。"""


# ── Redis 可用性探测（与 rate_limit._probe_redis 一致，结果缓存）─────────
_redis_lock_client = None
_redis_lock_probed = False


def _get_redis_lock_client():
    """探测 Redis 连通性，返回同步 client 或 None（结果缓存）。"""
    global _redis_lock_client, _redis_lock_probed
    if _redis_lock_probed:
        return _redis_lock_client
    _redis_lock_probed = True
    try:
        import redis

        client = redis.from_url(
            settings.redis_url, socket_connect_timeout=1, socket_timeout=1
        )
        client.ping()
        _redis_lock_client = client
        logger.info("distributed_lock: Redis 可用，启用跨进程分布式锁")
    except Exception:  # noqa: BLE001
        _redis_lock_client = None
        logger.warning(
            "distributed_lock: Redis 不可用，降级为进程内 threading.Lock（仅单进程安全）"
        )
    return _redis_lock_client


# ── 进程内降级锁池（Redis 不可用时使用）──────────────────────────────────
_local_locks: dict[str, threading.Lock] = {}
_local_locks_guard = threading.Lock()


def _get_local_lock(key: str) -> threading.Lock:
    """按 key 获取/创建进程内锁（单例，复用）。"""
    with _local_locks_guard:
        lock = _local_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _local_locks[key] = lock
        return lock


@contextmanager
def distributed_lock(
    key: str,
    timeout: int = 30,
    blocking_timeout: int = 10,
) -> Iterator[None]:
    """分布式锁上下文管理器。

    - Redis 可用：``redis.lock.Lock``（跨进程/跨实例，自动 TTL 防死锁）
    - Redis 不可用：``threading.Lock``（仅单进程，blocking_timeout 控制等待）

    获取失败（超时未拿到锁）抛 ``LockAcquireError``，调用方可据此跳过重复操作。
    """
    redis_client = _get_redis_lock_client()

    if redis_client is not None:
        # Redis 分布式锁
        lock_name = f"finpilot:lock:{key}"
        lock = redis_client.lock(lock_name, timeout=timeout)
        acquired = False
        try:
            acquired = lock.acquire(blocking=True, blocking_timeout=blocking_timeout)
            if not acquired:
                raise LockAcquireError(
                    f"获取分布式锁超时: {key}（等待 {blocking_timeout}s）"
                )
            yield
        finally:
            if acquired:
                try:
                    lock.release()
                except Exception:  # noqa: BLE001  锁已过期或被强制释放
                    pass
        return

    # 进程内降级锁
    lock = _get_local_lock(key)
    acquired = lock.acquire(blocking=True, timeout=blocking_timeout)
    if not acquired:
        raise LockAcquireError(
            f"获取进程锁超时: {key}（等待 {blocking_timeout}s）"
        )
    try:
        yield
    finally:
        lock.release()
