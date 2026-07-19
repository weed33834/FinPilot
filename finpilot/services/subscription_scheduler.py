"""订阅调度器：扫描到期订阅并逐个执行."""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

# TODO: requires finpilot.core.tenant_context；FinPilot 使用 SQLite，无 RLS，
#   set_tenant_session 在源项目中于非 PostgreSQL 方言上本就是 no-op。
#   FinPilot 内核未提供该模块，本文件已将其移入函数体内 best-effort 调用。
# from finpilot.core.tenant_context import set_tenant_session  # 移到函数内
from finpilot.database.models import ReportSubscription
from finpilot.services.subscription_crud import compute_next_run
from finpilot.services.subscription_runner import run_subscription_once


def _set_tenant_session(db: Session, tenant_id: str | None) -> None:
    """设置租户上下文（no-op on SQLite / 缺失依赖时安全降级）."""
    try:
        from finpilot.core.tenant_context import set_tenant_session

        set_tenant_session(db, tenant_id)
    except ImportError:
        return
    except Exception:  # noqa: BLE001
        return


def run_due_subscriptions(
    db: Session,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """执行所有到期订阅。

    采用「认领即推进」模式：扫描到期订阅后，**先把 next_run_at 推进到下一
    调度点并提交**，再执行报告生成 / 导出 / 通知。这样即使单轮执行超过
    beat 间隔（600s），下一轮 beat 也不会重复拾取同一订阅造成重复报告。
    单个订阅失败不中断其他订阅；失败时记录 last_error，next_run_at 已在
    认领阶段推进，避免故障订阅在下一轮立即重试造成刷屏。

    M1：扫描阶段在 system_db_session 的 ``SET LOCAL row_security = off``
    事务内完成（跨租户读取到期订阅）；但认领 ``db.commit()`` 后该 ``SET LOCAL``
    失效，RLS 恢复开启。此后写订阅行 / 执行报告生成必须在正确的租户上下文
    中进行，故在认领前为每个订阅 ``set_tenant_session``，使 RLS 策略按该
    订阅租户过滤。run_subscription_once 内部在每个事务段前也会重新设置
    （应对其内部 commit 后 GUC 失效）。SQLite 等不支持 RLS 的方言上 no-op。
    """
    if now is None:
        now = datetime.now(UTC)

    due = (
        db.query(ReportSubscription)
        .filter(
            ReportSubscription.is_active == "Y",
            ReportSubscription.next_run_at.is_not(None),
            ReportSubscription.next_run_at <= now,
        )
        .all()
    )

    results: list[dict[str, Any]] = []
    for sub in due:
        # M1：为认领写入设置租户上下文。首轮仍在扫描事务内（RLS off），
        # GUC 不影响；后续轮 RLS 已恢复开启，写订阅行需 GUC 匹配 tenant_id。
        _set_tenant_session(db, sub.tenant_id)
        # 认领：先推进 next_run_at 并提交，防止 beat 重叠时重复执行。
        # 若进程在认领后、执行前崩溃，本轮报告丢失，但下一调度点会正常触发，
        # 不会永久卡死。
        claimed_next = compute_next_run(
            sub.frequency,
            sub.at_hour,
            sub.at_minute,
            sub.day_of_week,
            sub.day_of_month,
            now,
        )
        sub.next_run_at = claimed_next
        with suppress(Exception):
            db.commit()
        db.refresh(sub)

        try:
            outcome = run_subscription_once(db, sub, now=now)
            sub.last_run_at = now
            sub.last_report_id = outcome["report_id"]
            sub.last_error = "; ".join(outcome["warnings"]) or None
            status = "success"
            error = None
        except Exception as exc:  # noqa: BLE001
            # run_subscription_once 在生成阶段失败时不会持久化半成品报告
            # （Report 行仅在生成成功后才 db.add），故此处可直接更新订阅
            # 状态并提交，无需回滚。next_run_at 已在认领阶段推进。
            sub.last_run_at = now
            sub.last_report_id = None
            sub.last_error = str(exc)
            status = "failed"
            error = str(exc)

        # M1：状态更新写入订阅行，需在租户上下文中提交（run_subscription_once
        # 内部 commit 后 GUC 可能已失效，重新设置确保 WITH CHECK 通过）。
        _set_tenant_session(db, sub.tenant_id)
        with suppress(Exception):
            db.commit()
        results.append(
            {
                "subscription_id": sub.id,
                "report_id": sub.last_report_id,
                "status": status,
                "error": error,
            }
        )
    return results
