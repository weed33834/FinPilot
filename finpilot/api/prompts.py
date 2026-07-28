"""提示词模板管理路由.

提供模板 CRUD、渲染、分类查询能力。
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from finpilot.api.deps import require_scope, get_db_session
from finpilot.api.schemas import (
    PromptAIGenerateRequest,
    PromptAIGenerateResponse,
    PromptEvaluateRequest,
    PromptImportRequest,
    PromptRenderRequest,
    PromptTemplateCreate,
    PromptTemplateResponse,
    PromptTemplateUpdate,
    PromptTestRequest,
)
from finpilot.database.models import PromptTemplate, PromptVersion

router = APIRouter(prefix="/prompts", tags=["Prompts"])


def _model_to_response(tpl: PromptTemplate) -> PromptTemplateResponse:
    """模型转响应.

    注意：ORM 模型中 id/created_by 为 int，created_at/updated_at 为 datetime，
    而 schema 期望字符串，这里显式做类型转换避免 Pydantic ValidationError。
    """
    import json
    from datetime import datetime as _dt

    variables: list[str] | None = None
    if tpl.variables:
        try:
            variables = json.loads(tpl.variables)
        except (json.JSONDecodeError, TypeError):
            variables = None

    def _to_str(value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, _dt):
            return value.isoformat(sep=" ")
        return str(value)

    return PromptTemplateResponse(
        id=str(tpl.id),
        tenant_id=tpl.tenant_id,
        name=tpl.name,
        description=tpl.description,
        template_type=tpl.template_type,
        content=tpl.content,
        variables=variables,
        is_system=tpl.is_system or False,
        is_active=getattr(tpl, "is_active", True),
        created_by=_to_str(tpl.created_by),
        created_at=_to_str(tpl.created_at),
        updated_at=_to_str(tpl.updated_at),
    )


@router.get("")
def list_prompts(
    page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    current_user: dict = Depends(require_scope("prompts:admin")),
    db: Session = Depends(get_db_session),
    template_type: str = Query(default="", description="按类型筛选"),
    search: str = Query(default="", description="按名称搜索"),
    is_active: str = Query(default="", description="按状态筛选: active/inactive/all"),
) -> dict[str, Any]:
    """获取提示词模板列表（分页/搜索/筛选）."""
    tenant_id = str(current_user.get("user_id", "default"))
    query = db.query(PromptTemplate).filter(
        PromptTemplate.tenant_id == tenant_id,
    )
    if template_type:
        query = query.filter(PromptTemplate.template_type == template_type)
    if search:
        query = query.filter(PromptTemplate.name.ilike(f"%{search}%"))
    if is_active == "active":
        query = query.filter(PromptTemplate.is_active.is_(True))
    elif is_active == "inactive":
        query = query.filter(PromptTemplate.is_active.is_(False))

    total = query.count()
    items = (
        query.order_by(PromptTemplate.updated_at.desc())
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
            "items": [_model_to_response(t) for t in items],
        },
    }


@router.get("/types")
def list_prompt_types(
    current_user: dict = Depends(require_scope("prompts:admin")),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """获取提示词模板类型列表."""
    tenant_id = str(current_user.get("user_id", "default"))
    rows = (
        db.query(PromptTemplate.template_type)
        .filter(PromptTemplate.tenant_id == tenant_id)
        .distinct()
        .all()
    )
    types = [r[0] for r in rows]
    return {"code": 0, "message": "ok", "data": sorted(types)}


# ---------------------------------------------------------------------------
# AI 自动生成提示词 + 导入 / 导出（外部资源）
# ⚠️ 必须声明在 /{template_id} 之前，否则 /export 会被 /{template_id="export"} 抢先匹配
# ---------------------------------------------------------------------------


_META_SYSTEM_PROMPT = """你是金融分析师智能体平台的提示词工程师。
根据用户的自然语言需求描述，生成一份高质量、可直接使用的 System Prompt 模板。

要求：
1. 输出必须是严格的 JSON，字段：name, description, content, variables
2. name：模板名称（不超过 30 字，中文）
3. description：一句话描述模板用途（不超过 60 字，中文）
4. content：完整的 System Prompt 正文，使用 {{变量名}} 形式的占位符标记可替换变量
5. variables：从 content 中提取的变量名列表（字符串数组，不含花括号）
6. 风格、语言按用户指定
7. 内容需贴合金融分析师场景（财报分析/估值/行业研究/风险审计等）
8. 严禁在 content 中包含示例用户输入或 assistant 回复

