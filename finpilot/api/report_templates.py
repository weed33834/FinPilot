"""报告模板管理路由.

Schema 与前端 ``frontend/src/types/report.ts`` 中的 ``ReportTemplate`` 对齐：
- 字段：``id, tenant_id, name, report_type, sections, summary_template,
  title_template, created_by, is_active('Y'/'N'), created_at, updated_at``
- 列表/单查对所有登录用户开放；创建/更新/删除需要管理员权限。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from finpilot.api.deps import get_current_user, get_db_session, require_admin
from finpilot.database.models import ReportTemplate  # noqa: F401
from finpilot.services.template_service import (
    create_template,
    delete_template,
    get_template,
    list_templates,
    update_template,
)

router = APIRouter(prefix="/report-templates", tags=["ReportTemplates"])


# ---------------------------------------------------------------------------
# Schemas（与前端 types/report.ts 严格对齐）
# ---------------------------------------------------------------------------


class ReportTemplateSection(BaseModel):
    """模板 section 项：name + metric."""

    name: str
    metric: str


class ReportTemplateCreate(BaseModel):
    """模板创建请求."""

    name: str = Field(..., description="模板名称")
    report_type: str = Field(..., description="模板类型: profit/balance/cash/custom/comparison")
    sections: list[ReportTemplateSection] = Field(default_factory=list)
    summary_template: str = ""
    title_template: str = ""


class ReportTemplateUpdate(BaseModel):
    """模板更新请求（部分字段，is_active 用 'Y'/'N'）."""

    name: str | None = None
    sections: list[ReportTemplateSection] | None = None
    summary_template: str | None = None
    title_template: str | None = None
    is_active: str | None = Field(default=None, description="'Y' / 'N'")


class ReportTemplateResponse(BaseModel):
    """模板响应（与 ORM 一致，字段名对齐前端）."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str | None = None
    name: str
    report_type: str
    sections: list[dict[str, Any]] = Field(default_factory=list)
    summary_template: str = ""
    title_template: str = ""
    created_by: str | None = None
    is_active: str = "Y"
    created_at: str | None = None
    updated_at: str | None = None


def _to_response(t: ReportTemplate) -> dict[str, Any]:
    """ORM -> dict（与前端契约一致）."""
    return {
        "id": str(t.id),
        "tenant_id": t.tenant_id,
        "name": t.name,
        "report_type": t.report_type,
        "sections": t.sections or [],
        "summary_template": t.summary_template or "",
        "title_template": t.title_template or "",
        "created_by": str(t.created_by) if t.created_by is not None else None,
        "is_active": t.is_active or "Y",
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


@router.get("")
def list_templates_api(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
    page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    active_only: bool = Query(default=False, description="仅返回启用的模板"),
) -> dict[str, Any]:
    """查询当前租户的模板列表."""
    items, total = list_templates(
        db=db,
        tenant_id=str(current_user.get("user_id", "default")),
        page=page,
        page_size=page_size,
        active_only=active_only,
    )
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [_to_response(t) for t in items],
        },
    }


@router.get("/{template_id}")
def get_template_api(
    template_id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """获取单个模板."""
    template = get_template(
        db=db,
        template_id=template_id,
        tenant_id=str(current_user.get("user_id", "default")),
    )
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模板不存在")
    return {"code": 0, "message": "ok", "data": _to_response(template)}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_template_api(
    data: ReportTemplateCreate,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
) -> dict[str, Any]:
    """创建模板."""
    template = create_template(db=db, data=data, user=current_user)
    return {"code": 0, "message": "ok", "data": _to_response(template)}


@router.put("/{template_id}")
def update_template_api(
    template_id: str,
    data: ReportTemplateUpdate,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
) -> dict[str, Any]:
    """更新模板."""
    template = get_template(
        db=db,
        template_id=template_id,
        tenant_id=str(current_user.get("user_id", "default")),
    )
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模板不存在")
    updated = update_template(db=db, template=template, data=data, user=current_user)
    return {"code": 0, "message": "ok", "data": _to_response(updated)}


@router.delete("/{template_id}")
def delete_template_api(
    template_id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
) -> dict[str, Any]:
    """删除模板."""
    template = get_template(
        db=db,
        template_id=template_id,
        tenant_id=str(current_user.get("user_id", "default")),
    )
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模板不存在")
    delete_template(db=db, template=template, user=current_user)
    return {"code": 0, "message": "ok", "data": {"id": template_id, "deleted": True}}
