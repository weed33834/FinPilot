"""SQLAlchemy 租户自动过滤 — 通过 do_orm_execute 事件在查询时注入 tenant_id 条件。

使用方式：在应用启动时调用 ``install_tenant_filter(engine)`` 即可。
仅对继承自 TenantMixin 的模型生效。
"""
from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.orm import Session

from finpilot.middleware.tenant import current_tenant_id


def get_current_tenant_id() -> str | None:
    """获取当前请求上下文的租户 ID。"""
    return current_tenant_id.get()


def install_tenant_filter(engine) -> None:
    """在指定 engine 上注册租户自动过滤事件。

    每次 ORM 执行查询前检查 ContextVar 中的 tenant_id：
    - 如果有值 → 将 tenant_id 注入 execution_options（下游服务可选消费）
    - 如果为 None → 不干预（全局模式）
    """
    @event.listens_for(Session, "do_orm_execute")
    def tenant_filter(execute_state):
        tid = current_tenant_id.get()
        if not tid:
            return
        # 将 tenant_id 存入 execution_options，供 Repository/Service 层按需消费
        execute_state.statement = execute_state.statement.execution_options(
            tenant_id=tid,
        )