输出格式示例：
{"name":"财报摘要生成","description":"根据财报数据生成结构化摘要","content":"你是资深财报分析师...请基于以下财报数据生成摘要：\\n公司：{{company}}\\n期间：{{period}}\\n数据：{{financial_data}}","variables":["company","period","financial_data"]}
"""


@router.post("/ai-generate")
def ai_generate_prompt(
    body: PromptAIGenerateRequest,
    current_user: dict = Depends(require_scope("prompts:admin")),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """AI 自动生成提示词模板（meta-prompting）.

    调用默认 LLM，根据用户需求描述生成结构化提示词模板。
    返回字段：name / description / template_type / content / variables。
    生成失败时返回 503 + 错误详情。
    """
    import json

    from finpilot.llm.client import LLMClient
    from finpilot.llm.config import get_default_config

    config = get_default_config(db)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="未配置默认 LLM 供应商，无法调用 AI 生成。请先在「模型供应商管理」中配置并设为默认。",
        )

    user_prompt = (
        f"需求描述：{body.description}\n"
        f"目标分类：{body.template_type}\n"
        f"风格：{body.tone}\n"
        f"输出语言：{body.language}\n\n"
        f"请按要求的 JSON 格式输出。"
    )

    try:
        client = LLMClient(config=config)
        raw = client.chat(
            system_prompt=_META_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.4,
            max_tokens=1500,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LLM 调用失败：{exc}",
        ) from exc

    # 兼容模型包裹 ```json ... ``` 的情况，以及 JSON 后追加说明文字的情况
    text = raw.strip()
    if text.startswith("```"):
        # 去除首个 ```json 或 ``` 围栏
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
        if text.endswith("```"):
            text = text[:-3].strip()

    # 用 raw_decode 解析首个 JSON 对象，自动忽略后续说明文字
    # （模型有时在 JSON 后追加解释，导致 json.loads 报 "Extra data"）
    decoder = json.JSONDecoder()
    first_brace = text.find("{")
    parsed: dict[str, Any] | None = None
    if first_brace != -1:
        try:
            parsed, _end = decoder.raw_decode(text[first_brace:])
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"AI 返回内容无法解析为 JSON：{exc}",
            ) from exc
    else:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI 返回内容未找到 JSON 对象",
        )

    # 字段兜底
    name = str(parsed.get("name", "AI 生成模板")).strip()[:60] or "AI 生成模板"
    description = str(parsed.get("description", "")).strip()[:200]
    content = str(parsed.get("content", "")).strip()
    variables_raw = parsed.get("variables", []) or []
    variables = [str(v).strip() for v in variables_raw if str(v).strip()]
    if not content:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI 返回的 content 字段为空",
        )

    return {
        "code": 0,
        "message": "ok",
        "data": PromptAIGenerateResponse(
            name=name,
            description=description,
            template_type=body.template_type,
            content=content,
            variables=variables,
        ).model_dump(),
    }


@router.post("/import", status_code=status.HTTP_201_CREATED)
def import_prompts(
    body: PromptImportRequest,
    current_user: dict = Depends(require_scope("prompts:admin")),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """批量导入提示词模板（外部资源导入）.

    接受 JSON 数组，逐条创建模板。已存在同名模板时追加 "(导入)" 后缀避免冲突。
    返回：成功数 / 跳过数 / 失败详情列表。
    """
    import json

    from finpilot.services.prompt_loader import (
        _invalidate_cache as invalidate_prompt_cache,
    )

    tenant_id = str(current_user.get("user_id", "default"))
    created: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for idx, item in enumerate(body.items):
        try:
            existing = (
                db.query(PromptTemplate)
                .filter(
                    PromptTemplate.tenant_id == tenant_id,
                    PromptTemplate.name == item.name,
                )
                .first()
            )
            name = f"{item.name} (导入)" if existing else item.name

            variables_json = (
                json.dumps(item.variables, ensure_ascii=False) if item.variables else None
            )
            tpl = PromptTemplate(
                tenant_id=tenant_id,
                created_by=current_user.get("user_id"),
                name=name,
                description=item.description,
                template_type=item.template_type or "general",
                content=item.content,
                variables=variables_json,
                is_system=False,
                is_active=item.is_active,
            )
            db.add(tpl)
            db.flush()
            created.append({"id": tpl.id, "name": tpl.name})
        except Exception as exc:  # noqa: BLE001
            failed.append({"index": idx, "name": item.name, "error": str(exc)})

    if created:
        db.commit()
        invalidate_prompt_cache()

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "created_count": len(created),
            "failed_count": len(failed),
            "created": created,
            "failed": failed,
        },
    }


@router.get("/export")
def export_prompts(
    template_type: str = Query(default="", description="按类型筛选，空表示全部"),
    current_user: dict = Depends(require_scope("prompts:admin")),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """导出全部提示词模板为 JSON（外部资源导出 / 备份）.

    返回可直接保存为 .json 文件的结构，配合 /import 端点实现迁移。
    """
    tenant_id = str(current_user.get("user_id", "default"))
    query = db.query(PromptTemplate).filter(PromptTemplate.tenant_id == tenant_id)
    if template_type:
        query = query.filter(PromptTemplate.template_type == template_type)
    items = query.order_by(PromptTemplate.template_type, PromptTemplate.name).all()

    import json as _json

    payload = [
        {
            "name": tpl.name,
            "description": tpl.description,
            "template_type": tpl.template_type,
            "content": tpl.content,
            "variables": (
                _json.loads(tpl.variables)
                if tpl.variables
                else None
            ),
            "is_active": getattr(tpl, "is_active", True),
        }
        for tpl in items
    ]

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "version": "1.0",
            "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "count": len(payload),
            "items": payload,
        },
    }


@router.get("/{template_id}/versions")
def list_versions(
    template_id: str,
    current_user: dict = Depends(require_scope("prompts:admin")),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """列出指定模板的版本历史（按版本号降序）."""
    try:
        tid = int(template_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模板不存在")
    tpl = db.get(PromptTemplate, tid)
    if not tpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模板不存在")

    versions = (
        db.query(PromptVersion)
        .filter(PromptVersion.prompt_id == tid)
        .order_by(PromptVersion.version.desc())
        .all()
    )

    def _v_to_response(v: PromptVersion) -> dict[str, Any]:
        return {
            "id": str(v.id),
            "version": v.version,
            "content": v.content,
            "change_description": v.change_description,
            "is_active": bool(v.is_active_version),
            "created_by": str(v.created_by) if v.created_by is not None else None,
            "created_at": v.created_at.isoformat(sep=" ") if v.created_at else None,
        }

    return {"code": 0, "message": "ok", "data": [_v_to_response(v) for v in versions]}


@router.post("/{template_id}/versions", status_code=status.HTTP_201_CREATED)
def create_version(
    template_id: str,
    payload: dict,
    current_user: dict = Depends(require_scope("prompts:admin")),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """基于当前模板内容创建新版本快照."""
    try:
        tid = int(template_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模板不存在")
    tpl = db.get(PromptTemplate, tid)
    if not tpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模板不存在")

    content = (payload.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="content 不能为空")

    # 计算新版本号
    max_version = (
        db.query(PromptVersion)
        .filter(PromptVersion.prompt_id == tid)
        .order_by(PromptVersion.version.desc())
        .first()
    )
    next_version = (max_version.version + 1) if max_version else 1

    # 把旧的活动版本置为非活动
    if max_version and max_version.is_active_version:
        max_version.is_active_version = False

    v = PromptVersion(
        prompt_id=tid,
        version=next_version,
        content=content,
        variables=payload.get("variables"),
        change_description=payload.get("change_description"),
        created_by=current_user.get("user_id"),
        is_active_version=True,
    )
    db.add(v)
    # 同步更新模板当前内容
    tpl.content = content
    try:
        db.commit()
        db.refresh(v)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"创建版本失败: {exc}"
        ) from exc

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "id": str(v.id),
            "version": v.version,
            "content": v.content,
            "change_description": v.change_description,
            "is_active": bool(v.is_active_version),
            "created_by": str(v.created_by) if v.created_by is not None else None,
            "created_at": v.created_at.isoformat(sep=" ") if v.created_at else None,
        },
    }


@router.post("/{template_id}/versions/{version}/rollback")
def rollback_version(
    template_id: str,
    version: int,
    current_user: dict = Depends(require_scope("prompts:admin")),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """回滚到指定版本：把该版本内容设为模板当前内容，并标记为活动版本."""
    try:
        tid = int(template_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模板不存在")
    tpl = db.get(PromptTemplate, tid)
    if not tpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模板不存在")

    target = (
        db.query(PromptVersion)
        .filter(PromptVersion.prompt_id == tid, PromptVersion.version == version)
        .first()
    )
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"版本 v{version} 不存在",
        )

    # 取消其他活动版本
    db.query(PromptVersion).filter(
        PromptVersion.prompt_id == tid,
        PromptVersion.is_active_version.is_(True),
    ).update({PromptVersion.is_active_version: False})

    target.is_active_version = True
    tpl.content = target.content
    try:
        db.commit()
        db.refresh(tpl)
        db.refresh(target)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"回滚失败: {exc}"
        ) from exc

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "id": str(tpl.id),
            "name": tpl.name,
            "content": tpl.content,
            "rolled_back_to": version,
        },
    }


@router.get("/{template_id}/versions/{version}/diff")
def diff_version(
    template_id: str,
    version: int,
    current_user: dict = Depends(require_scope("prompts:admin")),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """对比指定版本与当前模板内容差异（逐行 diff）."""
    import difflib

    try:
        tid = int(template_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模板不存在")
    tpl = db.get(PromptTemplate, tid)
    if not tpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模板不存在")

    target = (
        db.query(PromptVersion)
        .filter(PromptVersion.prompt_id == tid, PromptVersion.version == version)
        .first()
    )
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"版本 v{version} 不存在",
        )

    current_lines = (tpl.content or "").splitlines(keepends=True)
    version_lines = (target.content or "").splitlines(keepends=True)
    diff = "".join(
        difflib.unified_diff(
            version_lines,
            current_lines,
            fromfile=f"v{version}",
            tofile="current",
            lineterm="",
        )
    )

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "version": version,
            "version_content": target.content,
            "current_content": tpl.content,
            "diff": diff,
        },
    }


@router.get("/{template_id}")
def get_prompt(
    template_id: str,
    current_user: dict = Depends(require_scope("prompts:admin")),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """获取单个提示词模板."""
    tenant_id = str(current_user.get("user_id", "default"))
    tpl = (
        db.query(PromptTemplate)
        .filter(
            PromptTemplate.id == template_id,
            PromptTemplate.tenant_id == tenant_id,
        )
        .first()
    )
    if not tpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模板不存在")

    return {"code": 0, "message": "ok", "data": _model_to_response(tpl)}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_prompt(
    body: PromptTemplateCreate,
    current_user: dict = Depends(require_scope("prompts:admin")),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """创建提示词模板."""
    import json

    from finpilot.services.prompt_loader import (
        _invalidate_cache as invalidate_prompt_cache,
    )

    variables_json: str | None = None
    if body.variables:
        variables_json = json.dumps(body.variables, ensure_ascii=False)

    tpl = PromptTemplate(
        tenant_id=str(current_user.get("user_id", "default")),
        created_by=current_user.get("user_id"),
        name=body.name,
        description=body.description,
        template_type=body.template_type,
        content=body.content,
        variables=variables_json,
    )
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    invalidate_prompt_cache()

    return {"code": 0, "message": "ok", "data": _model_to_response(tpl)}


@router.put("/{template_id}")
def update_prompt(
    template_id: str,
    body: PromptTemplateUpdate,
    current_user: dict = Depends(require_scope("prompts:admin")),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """更新提示词模板."""
    import json

    from finpilot.services.prompt_loader import (
        _invalidate_cache as invalidate_prompt_cache,
    )

    tenant_id = str(current_user.get("user_id", "default"))
    tpl = (
        db.query(PromptTemplate)
        .filter(
            PromptTemplate.id == template_id,
            PromptTemplate.tenant_id == tenant_id,
        )
        .first()
    )
    if not tpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模板不存在")

    if tpl.is_system:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="系统模板不可编辑")

    if body.name is not None:
        tpl.name = body.name
    if body.description is not None:
        tpl.description = body.description
    if body.template_type is not None:
        tpl.template_type = body.template_type
    if body.content is not None:
        tpl.content = body.content
    if body.variables is not None:
        tpl.variables = json.dumps(body.variables, ensure_ascii=False)

    db.commit()
    db.refresh(tpl)
    invalidate_prompt_cache()

    return {"code": 0, "message": "ok", "data": _model_to_response(tpl)}


@router.delete("/{template_id}")
def delete_prompt(
    template_id: str,
    current_user: dict = Depends(require_scope("prompts:admin")),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """删除提示词模板."""
    from finpilot.services.prompt_loader import (
        _invalidate_cache as invalidate_prompt_cache,
    )

    tenant_id = str(current_user.get("user_id", "default"))
    tpl = (
        db.query(PromptTemplate)
        .filter(
            PromptTemplate.id == template_id,
            PromptTemplate.tenant_id == tenant_id,
        )
        .first()
    )
    if not tpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模板不存在")
    if tpl.is_system:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="系统模板不可删除")

    db.delete(tpl)
    db.commit()
    invalidate_prompt_cache()

    return {"code": 0, "message": "ok", "data": None}


@router.put("/{template_id}/toggle")
def toggle_prompt(
    template_id: str,
    current_user: dict = Depends(require_scope("prompts:admin")),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """启用/禁用提示词模板."""
    from finpilot.services.prompt_loader import (
        _invalidate_cache as invalidate_prompt_cache,
    )

    tenant_id = str(current_user.get("user_id", "default"))
    tpl = (
        db.query(PromptTemplate)
        .filter(
            PromptTemplate.id == template_id,
            PromptTemplate.tenant_id == tenant_id,
        )
        .first()
    )
    if not tpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模板不存在")

    tpl.is_active = not getattr(tpl, "is_active", True)
    db.commit()
    db.refresh(tpl)
    invalidate_prompt_cache()

    return {"code": 0, "message": "ok", "data": _model_to_response(tpl)}


@router.post("/{template_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_prompt(
    template_id: str,
    current_user: dict = Depends(require_scope("prompts:admin")),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """复制提示词模板."""
    from finpilot.services.prompt_loader import (
        _invalidate_cache as invalidate_prompt_cache,
    )

    tenant_id = str(current_user.get("user_id", "default"))
    tpl = (
        db.query(PromptTemplate)
        .filter(
            PromptTemplate.id == template_id,
            PromptTemplate.tenant_id == tenant_id,
        )
        .first()
    )
    if not tpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模板不存在")

    new_tpl = PromptTemplate(
        tenant_id=tenant_id,
        created_by=current_user.get("user_id"),
        name=f"{tpl.name} (副本)",
        description=tpl.description,
        template_type=tpl.template_type,
        content=tpl.content,
        variables=tpl.variables,
        is_system=False,
        is_active=True,
    )
    db.add(new_tpl)
    db.commit()
    db.refresh(new_tpl)
    invalidate_prompt_cache()

    return {"code": 0, "message": "ok", "data": _model_to_response(new_tpl)}


@router.get("/categories/list")
def list_categories(
    current_user: dict = Depends(require_scope("prompts:admin")),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """获取所有提示词模板类型（分类）列表."""
    tenant_id = str(current_user.get("user_id", "default"))
    rows = (
        db.query(PromptTemplate.template_type)
        .filter(PromptTemplate.tenant_id == tenant_id)
        .distinct()
        .all()
    )
    categories = [r[0] for r in rows]
    return {"code": 0, "message": "ok", "data": sorted(categories)}


@router.post("/{template_id}/render")
def render_prompt_by_id(
    template_id: str,
    body: PromptRenderRequest,
    current_user: dict = Depends(require_scope("prompts:admin")),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """按模板 ID 渲染提示词（替换变量占位符）."""
    tenant_id = str(current_user.get("user_id", "default"))
    tpl = (
        db.query(PromptTemplate)
        .filter(
            PromptTemplate.id == template_id,
            PromptTemplate.tenant_id == tenant_id,
        )
        .first()
    )
    if not tpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模板不存在")

    rendered = tpl.content
    for key, val in body.variables.items():
        rendered = rendered.replace(f"{{{key}}}", val)

    return {
        "code": 0,
        "message": "ok",
        "data": {"rendered": rendered},
    }


@router.post("/render")
def render_prompt(
    body: PromptRenderRequest,
    current_user: dict = Depends(require_scope("prompts:admin")),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """渲染提示词模板（替换变量占位符）.

    支持两种模式：
    1. 按 template_id 从数据库加载模板
    2. 直接传入 content（不查数据库）
    """
    tenant_id = str(current_user.get("user_id", "default"))
    content: str
    if body.template_id:
        tpl = (
            db.query(PromptTemplate)
            .filter(
                PromptTemplate.id == body.template_id,
                PromptTemplate.tenant_id == tenant_id,
            )
            .first()
        )
        if not tpl:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模板不存在")
        content = tpl.content
    elif body.content:
        content = body.content
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请提供 template_id 或 content",
        )

    rendered = content
    for key, val in body.variables.items():
        rendered = rendered.replace(f"{{{key}}}", val)

    return {
        "code": 0,
        "message": "ok",
        "data": {"rendered": rendered},
    }


# ---------------------------------------------------------------------------
# 测试渲染 / 评估（使用高级引擎：条件渲染 + few-shot 注入 + 变量替换）
# ---------------------------------------------------------------------------


def _render_template_content(
    tpl: PromptTemplate,
    variables: dict[str, Any],
    current_user: dict,
    db: Session,
    include_few_shot: bool,
) -> str:
    """使用引擎渲染指定模板内容（条件 + few-shot + 变量）."""
    from finpilot.services.prompt_engine import (
        get_few_shot_examples,
        inject_few_shot,
        render_conditionals,
        substitute_variables,
    )

    tenant_id = str(current_user.get("user_id", "default"))
    rendered = render_conditionals(tpl.content, variables)
    if include_few_shot:
        examples = get_few_shot_examples(tpl.template_type, tenant_id, db)
        rendered = inject_few_shot(rendered, examples)
    rendered = substitute_variables(rendered, variables)
    return rendered


@router.post("/{template_id}/test")
def test_render_prompt(
    template_id: str,
    body: PromptTestRequest,
    current_user: dict = Depends(require_scope("prompts:admin")),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """用样例变量测试渲染提示词（支持条件模板与 few-shot 注入）."""
    tenant_id = str(current_user.get("user_id", "default"))
    tpl = (
        db.query(PromptTemplate)
        .filter(
            PromptTemplate.id == template_id,
            PromptTemplate.tenant_id == tenant_id,
        )
        .first()
    )
    if not tpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模板不存在")

    rendered = _render_template_content(tpl, body.variables, current_user, db, body.include_few_shot)
    return {
        "code": 0,
        "message": "ok",
        "data": {"rendered": rendered},
    }


@router.post("/{template_id}/evaluate")
def evaluate_prompt(
    template_id: str,
    body: PromptEvaluateRequest,
    current_user: dict = Depends(require_scope("prompts:admin")),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """对模板批量运行测试用例并评分.

    每个 test_case 字段:
      - variables: 渲染变量
      - expected: 期望渲染结果（可选）
      - match_type: exact / contains / llm_judge（默认 contains）
      - input: llm_judge 时的用户输入（可选）
    """
    from finpilot.services.prompt_engine import score_output

    tenant_id = str(current_user.get("user_id", "default"))
    tpl = (
        db.query(PromptTemplate)
        .filter(
            PromptTemplate.id == template_id,
            PromptTemplate.tenant_id == tenant_id,
        )
        .first()
    )
    if not tpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模板不存在")

    results: list[dict[str, Any]] = []
    total_score = 0.0
    total_latency = 0.0
    passed = 0

    for idx, tc in enumerate(body.test_cases):
        variables = tc.get("variables", {}) or {}
        expected = tc.get("expected")
        match_type = tc.get("match_type", "contains")
        user_input = tc.get("input", "")

        start = time.monotonic()
        try:
            rendered = _render_template_content(tpl, variables, current_user, db, body.include_few_shot)
            output = rendered
            if match_type == "llm_judge" and body.use_llm:
                try:
                    from finpilot.llm.client import LLMClient

                    client = LLMClient()
                    output = client.chat(system_prompt=rendered, user_prompt=user_input)
                except Exception:  # noqa: BLE001
                    output = rendered
            score = score_output(output, expected, match_type)
        except Exception:  # noqa: BLE001
            rendered = ""
            output = ""
            score = 0.0

        latency_ms = int((time.monotonic() - start) * 1000)
        total_score += score
        total_latency += latency_ms
        if score >= body.pass_threshold:
            passed += 1

        results.append({
            "case_index": idx,
            "rendered": rendered,
            "output": output,
            "expected": expected,
            "match_type": match_type,
            "score": round(score, 4),
            "latency_ms": latency_ms,
            "passed": score >= body.pass_threshold,
        })

    total = len(body.test_cases)
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "total": total,
            "passed": passed,
            "avg_score": round(total_score / total, 4) if total else 0.0,
            "avg_latency": int(total_latency / total) if total else 0,
            "results": results,
        },
    }
