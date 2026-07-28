"""报告订阅管理路由."""

import contextlib
from datetime import UTC, datetime

from finpilot.core.logging import get_logger
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from finpilot.api.deps import require_scope, get_db_session
from finpilot.api.schemas import (
    ReportSubscriptionCreate,
    ReportSubscriptionResponse,
    ReportSubscriptionUpdate,
)
from finpilot.database.models import ReportSubscription, User

logger = get_logger(__name__)

router = APIRouter(prefix="/report-subscriptions", tags=["Report Subscriptions"])


def _resolve_user(db: Session, current_user: dict) -> User:
    """从 require_scope 返回的 dict 中解析 User ORM 对象."""
    user_id = current_user.get("user_id")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return user


def _to_response(sub: ReportSubscription) -> dict[str, Any]:
    """将 ReportSubscription ORM 对象转为响应字典."""
    return ReportSubscriptionResponse.model_validate(sub).model_dump()


@router.post("", status_code=status.HTTP_201_CREATED)
def create_subscription_api(
    data: ReportSubscriptionCreate,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_scope("report_subscriptions:admin")),
) -> dict[str, Any]:
    """创建报告订阅."""
    from finpilot.services.subscription_service import create_subscription

    user = _resolve_user(db, current_user)
    sub = create_subscription(
        db=db,
        tenant_id=current_user.get("tenant_id") or str(user.id),
        user=user,
        data=data,
    )
    return {"code": 0, "message": "ok", "data": _to_response(sub)}


@router.get("")
def list_subscriptions_api(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_scope("report_subscriptions:read")),
    page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    active_only: bool = Query(default=False, description="仅返回启用的订阅"),
) -> dict[str, Any]:
    """查询当前租户的订阅列表."""
    from finpilot.services.subscription_service import list_subscriptions

    items, total = list_subscriptions(
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
            "items": [_to_response(s) for s in items],
        },
    }


@router.get("/{subscription_id}")
def get_subscription_api(
    subscription_id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_scope("report_subscriptions:read")),
) -> dict[str, Any]:
    """获取单个订阅."""
    from finpilot.services.subscription_service import get_subscription

    sub = get_subscription(
        db=db,
        subscription_id=subscription_id,
        tenant_id=str(current_user.get("user_id", "default")),
    )
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订阅不存在")
    return {"code": 0, "message": "ok", "data": _to_response(sub)}


@router.put("/{subscription_id}")
def update_subscription_api(
    subscription_id: str,
    data: ReportSubscriptionUpdate,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_scope("report_subscriptions:admin")),
) -> dict[str, Any]:
    """更新订阅."""
    from finpilot.services.subscription_service import (
        get_subscription,
        update_subscription,
    )

    sub = get_subscription(
        db=db,
        subscription_id=subscription_id,
        tenant_id=str(current_user.get("user_id", "default")),
    )
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订阅不存在")
    user = _resolve_user(db, current_user)
    updated = update_subscription(db=db, sub=sub, data=data, user=user)
    return {"code": 0, "message": "ok", "data": _to_response(updated)}


@router.delete("/{subscription_id}")
def delete_subscription_api(
    subscription_id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_scope("report_subscriptions:admin")),
) -> dict[str, Any]:
    """删除订阅."""
    from finpilot.services.subscription_service import (
        delete_subscription,
        get_subscription,
    )

    sub = get_subscription(
        db=db,
        subscription_id=subscription_id,
        tenant_id=str(current_user.get("user_id", "default")),
    )
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订阅不存在")
    user = _resolve_user(db, current_user)
    delete_subscription(db=db, sub=sub, user=user)
    return {"code": 0, "message": "ok", "data": {"id": subscription_id, "deleted": True}}


@router.post("/{subscription_id}/run")
def run_subscription_api(
    subscription_id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_scope("report_subscriptions:admin")),
) -> dict[str, Any]:
    """手动触发订阅执行（不改变 next_run_at，但更新 last_run_at）."""
    from finpilot.services.subscription_service import (
        get_subscription,
        run_subscription_once,
    )

    sub = get_subscription(
        db=db,
        subscription_id=subscription_id,
        tenant_id=str(current_user.get("user_id", "default")),
    )
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订阅不存在")
    try:
        outcome = run_subscription_once(db=db, sub=sub, now=None)
        # 记录手动执行结果（不影响调度）。run_subscription_once 内部已提交
        # 报告，此处仅更新订阅状态。
        sub.last_run_at = datetime.now(UTC)
        sub.last_report_id = outcome["report_id"]
        sub.last_error = "; ".join(outcome["warnings"]) or None
        db.commit()
        db.refresh(sub)
        # M5：订阅手动执行成功审计。
        try:
            from finpilot.services.audit_service import log_action

            log_action(
                db=db,
                action="report_subscription.run",
                resource=f"report_subscription:{sub.id}",
                user=current_user,
                reason=f"report_id={outcome['report_id']}",
                commit=False,
                target_object_type="report_subscription",
                target_object_id=str(sub.id),
                meta={"result": "success", "report_id": outcome["report_id"]},
            )
        except Exception:  # noqa: BLE001
            logger.warning("audit_log_failed", subscription_id=sub.id)
        return {
            "code": 0,
            "message": "ok",
            "data": {
                "subscription_id": sub.id,
                "report_id": outcome["report_id"],
                "status": "success",
                "error": None,
            },
        }
    except Exception as exc:  # noqa: BLE001
        # 生成失败时不留半成品报告（run_subscription_once 未持久化 Report），
        # 仅记录失败状态。next_run_at 保持不变。
        logger.warning("report_subscription_run_failed", subscription_id=sub.id, error=str(exc))
        sub.last_run_at = datetime.now(UTC)
        sub.last_report_id = None
        sub.last_error = "订阅操作失败"
        with contextlib.suppress(Exception):
            db.commit()
        # M5：订阅手动执行失败审计。
        try:
            from finpilot.services.audit_service import log_action

            log_action(
                db=db,
                action="report_subscription.run",
                resource=f"report_subscription:{sub.id}",
                user=current_user,
                reason="run_failed",
                commit=False,
                target_object_type="report_subscription",
                target_object_id=str(sub.id),
                meta={"result": "failed", "error": str(exc)},
            )
        except Exception:  # noqa: BLE001
            logger.warning("audit_log_failed", subscription_id=sub.id)
        return {
            "code": 0,
            "message": "ok",
            "data": {
                "subscription_id": sub.id,
                "report_id": None,
                "status": "failed",
                "error": "订阅操作失败",
            },
        }
