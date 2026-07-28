"""提示词 Few-shot 示例路由 — 管理按 prompt_key 分组的示例样本.

对应前端：promptDeep.ts，调用 /prompt-few-shot 前缀。
基于 FewShotExample 模型。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from finpilot.api.deps import get_current_user, get_db_session
from finpilot.database.models import FewShotExample

router = APIRouter(prefix="/prompt-few-shot", tags=["Prompt Few-shot"])


def _to_response(e: FewShotExample) -> dict[str, Any]:
    """ORM 对象转响应字典（字段与前端 interface FewShotExample 对齐）."""
    return {
        "id": str(e.id),
        "tenant_id": e.tenant_id or "",
        "prompt_key": e.prompt_key,
        "input_text": e.input_text,
        "output_text": e.output_text,
        "category": e.category,
        "quality_score": e.quality_score,
        "is_active": bool(e.is_active),
        "display_order": e.display_order,
        "created_at": e.created_at.isoformat(sep=" ") if e.created_at else None,
    }


@router.get("/reorder")
def _reorder_get() -> dict[str, Any]:
    """占位：避免 GET /reorder 被误匹配为 /{exampleId}（GET 仅支持 POST reorder）."""
    return {"code": 0, "message": "ok", "data": {"hint": "请使用 POST /prompt-few-shot/reorder 重新排序"}}


@router.get("/{prompt_key}")
def list_few_shot(
    prompt_key: str,
    is_active: str = Query(default="", description="按启用状态筛选: true/false"),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """列出指定 prompt_key 的 few-shot 示例.

    注意：/{prompt_key} 需在 /reorder 之外定义，但 FastAPI 会按定义顺序匹配，
    因此上面的 _reorder_get 占位路由必须放在本路由之前以避免被吞。
    """
    tenant_id = f"user_{current_user.get('user_id', 'default')}"
    q = db.query(FewShotExample).filter(
        FewShotExample.tenant_id == tenant_id,
        FewShotExample.prompt_key == prompt_key,
    )
    if is_active == "true":
        q = q.filter(FewShotExample.is_active.is_(True))
    elif is_active == "false":
        q = q.filter(FewShotExample.is_active.is_(False))

    items = q.order_by(FewShotExample.display_order.asc(), FewShotExample.quality_score.desc()).all()
    return {"code": 0, "message": "ok", "data": [_to_response(e) for e in items]}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_few_shot(
    payload: dict,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """创建 few-shot 示例."""
    prompt_key = (payload.get("prompt_key") or "").strip()
    if not prompt_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="prompt_key 不能为空")
    input_text = (payload.get("input_text") or "").strip()
    if not input_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="input_text 不能为空")
    output_text = (payload.get("output_text") or "").strip()
    if not output_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="output_text 不能为空")

    tenant_id = f"user_{current_user.get('user_id', 'default')}"
    e = FewShotExample(
        tenant_id=tenant_id,
        prompt_key=prompt_key,
        input_text=input_text,
        output_text=output_text,
        category=payload.get("category"),
        quality_score=float(payload.get("quality_score", 0.5)),
        is_active=bool(payload.get("is_active", True)),
        display_order=int(payload.get("display_order", 0)),
    )
    db.add(e)
    try:
        db.commit()
        db.refresh(e)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"创建失败: {exc}"
        ) from exc
    return {"code": 0, "message": "ok", "data": _to_response(e)}


@router.put("/{example_id}")
def update_few_shot(
    example_id: int,
    payload: dict,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """更新 few-shot 示例（支持部分更新）."""
    e = db.get(FewShotExample, example_id)
    if not e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="示例不存在")

    for field in ("prompt_key", "input_text", "output_text", "category"):
        if field in payload and payload[field] is not None:
            setattr(e, field, payload[field])
    if "quality_score" in payload and payload["quality_score"] is not None:
        e.quality_score = float(payload["quality_score"])
    if "is_active" in payload and payload["is_active"] is not None:
        e.is_active = bool(payload["is_active"])
    if "display_order" in payload and payload["display_order"] is not None:
        e.display_order = int(payload["display_order"])

    try:
        db.commit()
        db.refresh(e)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"更新失败: {exc}"
        ) from exc
    return {"code": 0, "message": "ok", "data": _to_response(e)}


@router.delete("/{example_id}", status_code=status.HTTP_200_OK)
def delete_few_shot(
    example_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """删除 few-shot 示例."""
    e = db.get(FewShotExample, example_id)
    if not e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="示例不存在")
    try:
        db.delete(e)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"删除失败: {exc}"
        ) from exc
    return {"code": 0, "message": "ok", "data": None}


@router.post("/reorder")
def reorder_few_shot(
    payload: dict,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """按给定顺序重新排序指定 prompt_key 的 few-shot 示例."""
    prompt_key = (payload.get("prompt_key") or "").strip()
    if not prompt_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="prompt_key 不能为空")
    example_ids = payload.get("example_ids") or []
    if not isinstance(example_ids, list) or not example_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="example_ids 必须为非空数组",
        )

    tenant_id = f"user_{current_user.get('user_id', 'default')}"
    # 转为 int
    try:
        id_list = [int(eid) for eid in example_ids]
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="example_ids 包含无效 ID"
        )

    for order, eid in enumerate(id_list):
        e = db.get(FewShotExample, eid)
        if e and e.tenant_id == tenant_id and e.prompt_key == prompt_key:
            e.display_order = order
    try:
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"排序失败: {exc}"
        ) from exc

    items = (
        db.query(FewShotExample)
        .filter(
            FewShotExample.tenant_id == tenant_id,
            FewShotExample.prompt_key == prompt_key,
        )
        .order_by(FewShotExample.display_order.asc())
        .all()
    )
    return {"code": 0, "message": "ok", "data": [_to_response(e) for e in items]}
