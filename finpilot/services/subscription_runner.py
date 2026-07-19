"""订阅单次执行：生成报告 → 导出.

FinPilot 内核尚未提供 ``finpilot.core.tenant_context`` / ``finpilot.reporting.generator``
/ ``finpilot.services.export_service`` / ``finpilot.storage`` 等模块；本文件已把这些
导入移到函数内部并加 best-effort fallback，使模块导入不再因缺失依赖而失败。

仅当真正调用 ``run_subscription_once`` 时才会触发对应 ImportError，并在那时以
清晰错误信息提示；列表/查询接口不会受影响。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

# Report ORM 在 FinPilot 中尚未定义（仅有 FinancialReport），导入时置 None，
# 真正调用 run_subscription_once 时若仍为 None 则抛清晰错误。
try:
    from finpilot.database.models import Report
except ImportError:  # pragma: no cover
    Report = None  # type: ignore[assignment,misc]

from finpilot.database.models import ReportSubscription
from finpilot.services.audit_service import log_action
from finpilot.services.subscription_crud import _resolve_creator


def _set_tenant_session(db: Session, tenant_id: str | None) -> None:
    """设置租户上下文（no-op on SQLite / 缺失依赖时安全降级）."""
    try:
        from finpilot.core.tenant_context import set_tenant_session

        set_tenant_session(db, tenant_id)
    except ImportError:
        # FinPilot 使用 SQLite，无 RLS，set_tenant_session 在源项目本就是 no-op
        return
    except Exception:  # noqa: BLE001
        return


def _get_report_generator(db: Session):
    """加载 ReportGenerator；缺失时抛清晰错误."""
    from finpilot.reporting.generator import ReportGenerator  # noqa: PLC0415

    return ReportGenerator(db)


def _get_storage_client():
    """加载 storage client；缺失时抛清晰错误."""
    from finpilot.storage import get_storage_client  # noqa: PLC0415

    return get_storage_client()


def _export_report(*, db, report, storage, user, fmt):
    """调用 export_service；缺失时抛清晰错误."""
    from finpilot.services.export_service import export_report  # noqa: PLC0415

    return export_report(db=db, report=report, storage=storage, user=user, fmt=fmt)


def run_subscription_once(
    db: Session,
    sub: ReportSubscription,
    now: datetime | None = None,
) -> dict[str, Any]:
    """执行单次订阅：生成报告 → 导出。

    报告生成失败抛 ``ReportGenerationError``（或 ImportError 当依赖缺失时）；导出
    失败记入 warnings 不抛出。返回 ``{"report_id", "content_url", "warnings"}``。
    """
    if now is None:
        now = datetime.now(UTC)

    creator = _resolve_creator(db, sub)

    # 事务段 1：生成报告
    _set_tenant_session(db, sub.tenant_id)
    if Report is None:
        raise RuntimeError(
            "Report ORM 模型未定义，无法执行订阅；请在 finpilot.database.models 中补充 Report 表"
        )
    report = Report(
        tenant_id=sub.tenant_id,
        created_by=sub.created_by,
        title=f"[订阅] {sub.name}",
        report_type=sub.report_type,
        parameters=sub.parameters or {},
        status="processing",
    )

    report_generator = _get_report_generator(db)
    result = report_generator.generate(report)
    report.content = result["content"]
    report.summary = result["summary"]
    report.status = "reviewing"

    db.add(report)
    db.flush()

    log_action(
        db=db,
        action="report_subscription.generate",
        resource=f"report://{report.id}",
        user=creator,
        reason=f"subscription={sub.id}",
        commit=False,
    )
    db.commit()
    db.refresh(report)

    warnings: list[str] = []
    content_url: str | None = None

    # 事务段 2：导出（失败不阻断主流程）
    _set_tenant_session(db, sub.tenant_id)
    try:
        content_url = _export_report(
            db=db,
            report=report,
            storage=_get_storage_client(),
            user=creator,
            fmt=sub.export_format,
        )
        db.commit()
        db.refresh(report)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"导出失败: {exc}")

    return {"report_id": report.id, "content_url": content_url, "warnings": warnings}
