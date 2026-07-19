# -*- coding: utf-8 -*-
"""统一路由聚合 - 挂载所有子路由到 /api/v1 前缀下。

用法::

    from finpilot.api import create_router, configure_cors
    from fastapi import FastAPI

    app = FastAPI()
    configure_cors(app)          # 配置 CORS（允许前端 localhost:5173 跨域携带 cookie）
    app.include_router(create_router())
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from .admin import router as admin_router
from .agent import router as agent_router
from .approvals import router as approvals_router
from .audit import router as audit_router
from .auth import router as auth_router
from .conversations import router as conversations_router
from .documents import router as documents_router
from .llm_providers import router as llm_providers_router
from .queries import router as queries_router
from .reports import router as reports_router
from .users import router as users_router

logger = logging.getLogger(__name__)

# 允许的前端来源（Vite 默认端口 5173）
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# 扩展路由：财务智能体平台配套模块路由。
# 用 try/except 逐个加载，某个路由因依赖缺失无法加载时记录警告但不影响核心功能。
# dashboard 模块导出两个 router：router（管理后台）+ user_router（用户仪表盘，前端调用）。
_EXTENSION_ROUTERS: list[tuple[str, str]] = [
    (".backtesting", "router"),
    (".factor_mining", "router"),
    (".valuation", "router"),
    (".mcp_servers", "router"),
    (".report_subscriptions", "router"),
    (".report_templates", "router"),
    (".sandbox_configs", "router"),
    (".prompts", "router"),
    (".skills", "router"),
    (".tools", "router"),
    (".dashboard", "router"),
    (".dashboard", "user_router"),
    (".runtime_logs", "router"),
]


def _load_extension_routers(api: APIRouter) -> None:
    """安全加载扩展路由，失败时记录警告但不中断。"""
    import importlib

    # package=__package__ 让相对路径 ".backtesting" 解析为 "finpilot.api.backtesting"
    # （__name__ 是 "finpilot.api.router"，会把 ".backtesting" 错误解析为 "finpilot.api.router.backtesting"）
    for module_path, attr in _EXTENSION_ROUTERS:
        try:
            mod = importlib.import_module(module_path, package=__package__)
            router_obj = getattr(mod, attr, None)
            if router_obj is not None:
                api.include_router(router_obj)
        except Exception as exc:  # noqa: BLE001
            logger.warning("扩展路由 %s 加载失败（功能降级）: %s", module_path, exc)


def create_router() -> APIRouter:
    """创建聚合路由器，所有子路由挂载在 /api/v1 下"""
    api = APIRouter(prefix="/api/v1")
    api.include_router(auth_router)
    api.include_router(documents_router)
    api.include_router(queries_router)
    api.include_router(agent_router)
    api.include_router(conversations_router)
    api.include_router(reports_router)
    api.include_router(llm_providers_router)
    api.include_router(admin_router)
    # 用户管理 / 审计日志 / 报告审批（管理员路由）
    api.include_router(users_router)
    api.include_router(audit_router)
    api.include_router(approvals_router)
    # 加载扩展路由（失败不影响核心功能）
    _load_extension_routers(api)
    # 确保默认管理员存在，使管理员路由开箱可用（幂等）
    _ensure_default_admin()
    return api


def configure_cors(app: FastAPI) -> None:
    """为 FastAPI 应用配置 CORS（允许前端跨域携带 cookie）。

    注意：CORS 中间件必须挂载在 app 上（而非子路由），且需在 include_router 之前调用。
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _ensure_default_admin() -> None:
    """确保存在默认管理员账号（admin@finpilot.ai / admin123），幂等。

    先建表再建用户，失败不阻断路由创建。
    """
    from finpilot.database import SessionLocal, crud, init_db
    from .deps import hash_password

    try:
        init_db()
    except SQLAlchemyError:
        return

    db = SessionLocal()
    try:
        if not crud.get_user_by_email(db, "admin@finpilot.ai"):
            crud.create_user(
                db,
                email="admin@finpilot.ai",
                password_hash=hash_password("admin123"),
                name="管理员",
                role="admin",
            )
    except SQLAlchemyError:
        pass
    finally:
        db.close()
