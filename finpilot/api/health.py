# -*- coding: utf-8 -*-
"""``/health/*`` —— 生产级健康检查端点（K8s readiness/liveness 探针）。

端点契约（挂载在 app 根路径，非 /api/v1，便于 K8s 直接探活）：

- ``GET /health/live``  — 存活探针：进程能响应即 200，不检查依赖
- ``GET /health/ready`` — 就绪探针：检查 DB / Redis 连通性，全部 ok 才 200
- ``GET /health``       — 聚合状态：列出各依赖组件状态，便于运维排查

设计原则：
- 轻量：每个探测有超时保护（DB 1s / Redis 1s），不拖垮探针本身
- 降级：依赖不可达时返回 503 + 具体组件状态，而非 500 崩溃
- 无认证：探针端点不需要 session（K8s/负载均衡器无 cookie）
"""
from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/health", tags=["health"])

# 探测超时（秒），避免依赖卡死拖垮探针
_PROBE_TIMEOUT_S = 1.0


def _probe_db() -> dict:
    """探测数据库连通性：执行一次 SELECT 1。"""
    try:
        from finpilot.database import SessionLocal

        db = SessionLocal()
        try:
            from sqlalchemy import text

            db.execute(text("SELECT 1")).scalar()
            return {"status": "ok"}
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        return {"status": "down", "error": str(exc)[:200]}


def _probe_redis() -> dict:
    """探测 Redis 连通性（不通时返回 down，但不影响主流程）。"""
    try:
        import redis  # sync client

        url = __import__("os").getenv("REDIS_URL", "redis://localhost:6379/0")
        client = redis.from_url(url, socket_connect_timeout=_PROBE_TIMEOUT_S, socket_timeout=_PROBE_TIMEOUT_S)
        client.ping()
        client.close()
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "down", "error": str(exc)[:200]}


@router.get("/live")
def liveness() -> dict:
    """存活探针：进程能响应即健康，不检查依赖。"""
    return {"status": "ok"}


@router.get("/ready")
def readiness() -> JSONResponse:
    """就绪探针：DB 必须可达，Redis 降级容忍（down 不阻断就绪）。"""
    db = _probe_db()
    redis = _probe_redis()

    # DB 不可达 → 未就绪（503）；Redis 不可达 → 仍就绪（降级到内存）
    ready = db["status"] == "ok"
    body = {"status": "ready" if ready else "not_ready", "checks": {"db": db, "redis": redis}}
    return JSONResponse(
        status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=body,
    )


@router.get("")
def full_health() -> dict:
    """聚合健康状态：列出各依赖组件状态，便于运维排查。"""
    return {
        "status": "ok",
        "checks": {
            "db": _probe_db(),
            "redis": _probe_redis(),
        },
    }
