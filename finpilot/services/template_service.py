"""报告模板 CRUD 服务.

直接操作 ``ReportTemplate`` ORM，封装列表/获取/创建/更新/删除。
所有写操作 best-effort 记录审计日志（``log_action``）。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from finpilot.database.models import ReportTemplate, User
from finpilot.services.audit_service import log_action
from finpilot.utils.pagination import paginate


def _normalize_active(value: Any) -> str:
    """把任意 is_active 输入归一为 ORM 使用的 'Y'/'N' 字符串."""
    if isinstance(value, str):
        if value in ("Y", "N"):
            return value
        return "Y" if value.lower() in ("true", "1", "y", "yes") else "N"
    if value is None:
        return "Y"
    return "Y" if bool(value) else "N"


def list_templates(
    *,
    db: Session,
    tenant_id: str,
    page: int = 1,
    page_size: int = 20,
    active_only: bool = False,
) -> tuple[list[ReportTemplate], int]:
    """查询当前租户的模板列表（按更新时间倒序）."""
    query = db.query(ReportTemplate).filter(ReportTemplate.tenant_id == tenant_id)
    if active_only:
        query = query.filter(ReportTemplate.is_active == "Y")
    query = query.order_by(ReportTemplate.updated_at.desc(), ReportTemplate.created_at.desc())
    return paginate(query, page, page_size)


def get_template(
    *,
    db: Session,
    template_id: str,
    tenant_id: str,
) -> ReportTemplate | None:
    """获取单个模板（按租户隔离）."""
    try:
        tid = int(template_id)
    except (TypeError, ValueError):
        return None
    return (
        db.query(ReportTemplate)
        .filter(
            ReportTemplate.id == tid,
            ReportTemplate.tenant_id == tenant_id,
        )
        .first()
    )


def create_template(
    *,
    db: Session,
    data: Any,
    user: Any,
) -> ReportTemplate:
    """创建模板。data 期望含 name/report_type/sections/summary_template/title_template."""
    tenant_id = str(_extract(user, "user_id", "default"))
    payload = _data_to_dict(data)
    tpl = ReportTemplate(
        tenant_id=tenant_id,
        name=payload.get("name") or "",
        report_type=payload.get("report_type") or "custom",
        sections=payload.get("sections") or [],
        summary_template=payload.get("summary_template") or "",
        title_template=payload.get("title_template") or "",
        created_by=_extract(user, "user_id"),
        is_active="Y",
    )
    db.add(tpl)
    db.flush()
    log_action(
        db=db,
        action="report_template.create",
        resource=f"report_template://{tpl.id}",
        user=user,
        commit=False,
    )
    db.commit()
    db.refresh(tpl)
    return tpl


def update_template(
    *,
    db: Session,
    template: ReportTemplate,
    data: Any,
    user: Any,
) -> ReportTemplate:
    """更新模板字段（部分更新）."""
    payload = _data_to_dict(data)
    if "name" in payload:
        template.name = payload["name"] or template.name
    if "sections" in payload:
        template.sections = payload["sections"] or []
    if "summary_template" in payload:
        template.summary_template = payload["summary_template"] or ""
    if "title_template" in payload:
        template.title_template = payload["title_template"] or ""
    if "is_active" in payload and payload["is_active"] is not None:
        template.is_active = _normalize_active(payload["is_active"])

    db.flush()
    log_action(
        db=db,
        action="report_template.update",
        resource=f"report_template://{template.id}",
        user=user,
        commit=False,
    )
    db.commit()
    db.refresh(template)
    return template


def delete_template(
    *,
    db: Session,
    template: ReportTemplate,
    user: Any,
) -> None:
    """删除模板."""
    tpl_id = template.id
    db.delete(template)
    log_action(
        db=db,
        action="report_template.delete",
        resource=f"report_template://{tpl_id}",
        user=user,
        commit=False,
    )
    db.commit()


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _extract(user: Any, key: str, default: Any = None) -> Any:
    """从 user（dict / ORM）中取字段."""
    if user is None:
        return default
    if isinstance(user, dict):
        return user.get(key, default)
    return getattr(user, key, default)


def _data_to_dict(data: Any) -> dict[str, Any]:
    """把 Pydantic model / dict 统一转成 dict."""
    if hasattr(data, "model_dump"):
        return data.model_dump(exclude_unset=True)
    if isinstance(data, dict):
        return dict(data)
    return {}


__all__ = [
    "create_template",
    "delete_template",
    "get_template",
    "list_templates",
    "update_template",
]
