"""提示词 A/B 测试路由 — 管理提示词变体对照实验.

对应前端：promptDeep.ts，调用 /prompt-ab-tests 前缀。
基于 PromptABTest / PromptABTestResult 模型。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from finpilot.api.deps import get_current_user, get_db_session
from finpilot.database.models import PromptABTest, PromptABTestResult, PromptTemplate

router = APIRouter(prefix="/prompt-ab-tests", tags=["Prompt AB Tests"])


def _to_response(t: PromptABTest) -> dict[str, Any]:
    """ORM 对象转响应字典（字段与前端 interface ABTestItem 对齐）."""
    return {
        "id": str(t.id),
        "tenant_id": t.tenant_id or "",
        "name": t.name,
        "prompt_key": t.prompt_key,
        "variant_a_id": str(t.variant_a_id) if t.variant_a_id is not None else "",
        "variant_b_id": str(t.variant_b_id) if t.variant_b_id is not None else "",
        "traffic_split_b": t.traffic_split_b,
        "status": t.status,
        "start_time": t.start_time.isoformat(sep=" ") if t.start_time else None,
        "end_time": t.end_time.isoformat(sep=" ") if t.end_time else None,
        "winner": t.winner,
        "created_at": t.created_at.isoformat(sep=" ") if t.created_at else None,
        "updated_at": t.updated_at.isoformat(sep=" ") if t.updated_at else None,
    }


def _validate_variants(db: Session, variant_a_id: int | None, variant_b_id: int | None) -> None:
    """校验变体模板存在."""
    for vid in (variant_a_id, variant_b_id):
        if vid is not None and not db.get(PromptTemplate, vid):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"变体模板不存在: {vid}",
            )


@router.get("")
def list_ab_tests(
    status_filter: str = Query(default="", alias="status", description="按状态筛选: draft/running/completed"),
    prompt_key: str = Query(default="", description="按 prompt_key 筛选"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """列出 A/B 测试（分页 + 状态/Key 筛选）."""
    tenant_id = f"user_{current_user.get('user_id', 'default')}"
    q = db.query(PromptABTest).filter(PromptABTest.tenant_id == tenant_id)
    if status_filter:
        q = q.filter(PromptABTest.status == status_filter)
    if prompt_key:
        q = q.filter(PromptABTest.prompt_key == prompt_key)

    total = q.count()
    items = (
        q.order_by(PromptABTest.created_at.desc())
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
            "items": [_to_response(t) for t in items],
        },
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_ab_test(
    payload: dict,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """创建 A/B 测试."""
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name 不能为空")
    prompt_key = (payload.get("prompt_key") or "").strip()
    if not prompt_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="prompt_key 不能为空")

    variant_a_id = payload.get("variant_a_id")
    variant_b_id = payload.get("variant_b_id")
    # 转 int（前端可能传字符串）
    try:
        variant_a_id = int(variant_a_id) if variant_a_id not in (None, "") else None
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="variant_a_id 无效")
    try:
        variant_b_id = int(variant_b_id) if variant_b_id not in (None, "") else None
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="variant_b_id 无效")

    _validate_variants(db, variant_a_id, variant_b_id)

    traffic_split_b = float(payload.get("traffic_split_b", 50.0))
    if not 0 <= traffic_split_b <= 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="traffic_split_b 需在 0-100 之间",
        )

    tenant_id = f"user_{current_user.get('user_id', 'default')}"
    t = PromptABTest(
        tenant_id=tenant_id,
        name=name,
        prompt_key=prompt_key,
        variant_a_id=variant_a_id,
        variant_b_id=variant_b_id,
        traffic_split_b=traffic_split_b,
        status="draft",
    )
    db.add(t)
    try:
        db.commit()
        db.refresh(t)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"创建失败: {exc}"
        ) from exc
    return {"code": 0, "message": "ok", "data": _to_response(t)}


@router.get("/{test_id}")
def get_ab_test(
    test_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """获取 A/B 测试详情."""
    t = db.get(PromptABTest, test_id)
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="A/B 测试不存在")
    return {"code": 0, "message": "ok", "data": _to_response(t)}


@router.post("/{test_id}/start")
def start_ab_test(
    test_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """启动 A/B 测试（draft → running）."""
    t = db.get(PromptABTest, test_id)
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="A/B 测试不存在")
    if t.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"仅 draft 状态可启动（当前: {t.status}）",
        )
    t.status = "running"
    t.start_time = datetime.now(UTC)
    try:
        db.commit()
        db.refresh(t)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"启动失败: {exc}"
        ) from exc
    return {"code": 0, "message": "ok", "data": _to_response(t)}


@router.post("/{test_id}/stop")
def stop_ab_test(
    test_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """停止 A/B 测试（running → completed）."""
    t = db.get(PromptABTest, test_id)
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="A/B 测试不存在")
    if t.status != "running":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"仅 running 状态可停止（当前: {t.status}）",
        )
    t.status = "completed"
    t.end_time = datetime.now(UTC)
    try:
        db.commit()
        db.refresh(t)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"停止失败: {exc}"
        ) from exc
    return {"code": 0, "message": "ok", "data": _to_response(t)}


@router.post("/{test_id}/feedback")
def submit_feedback(
    test_id: int,
    payload: dict,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """提交 A/B 测试单次反馈（命中变体 + 评分）."""
    t = db.get(PromptABTest, test_id)
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="A/B 测试不存在")

    variant = (payload.get("variant") or "").strip().lower()
    if variant not in {"a", "b"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="variant 无效，支持 a/b",
        )

    score = payload.get("score")
    try:
        score_val = float(score) if score is not None else None
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="score 无效")

    # 简单映射：thumbs_up → "thumbs_up"
    feedback = payload.get("feedback")
    result = PromptABTestResult(
        test_id=t.id,
        variant=variant,
        session_id=payload.get("session_id"),
        user_feedback=feedback,
        response_quality_score=score_val,
        latency_ms=int(payload.get("latency_ms", 0) or 0),
        token_count=int(payload.get("token_count", 0) or 0),
    )
    db.add(result)
    try:
        db.commit()
        db.refresh(result)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"提交反馈失败: {exc}"
        ) from exc
    return {"code": 0, "message": "ok", "data": {"id": str(result.id), "recorded": True}}


@router.get("/{test_id}/results")
def get_ab_test_results(
    test_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """聚合 A/B 测试结果（按变体统计 count/avg_score/avg_latency/反馈分布）."""
    t = db.get(PromptABTest, test_id)
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="A/B 测试不存在")

    results = db.query(PromptABTestResult).filter(PromptABTestResult.test_id == test_id).all()

    def _agg(variant: str) -> dict[str, Any]:
        rs = [r for r in results if r.variant == variant]
        count = len(rs)
        scores = [r.response_quality_score for r in rs if r.response_quality_score is not None]
        latencies = [r.latency_ms for r in rs if r.latency_ms]
        tokens = [r.token_count for r in rs if r.token_count]
        thumbs_up = sum(1 for r in rs if r.user_feedback == "thumbs_up")
        thumbs_down = sum(1 for r in rs if r.user_feedback == "thumbs_down")
        return {
            "count": count,
            "avg_score": sum(scores) / len(scores) if scores else 0.0,
            "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
            "avg_token_count": sum(tokens) / len(tokens) if tokens else 0.0,
            "thumbs_up": thumbs_up,
            "thumbs_down": thumbs_down,
        }

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "test_id": str(test_id),
            "status": t.status,
            "variant_a": _agg("a"),
            "variant_b": _agg("b"),
            "total_records": len(results),
        },
    }


@router.delete("/{test_id}", status_code=status.HTTP_200_OK)
def delete_ab_test(
    test_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """删除 A/B 测试（级联删除结果记录）."""
    t = db.get(PromptABTest, test_id)
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="A/B 测试不存在")
    try:
        db.delete(t)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"删除失败: {exc}"
        ) from exc
    return {"code": 0, "message": "ok", "data": {"id": str(test_id), "deleted": True}}
