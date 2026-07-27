"""structlog 结构化日志 — 链路追踪（trace_id）+ 环境自适应渲染。

用法::

    from finpilot.core.logging import get_logger, setup_logging

    # 应用启动时调用一次
    setup_logging("development")

    # 模块级
    logger = get_logger(__name__)
    logger.info("something_happened", key="value")
"""
from __future__ import annotations

from contextvars import ContextVar

import structlog

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


def add_trace_id(logger, method_name, event_dict):
    """structlog processor：将 ContextVar 中的 trace_id 注入日志事件。"""
    tid = trace_id_var.get()
    if tid:
        event_dict["trace_id"] = tid
    return event_dict


def setup_logging(environment: str = "development") -> None:
    """全局配置 structlog。

    ``development`` 模式使用彩色 ConsoleRenderer，方便本地开发；
    ``production`` 模式使用 JSONRenderer，方便日志采集系统解析。
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_trace_id,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
            if environment == "development"
            else structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = __name__):
    """获取 structlog logger 实例。"""
    return structlog.get_logger(name)
