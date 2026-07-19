"""报告订阅 CRUD 与下次执行时间计算.

依赖方向：本模块为底层，不依赖 runner / scheduler，避免循环引用。
``subscription_runner`` / ``subscription_scheduler`` 直接从本模块导入所需函数。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

# TODO: requires finpilot.database.models.ReportSubscription
from finpilot.database.models import ReportSubscription
from finpilot.database.models import User
# TODO: finpilot.services.audit_service 不存在；FinPilot 有 finpilot.security.audit.record_event，
#   但签名不兼容（record_event 无 db/resource/user/commit 参数，且自行开 Session）。
#   需在 FinPilot 侧补一个 log_action 适配层或改写调用点。
from finpilot.services.audit_service import log_action
# TODO: requires finpilot.utils.pagination.paginate
from finpilot.utils.pagination import paginate


def compute_next_run(
    frequency: str,
    at_hour: int,
    at_minute: int,
    day_of_week: int | None,
    day_of_month: int | None,
    now: datetime,
) -> datetime:
    """计算下一次执行时间（UTC）。

    纯函数，便于单测。``now`` 须为带时区时间。
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    def _at(date: datetime, hour: int, minute: int) -> datetime:
        return date.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if frequency == "daily":
        candidate = _at(now, at_hour, at_minute)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    if frequency == "weekly":
        if day_of_week is None:
            day_of_week = 0
        # Python weekday(): 周一=0 ... 周日=6，与订阅约定一致
        days_ahead = (day_of_week - now.weekday()) % 7
        candidate = _at(now + timedelta(days=days_ahead), at_hour, at_minute)
        if candidate <= now:
            candidate += timedelta(days=7)
        return candidate

    if frequency == "monthly":
        if day_of_month is None:
            day_of_month = 1
        # 封顶 28，所有月份都合法，无需处理月末
        candidate = _at(now.replace(day=day_of_month), at_hour, at_minute)
        if candidate <= now:
            if now.month == 12:
                candidate = candidate.replace(year=now.year + 1, month=1)
            else:
                candidate = candidate.replace(month=now.month + 1)
        return candidate

    # 未知频率退化为每日
    candidate = _at(now, at_hour, at_minute)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def _resolve_creator(db: Session, sub: ReportSubscription) -> User | None:
    if not sub.created_by:
        return None
    return db.query(User).filter(User.id == sub.created_by).first()


def create_subscription(
    db: Session,
    tenant_id: str,
    user: User,
    data: Any,
) -> ReportSubscription:
    """创建订阅并计算首次执行时间."""
    now = datetime.now(UTC)
    sub = ReportSubscription(
        tenant_id=tenant_id,
        created_by=user.id,
        name=data.name,
        report_type=data.report_type,
        parameters=data.parameters,
        frequency=data.frequency,
        at_hour=data.at_hour,
        at_minute=data.at_minute,
        day_of_week=data.day_of_week,
        day_of_month=data.day_of_month,
        export_format=data.export_format,
        channels=data.channels,
        recipients=data.recipients,
        is_active="Y",
        next_run_at=compute_next_run(
            data.frequency,
            data.at_hour,
            data.at_minute,
            data.day_of_week,
            data.day_of_month,
            now,
        ),
    )
    db.add(sub)
    db.flush()
    log_action(
        db=db,
        action="report_subscription.create",
        resource=f"report_subscription://{sub.id}",
        user=user,
        commit=False,
    )
    db.commit()
    db.refresh(sub)
    return sub


def get_subscription(
    db: Session,
    subscription_id: str,
    tenant_id: str,
) -> ReportSubscription | None:
    return (
        db.query(ReportSubscription)
        .filter(
            ReportSubscription.id == subscription_id,
            ReportSubscription.tenant_id == tenant_id,
        )
        .first()
    )


def list_subscriptions(
    db: Session,
    tenant_id: str,
    page: int = 1,
    page_size: int = 20,
    active_only: bool = False,
) -> tuple[list[ReportSubscription], int]:
    query = db.query(ReportSubscription).filter(
        ReportSubscription.tenant_id == tenant_id
    )
    if active_only:
        query = query.filter(ReportSubscription.is_active == "Y")
    items, total = paginate(
        query.order_by(ReportSubscription.created_at.desc()), page, page_size
    )
    return items, total


def update_subscription(
    db: Session,
    sub: ReportSubscription,
    data: Any,
    user: User,
) -> ReportSubscription:
    """更新订阅字段；调度相关字段变更时重算下次执行时间."""
    schedule_changed = False
    reactivating = False
    for field in (
        "name",
        "parameters",
        "frequency",
        "at_hour",
        "at_minute",
        "day_of_week",
        "day_of_month",
        "export_format",
        "channels",
        "recipients",
        "is_active",
    ):
        value = getattr(data, field)
        if value is not None:
            if field == "is_active" and sub.is_active == "N" and value == "Y":
                # 重新启用：旧 next_run_at 可能已过期，若不重算会在下一轮 beat
                # 立即触发。这里从当前时间重算到下一个调度点。
                reactivating = True
            setattr(sub, field, value)
            if field in ("frequency", "at_hour", "at_minute", "day_of_week", "day_of_month"):
                schedule_changed = True

    if schedule_changed or reactivating:
        sub.next_run_at = compute_next_run(
            sub.frequency,
            sub.at_hour,
            sub.at_minute,
            sub.day_of_week,
            sub.day_of_month,
            datetime.now(UTC),
        )

    db.flush()
    log_action(
        db=db,
        action="report_subscription.update",
        resource=f"report_subscription://{sub.id}",
        user=user,
        commit=False,
    )
    db.commit()
    db.refresh(sub)
    return sub


def delete_subscription(db: Session, sub: ReportSubscription, user: User) -> None:
    db.delete(sub)
    log_action(
        db=db,
        action="report_subscription.delete",
        resource=f"report_subscription://{sub.id}",
        user=user,
        commit=False,
    )
    db.commit()
