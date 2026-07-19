# -*- coding: utf-8 -*-
"""FinPilot API 路由层 - 将 finpilot 核心模块暴露为 REST API。

用法::

    from finpilot.api import create_router, configure_cors
"""
from .router import configure_cors, create_router

__all__ = ["create_router", "configure_cors"]
