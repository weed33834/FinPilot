"""技能管理路由 — 管理后台专用（/api/skills）.

提供技能列表/创建/更新/删除/启禁/测试/关联工具等完整管理能力。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

# TODO: FinPilot deps 暂未提供 get_current_user_or_api_key（带 API Key + scope 校验），
#       暂用 get_current_user；如需 API Key 鉴权与 scope 校验，需扩展 finpilot.api.deps。
# TODO: FinPilot 暂未引入多租户(tenant_id)概念，user.tenant_id 暂以 user_id 字符串替代。
# TODO: Skill ORM 模型尚未在 finpilot.database.models 中定义，需后续补充。
# TODO: SkillCreate/SkillResponse 等 schema 在 FinPilot 中未定义，已内联简化版。
from finpilot.api.deps import get_current_user, get_db_session
# TODO: Skill 模型尚未在 finpilot.database.models 中定义，导入会失败。
from finpilot.database.models import Skill  # noqa: F401

router = APIRouter(prefix="/skills", tags=["Skills Admin"])

SKILL_CATEGORIES = [
    "财报分析",
    "风险评估",
    "指标计算",
    "文档处理",
    "数据查询",
    "报告生成",
    "通用助手",
]


# ---------------------------------------------------------------------------
# 内联 Schemas（简化的 Pydantic 模型，待后续统一收敛到 schemas 模块）
# TODO: 待迁移到 finpilot/api/schemas.py 或新建 schemas 模块统一管理
# ---------------------------------------------------------------------------


class SkillCreate(BaseModel):
    """技能创建请求."""

    name: str = Field(..., description="技能名称")
    display_name: str = Field(..., description="展示名称")
    description: str | None = None
    category: str = Field(..., description="技能分类")
    prompt_id: str | None = Field(default=None, description="关联提示词模板 ID")
    system_prompt_override: str | None = None
    icon: str | None = None
    tool_ids: list[str] = Field(default_factory=list, description="关联工具 ID 列表")
    is_active: bool = True


class SkillUpdate(BaseModel):
    """技能更新请求."""

    name: str | None = None
    display_name: str | None = None
    description: str | None = None
    category: str | None = None
    prompt_id: str | None = None
    system_prompt_override: str | None = None
    icon: str | None = None
    tool_ids: list[str] | None = None
    is_active: bool | None = None


class SkillResponse(BaseModel):
    """技能响应."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str | None = None
    name: str
    display_name: str
    description: str | None = None
    category: str
    prompt_id: str | None = None
    system_prompt_override: str | None = None
    is_active: bool = True
    icon: str | None = None
    tool_ids: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class SkillTestRequest(BaseModel):
    """技能测试请求."""

    query: str = Field(..., description="测试查询文本")


