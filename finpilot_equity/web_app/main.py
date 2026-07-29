"""FinPilot AI 官方 ASGI 入口（README 指定的 uvicorn target）.

历史版本在此文件内自定义 /api/auth/* cookie-session 鉴权、/api/admin/* 管理路由、
Jinja2 模板与 /static 资源、GitHub OAuth 旧实现等，与 finpilot/api/*（JWT 鉴权 +
React SPA 前端）功能完全重复且前端从不调用，已全部移除。

当前职责仅剩「装配 FastAPI app + 挂载 finpilot.api 路由 + 初始化数据库」，
所有业务逻辑均在 finpilot/ 业务包内。
"""
import logging

from fastapi import FastAPI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="FinPilot AI", version="2.0.0")

# ============== FinPilot AI 业务路由与中间件 ==============
from finpilot.api import create_router, configure_middleware  # noqa: E402
from finpilot.database import init_db as init_finpilot_db  # noqa: E402
from finpilot.database.connection import SessionLocal as FinPilotSessionLocal  # noqa: E402
from finpilot.database.seed import seed_financial_data  # noqa: E402

# 初始化数据库 + 示例财务数据
init_finpilot_db()
with FinPilotSessionLocal() as _fp_session:
    seed_financial_data(_fp_session)

# 统一挂载中间件（CORS + Tenant + RateLimit + trace + lifespan/subscription_scheduler）
configure_middleware(app)
# 挂载 /api/v1 路由
app.include_router(create_router())

# WebSocket 实时通知端点：与 finpilot.api.router.app 入口对齐
try:
    from finpilot.api.websocket import router as websocket_router
    app.include_router(websocket_router)
except Exception as exc:  # noqa: BLE001
    logger.warning("websocket_router 加载失败: %s", exc)
