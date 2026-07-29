"""订阅单次执行：生成报告 → 导出.

原始实现依赖 ``finpilot.reporting.generator`` / ``finpilot.services.export_service``
/ ``finpilot.storage`` / ``finpilot.core.tenant_context`` 等模块，但 FinPilot 内核
并未提供这些模块，导致订阅执行必然失败（坏 import）。

本文件已重写为复用 ``finpilot.api.reports._generate_report_content`` 的生成逻辑
（FinancialReport + FinancialAccount 聚合 + LLM 摘要），导出改为 data: URI 方式
（与 reports.export_report 一致），使订阅执行链路真正打通。
"""

from __future__ import annotations

import urllib.parse
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from finpilot.database.models import Report, ReportSubscription
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


def _generate_report_content(report_id: int, tenant_id: str) -> None:
    """复用 reports.py 的报告生成逻辑（同步执行）.

    直接调用 finpilot.api.reports._generate_report_content，避免重复实现
    FinancialReport/FinancialAccount 聚合 + LLM 摘要逻辑。
    """
    from finpilot.api.reports import _generate_report_content as _gen

    _gen(report_id=report_id, tenant_id=tenant_id)


def _export_report_as_data_uri(report: Report) -> str:
    """把报告内容序列化为 markdown data: URI（与 reports.export_report 一致）."""
    content = report.content or {}
    md_lines = [f"# {report.title}", ""]
    if report.summary:
        md_lines.append(f"**摘要**: {report.summary}")
        md_lines.append("")
    for section in content.get("sections", []):
        md_lines.append(f"## {section.get('name', '')}")
        md_lines.append(f"值: {section.get('value', 'N/A')}")
        md_lines.append("")
    md_text = "\n".join(md_lines)
    encoded = urllib.parse.quote(md_text)
    return f"data:text/markdown;charset=utf-8,{encoded}"


def run_subscription_once(
    db: Session,
    sub: ReportSubscription,
    now: datetime | None = None,
) -> dict[str, Any]:
    """执行单次订阅：生成报告 → 导出。

    流程：
    1. 创建 Report 行（status=processing）并提交，拿到 report.id；
    2. 调用 _generate_report_content 同步生成内容（聚合财务数据 + LLM 摘要），
       生成失败时把 Report.status 置 failed 并抛出异常；
    3. 导出为 data: URI 写入 Report.content_url（best-effort，失败记 warnings）；
    4. 审计埋点 report_subscription.generate。

    返回 ``{"report_id", "content_url", "warnings"}``。
    """
    if now is None:
        now = datetime.now(UTC)

    creator = _resolve_creator(db, sub)

    # 事务段 1：创建 Report 行
    _set_tenant_session(db, sub.tenant_id)
    report = Report(
        tenant_id=sub.tenant_id,
        created_by=sub.created_by,
        title=f"[订阅] {sub.name}",
        report_type=sub.report_type,
        parameters=sub.parameters or {},
        status="processing",
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    # 事务段 2：生成报告内容（复用 reports.py 逻辑）
    warnings: list[str] = []
    try:
        _generate_report_content(report.id, sub.tenant_id)
        db.refresh(report)
    except Exception as exc:  # noqa: BLE001
        # 生成失败：标记 Report 失败并抛出，让 scheduler 记录 last_error
        report.status = "failed"
        report.error_message = str(exc)[:500]
        db.commit()
        raise RuntimeError(f"报告生成失败: {exc}") from exc

    # 事务段 3：导出为 data: URI（best-effort）
    try:
        content_url = _export_report_as_data_uri(report)
        report.content_url = content_url
        db.commit()
        db.refresh(report)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"导出失败: {exc}")
        content_url = None

    # 审计埋点
    try:
        log_action(
            db=db,
            action="report_subscription.generate",
            resource=f"report:{report.id}",
            user=creator,
            reason=f"subscription={sub.id}",
            commit=False,
            target_object_type="report",
            target_object_id=str(report.id),
            meta={"subscription_id": sub.id, "report_type": sub.report_type},
        )
    except Exception:  # noqa: BLE001
        pass

    # 通知订阅创建人：订阅报告已生成（best-effort，DB 写入 + WebSocket 推送）
    if sub.created_by is not None:
        try:
            from finpilot.api.notifications import notify_user

            notify_user(
                db,
                f"user_{sub.created_by}",
                channel="report",
                title="订阅报告已生成",
                content=f"订阅「{sub.name}」触发生成的报告《{report.title}》已完成",
                tenant_id=sub.tenant_id,
            )
        except Exception:  # noqa: BLE001
            pass

    return {"report_id": report.id, "content_url": content_url, "warnings": warnings}
