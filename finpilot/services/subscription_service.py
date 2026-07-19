"""报告订阅服务聚合入口.

子模块：subscription_crud / subscription_runner / subscription_scheduler。
保留此文件以兼容现有 ``from finpilot.services.subscription_service import ...`` 导入，
路由、任务、测试均通过本入口访问公开 API，无需修改。

依赖方向（无环）：
  - subscription_crud：纯 CRUD 与下次执行时间计算
  - subscription_runner → subscription_crud（执行单次订阅时查询创建者）
  - subscription_scheduler → subscription_crud + subscription_runner
"""

from finpilot.services.subscription_crud import (
    compute_next_run,
    create_subscription,
    delete_subscription,
    get_subscription,
    list_subscriptions,
    update_subscription,
)
from finpilot.services.subscription_runner import run_subscription_once
from finpilot.services.subscription_scheduler import run_due_subscriptions

__all__ = [
    "compute_next_run",
    "create_subscription",
    "delete_subscription",
    "get_subscription",
    "list_subscriptions",
    "run_due_subscriptions",
    "run_subscription_once",
    "update_subscription",
]
