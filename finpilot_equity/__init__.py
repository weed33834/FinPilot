"""FinPilot AI — Web 应用入口包.

本包仅暴露 FastAPI 应用对象 ``app``，由 ``finpilot_equity.web_app.main`` 提供。
所有业务逻辑统一封装在 ``finpilot`` 包内，``web_app`` 只负责挂载 /api/v1 路由、
配置 CORS 与初始化数据库。
"""

__version__ = "1.0.0"
__author__ = "badhope"
__description__ = "FinPilot AI — 企业财务智能体平台"

__all__: list[str] = []
