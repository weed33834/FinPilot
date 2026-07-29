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
import uuid
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy.exc import SQLAlchemyError

import structlog
from finpilot.api.rate_limit import limiter
from finpilot.core.logging import setup_logging, trace_id_var
from finpilot.middleware.tenant import TenantMiddleware

from .admin import router as admin_router
from .agent import router as agent_router
from .approvals import router as approvals_router
from .audit import router as audit_router
from .auth import router as auth_router
from .budgets import router as budgets_router
from .charts import router as charts_router
from .conversations import router as conversations_router
from .documents import router as documents_router
from .llm_providers import router as llm_providers_router
from .queries import router as queries_router
from .reports import router as reports_router
from .users import router as users_router

import os

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
    # 阶段 C 新增：财务智能体增强能力路由（校验/辩论/可解释/风险）
    (".validation", "router"),
    (".debate", "router"),
    (".explainability", "router"),
    (".risk", "router"),
    # Phase 1 新增
    (".ratios", "router"),
    (".three_statement", "router"),
    (".data_connections", "router"),
    # v1.1.0: 企业 SSO (OAuth 2.0 / OIDC)
    (".sso", "router"),
    # 板块C：前端 404 页面后端补齐
    (".api_keys", "router"),
    (".reflections", "router"),
    (".access_policies", "router"),
    (".hitl", "router"),
    (".eval", "router"),
    (".prompt_ab_tests", "router"),
    (".prompt_few_shot", "router"),
    # 站内通知（前端 NotificationBell 组件）
    (".notifications", "router"),
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

    @api.get("/")
    def health_check() -> dict[str, str]:
        """健康检查端点"""
        return {"status": "ok", "version": "2.0"}

    # 兼容路由必须先于 reports_router 注册，避免 /reports/templates 被 /reports/{report_id} 抢先匹配
    try:
        from .compat import register_compat_routes
        register_compat_routes(api)
    except Exception as exc:  # noqa: BLE001
        logger.warning("兼容路由加载失败（部分 admin 页可能 404）: %s", exc)
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
    api.include_router(budgets_router)
    api.include_router(charts_router)
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


