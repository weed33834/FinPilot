"""评估管理路由 — NL2SQL / RAG 系统评估统计与记录.

对应前端：EvalManagement.tsx，调用 /eval 前缀。
提供 stats / records / delete 端点。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from finpilot.api.deps import get_current_user, get_db_session
from finpilot.database.models import EvalRecord

router = APIRouter(prefix="/eval", tags=["Eval Management"])


def _to_response(r: EvalRecord) -> dict[str, Any]:
    """ORM 对象转响应字典（字段与前端 interface EvalRecord 对齐）."""
    return {
        "id": str(r.id),
        "question": r.question,
        "eval_type": r.eval_type,
        "score": r.score,
        "eval_method": r.eval_method or "",
        "created_at": r.created_at.isoformat(sep=" ") if r.created_at else "",
        "metrics": r.metrics,
    }


def _compute_stats(db: Session, tenant_id: str) -> dict[str, Any]:
    """聚合评估统计：nl2sql / rag 分别的 count/avg_score 与附加指标."""
    base_q = db.query(EvalRecord).filter(EvalRecord.tenant_id == tenant_id)

    def _agg(eval_type: str) -> dict[str, Any]:
        q = base_q.filter(EvalRecord.eval_type == eval_type)
        try:
            count = q.count()
            avg_score = q.with_only(func.avg(EvalRecord.score)).scalar() or 0.0
            avg_latency = 0.0
            sql_valid_rate = 0.0
            avg_mrr = 0.0
            avg_ndcg = 0.0
            avg_hit_rate = 0.0
            # 从 metrics JSON 聚合附加指标（best-effort）
            records = q.all()
            latencies: list[float] = []
            sql_valids: list[float] = []
            mrrs: list[float] = []
            ndcgs: list[float] = []
            hit_rates: list[float] = []
            for rec in records:
                m = rec.metrics or {}
                if isinstance(m, dict):
                    if "latency_ms" in m:
                        try:
                            latencies.append(float(m["latency_ms"]))
                        except (TypeError, ValueError):
                            pass
                    if "sql_valid" in m:
                        try:
                            sql_valids.append(1.0 if bool(m["sql_valid"]) else 0.0)
                        except (TypeError, ValueError):
                            pass
                    if "mrr" in m:
                        try:
                            mrrs.append(float(m["mrr"]))
                        except (TypeError, ValueError):
                            pass
                    if "ndcg" in m:
                        try:
                            ndcgs.append(float(m["ndcg"]))
                        except (TypeError, ValueError):
                            pass
                    if "hit_rate" in m:
                        try:
                            hit_rates.append(float(m["hit_rate"]))
                        except (TypeError, ValueError):
                            pass
            if latencies:
                avg_latency = sum(latencies) / len(latencies)
            if sql_valids:
                sql_valid_rate = sum(sql_valids) / len(sql_valids)
            if mrrs:
                avg_mrr = sum(mrrs) / len(mrrs)
            if ndcgs:
                avg_ndcg = sum(ndcgs) / len(ndcgs)
            if hit_rates:
                avg_hit_rate = sum(hit_rates) / len(hit_rates)
        except Exception:  # noqa: BLE001
            count = 0
            avg_score = avg_latency = sql_valid_rate = avg_mrr = avg_ndcg = avg_hit_rate = 0.0

        return {
            "count": count,
            "avg_score": float(avg_score),
            "avg_latency_ms": float(avg_latency),
            "sql_valid_rate": float(sql_valid_rate),
            "avg_mrr": float(avg_mrr),
            "avg_ndcg": float(avg_ndcg),
            "avg_hit_rate": float(avg_hit_rate),
        }

    nl2sql = _agg("nl2sql")
    rag = _agg("rag")
    total = nl2sql["count"] + rag["count"]
    return {"total": total, "nl2sql": nl2sql, "rag": rag}


@router.get("/stats")
def eval_stats(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """获取评估统计（nl2sql / rag 分别的 count/avg_score 与附加指标）."""
    tenant_id = f"user_{current_user.get('user_id', 'default')}"
    try:
        stats = _compute_stats(db, tenant_id)
    except Exception:  # noqa: BLE001
        stats = {
            "total": 0,
            "nl2sql": {"count": 0, "avg_score": 0.0, "avg_latency_ms": 0.0, "sql_valid_rate": 0.0, "avg_mrr": 0.0, "avg_ndcg": 0.0, "avg_hit_rate": 0.0},
            "rag": {"count": 0, "avg_score": 0.0, "avg_latency_ms": 0.0, "sql_valid_rate": 0.0, "avg_mrr": 0.0, "avg_ndcg": 0.0, "avg_hit_rate": 0.0},
        }
    return {"code": 0, "message": "ok", "data": stats}


@router.get("/records")
def list_eval_records(
    eval_type: str = Query(default="", description="按评估类型筛选: nl2sql/rag"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """列出评估记录（分页 + 类型筛选）."""
    tenant_id = f"user_{current_user.get('user_id', 'default')}"
    q = db.query(EvalRecord).filter(EvalRecord.tenant_id == tenant_id)
    if eval_type:
        q = q.filter(EvalRecord.eval_type == eval_type)

    total = q.count()
    items = (
        q.order_by(EvalRecord.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "items": [_to_response(r) for r in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.post("/records", status_code=status.HTTP_201_CREATED)
def create_eval_record(
    payload: dict,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """创建评估记录（供评估管线写入结果）."""
    eval_type = (payload.get("eval_type") or "").strip().lower()
    if eval_type not in {"nl2sql", "rag"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="eval_type 无效，支持 nl2sql/rag",
        )
    question = (payload.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="question 不能为空")

    tenant_id = f"user_{current_user.get('user_id', 'default')}"
    r = EvalRecord(
        tenant_id=tenant_id,
        eval_type=eval_type,
        question=question,
        eval_method=payload.get("eval_method"),
        score=float(payload.get("score", 0.0)),
        metrics=payload.get("metrics"),
        detail=payload.get("detail"),
        created_by=str(current_user.get("user_id", "")),
    )
    db.add(r)
    try:
        db.commit()
        db.refresh(r)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"创建失败: {exc}"
        ) from exc
    return {"code": 0, "message": "ok", "data": _to_response(r)}


@router.delete("/records/{record_id}", status_code=status.HTTP_200_OK)
def delete_eval_record(
    record_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """删除评估记录."""
    r = db.get(EvalRecord, record_id)
    if not r:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="评估记录不存在")

    tenant_id = f"user_{current_user.get('user_id', 'default')}"
    if r.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作他人记录")

    try:
        db.delete(r)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"删除失败: {exc}"
        ) from exc

    return {"code": 0, "message": "ok", "data": {"id": str(record_id), "deleted": True}}