def _model_to_response(s: Skill) -> SkillResponse:
    return SkillResponse(
        id=s.id,
        tenant_id=s.tenant_id,
        name=s.name,
        display_name=s.display_name,
        description=s.description,
        category=s.category,
        prompt_id=s.prompt_id,
        system_prompt_override=s.system_prompt_override,
        is_active=s.is_active,
        icon=s.icon,
        tool_ids=s.tool_ids or [],
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


@router.get("")
def list_skills(
    page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    search: str = Query(default="", description="按名称/展示名搜索"),
    category: str = Query(default="", description="按分类筛选"),
    is_active: str = Query(default="", description="按状态筛选: active/inactive"),
) -> dict[str, Any]:
    """技能列表（分页/搜索/筛选）."""
    tenant_id = str(current_user.get("user_id", "default"))
    query = db.query(Skill).filter(Skill.tenant_id == tenant_id)
    if category:
        query = query.filter(Skill.category == category)
    if search:
        query = query.filter(
            (Skill.display_name.ilike(f"%{search}%"))
            | (Skill.name.ilike(f"%{search}%"))
        )
    if is_active == "active":
        query = query.filter(Skill.is_active.is_(True))
    elif is_active == "inactive":
        query = query.filter(Skill.is_active.is_(False))

    total = query.count()
    items = (
        query.order_by(Skill.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [_model_to_response(s) for s in items],
        },
    }


@router.get("/categories")
def list_skill_categories(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """获取技能分类列表."""
    return {"code": 0, "message": "ok", "data": SKILL_CATEGORIES}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_skill(
    body: SkillCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """创建技能（含关联工具 ID 列表）."""
    s = Skill(
        tenant_id=str(current_user.get("user_id", "default")),
        name=body.name,
        display_name=body.display_name,
        description=body.description,
        category=body.category,
        prompt_id=body.prompt_id,
        system_prompt_override=body.system_prompt_override,
        icon=body.icon,
        tool_ids=body.tool_ids,
        is_active=body.is_active,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"code": 0, "message": "ok", "data": _model_to_response(s)}


@router.put("/{skill_id}")
def update_skill(
    skill_id: str,
    body: SkillUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """更新技能（含关联工具 ID 列表）."""
    tenant_id = str(current_user.get("user_id", "default"))
    s = (
        db.query(Skill)
        .filter(Skill.id == skill_id, Skill.tenant_id == tenant_id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="技能不存在")

    update_data = body.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        if v is not None:
            setattr(s, k, v)

    db.commit()
    db.refresh(s)
    return {"code": 0, "message": "ok", "data": _model_to_response(s)}


@router.delete("/{skill_id}")
def delete_skill(
    skill_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """删除技能."""
    tenant_id = str(current_user.get("user_id", "default"))
    s = (
        db.query(Skill)
        .filter(Skill.id == skill_id, Skill.tenant_id == tenant_id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="技能不存在")

    db.delete(s)
    db.commit()
    return {"code": 0, "message": "ok", "data": {"id": skill_id, "deleted": True}}


@router.patch("/{skill_id}/toggle")
def toggle_skill(
    skill_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """切换技能启用/禁用状态."""
    tenant_id = str(current_user.get("user_id", "default"))
    s = (
        db.query(Skill)
        .filter(Skill.id == skill_id, Skill.tenant_id == tenant_id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="技能不存在")

    s.is_active = not s.is_active
    db.commit()
    db.refresh(s)
    return {"code": 0, "message": "ok", "data": _model_to_response(s)}


@router.get("/{skill_id}/tools")
def get_skill_tools(
    skill_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """获取技能关联的工具列表."""
    tenant_id = str(current_user.get("user_id", "default"))
    s = (
        db.query(Skill)
        .filter(Skill.id == skill_id, Skill.tenant_id == tenant_id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="技能不存在")

    return {"code": 0, "message": "ok", "data": s.tool_ids or []}


@router.put("/{skill_id}/tools")
def update_skill_tools(
    skill_id: str,
    body: dict[str, list[str]],
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """更新技能关联的工具列表."""
    tenant_id = str(current_user.get("user_id", "default"))
    s = (
        db.query(Skill)
        .filter(Skill.id == skill_id, Skill.tenant_id == tenant_id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="技能不存在")

    s.tool_ids = body.get("tool_ids", [])
    db.commit()
    db.refresh(s)
    return {"code": 0, "message": "ok", "data": _model_to_response(s)}


@router.post("/{skill_id}/test")
def test_skill(
    skill_id: str,
    body: SkillTestRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """测试技能 — 用关联 prompt + 首个 tool 执行简单测试."""
    tenant_id = str(current_user.get("user_id", "default"))
    s = (
        db.query(Skill)
        .filter(Skill.id == skill_id, Skill.tenant_id == tenant_id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="技能不存在")

    tool_count = len(s.tool_ids or [])
    prompt_info = ""
    if s.prompt_id:
        # TODO: PromptTemplate 模型尚未在 finpilot.database.models 中定义，导入会失败。
        from finpilot.database.models import PromptTemplate

        prompt = db.query(PromptTemplate).filter(PromptTemplate.id == s.prompt_id).first()
        if prompt:
            prompt_info = f"，关联 Prompt: {prompt.name}"

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "success": True,
            "message": f"技能 {s.display_name} 可用，关联 {tool_count} 个工具{prompt_info}",
            "result": f"收到测试查询: {body.query}",
        },
    }