def configure_middleware(app: FastAPI) -> None:
    """为任意 FastAPI app 统一挂载全部中间件与 lifespan。

    解决双 App 架构断裂：``finpilot_equity.web_app.main.app`` 此前仅挂载 CORS，
    缺失 TenantMiddleware / SlowAPIMiddleware / trace_middleware / subscription_scheduler lifespan。
    现统一通过本函数挂载，两个入口（``router.app`` 与 ``web_app.main.app``）行为一致。

    调用顺序：CORS → Tenant → SlowAPI → trace（FastAPI 中间件按 LIFO 执行，
    最后 add 的最先执行，故 trace 放最后确保最先注入 trace_id）。
    """
    # lifespan：启动订阅调度后台线程，停止时优雅关闭
    @asynccontextmanager
    async def _lifespan(_app: FastAPI):
        # 1. 启动订阅调度后台线程
        try:
            from finpilot.services.subscription_scheduler import start_scheduler
            start_scheduler()
        except Exception as exc:  # noqa: BLE001
            logger.warning("subscription_scheduler_start_failed: %s", exc)
        # 2. 批量加载 MCP 工具到 tool_registry（此前从未在启动时调用，导致 MCP 工具永远不可用）
        try:
            from finpilot.database import SessionLocal
            from finpilot.services.mcp_tool_bridge import register_mcp_tools
            with SessionLocal() as _db:
                n = register_mcp_tools("default", _db)
                if n:
                    logger.info("mcp_tools_registered_at_startup: %d", n)
        except Exception as exc:  # noqa: BLE001
            logger.warning("mcp_tools_startup_load_failed: %s", exc)
        # 3. 从 DB 重建 RAG 内存索引（vector_store/bm25_index/registry 为进程级状态，
        #    重启后全空导致检索返回空；此前服务重启后所有 RAG 检索失效）
        try:
            from finpilot.database import SessionLocal
            from finpilot.rag import RagService
            with SessionLocal() as _db:
                RagService(_db).rebuild_from_db(_db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("rag_index_rebuild_at_startup_failed: %s", exc)
        try:
            yield
        finally:
            try:
                from finpilot.services.subscription_scheduler import stop_scheduler
                stop_scheduler()
            except Exception:  # noqa: BLE001
                pass

    # 设置 lifespan：赋值 ``app.router.lifespan_context``。
    # Starlette 1.3+ 中 ``Router.lifespan`` 是 ASGI lifespan 处理 *方法*
    # (self, scope, receive, send)，实际逻辑存于 ``lifespan_context``（一个接受 app
    # 返回异步上下文管理器的可调用对象）。此前用 ``app.router.lifespan = _lifespan``
    # 会覆盖该方法导致 ``TypeError: takes 1 positional argument but 3 were given``；
    # 而更早的 ``if lifespan_context is None`` 守卫因默认非 None 永不成立，
    # 致使订阅调度线程与 MCP 工具启动注册静默失效。现直接赋值 lifespan_context 修复。
    app.router.lifespan_context = _lifespan

    # Rate Limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # 多租户中间件 — 从 X-Tenant-ID 请求头或用户会话提取 tenant_id
    app.add_middleware(TenantMiddleware)

    # 链路追踪中间件 — 每个请求生成 trace_id 注入 structlog 上下文中
    @app.middleware("http")
    async def trace_middleware(request: Request, call_next):
        trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
        trace_id_var.set(trace_id)
        structlog.contextvars.bind_contextvars(trace_id=trace_id)
        response = await call_next(request)
        response.headers["X-Trace-ID"] = trace_id
        return response

    # CORS
    configure_cors(app)

    # 全局异常处理器 — 脱敏未捕获异常，避免堆栈泄露给前端
    @app.exception_handler(Exception)
    async def _global_exception_handler(request: Request, exc: Exception):
        logger.exception("unhandled_exception path=%s method=%s", request.url.path, request.method)
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=500,
            content={
                "code": -1,
                "message": "服务器内部错误，请联系管理员",
                "data": None,
            },
            headers={"X-Trace-ID": request.headers.get("X-Trace-ID", "")},
        )

    # Prometheus 指标采集：暴露 /metrics 端点供 Grafana/Prometheus 抓取。
    # 采集请求量、延迟分位、状态码分布、在途请求数等默认指标。
    # best-effort：库未安装时降级跳过，不影响应用启动。
    try:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator().instrument(app).expose(
            app, endpoint="/metrics", include_in_schema=False
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("prometheus_instrumentation_skipped: %s", exc)


def _ensure_default_admin() -> None:
    """确保存在默认管理员账号，幂等。

    安全改进：管理员密码从环境变量 ``FINPILOT_ADMIN_PASSWORD`` 读取，
    未设置则不创建默认管理员（避免硬编码 admin123 的安全风险）。
    同时导入默认 LLM 供应商与模型。
    """
    from finpilot.database import SessionLocal, crud, init_db
    from finpilot.database.models import LlmProvider, LlmModel
    from .deps import hash_password

    try:
        init_db()
    except SQLAlchemyError:
        return

    admin_email = os.getenv("FINPILOT_ADMIN_EMAIL", "admin@finpilot.ai")
    admin_password = os.getenv("FINPILOT_ADMIN_PASSWORD", "")

    db = SessionLocal()
    try:
        if not crud.get_user_by_email(db, admin_email):
            if not admin_password:
                logger.warning(
                    "default_admin_skipped: FINPILOT_ADMIN_PASSWORD 未设置，"
                    "跳过默认管理员创建。请设置环境变量或手动创建管理员。"
                )
            else:
                crud.create_user(
                    db,
                    email=admin_email,
                    password_hash=hash_password(admin_password),
                    name="管理员",
                    role="admin",
                )

        # 导入默认 LLM 供应商与模型（基于 .env 配置）
        if not db.query(LlmProvider).first():
            default_api_key = os.getenv("OPENAI_API_KEY", "")
            default_base_url = os.getenv("OPENAI_BASE_URL", "")
            default_model = os.getenv("OPENAI_MODEL", "DeepSeek-V4-Pro")
            encoded_key = crud.encode_api_key(default_api_key) if default_api_key else None
            provider = LlmProvider(
                name="默认供应商",
                provider_type="openai",
                base_url=default_base_url,
                api_key=encoded_key,
                is_default=True,
                is_active=True,
            )
            db.add(provider)
            db.flush()
            db.add(LlmModel(
                provider_id=provider.id,
                model_name=default_model,
                display_name=default_model,
                tier="high",
                is_active=True,
            ))
            db.commit()
    except SQLAlchemyError:
        db.rollback()
    finally:
        db.close()


# 模块级 FastAPI 应用实例（供 uvicorn 直接加载）
setup_logging()

app = FastAPI(title="FinPilot AI", version="1.0.0")
configure_middleware(app)
app.include_router(create_router())

# WebSocket 实时通知端点：直接挂载在 app 上（不带 /api/v1 前缀），
# 与前端 useWebSocket.ts 默认 URL `/ws/notifications` 对齐。
try:
    from .websocket import router as websocket_router

    app.include_router(websocket_router)
except Exception as exc:  # noqa: BLE001
    logger.warning("websocket_router 加载失败: %s", exc)

# 生产级健康检查端点：挂载在 app 根路径 /health/*（非 /api/v1），
# 便于 K8s readiness/liveness 探针与负载均衡器直接探活（无需 cookie 认证）。
try:
    from .health import router as health_router

    app.include_router(health_router)
except Exception as exc:  # noqa: BLE001
    logger.warning("health_router 加载失败: %s", exc)
