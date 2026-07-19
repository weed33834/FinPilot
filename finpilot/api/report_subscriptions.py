"""报告订阅管理路由."""

import contextlib
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

# TODO: FinPilot deps 暂未提供 get_current_user_or_api_key（带 API Key + scope 校验），
#       暂用 get_current_user / require_admin；如需 API Key 鉴权与 scope 校验，需扩展 finpilot.api.deps。
# TODO: FinPilot 暂未引入多租户(tenant_id)概念，user.tenant_id 暂以 user_id 字符串替代。
# TODO: ReportSubscription ORM 模型尚未在 finpilot.database.models 中定义，需后续补充。
# TODO: subscription_service 与 audit_service 服务尚未在 finpilot.services 中实现，需后续补充。
#       当前导入语句保留以便后续接入；运行时会因 ImportError 而失败。
from finpilot.api.deps import get_current_user, get_db_session, require_admin
# TODO: ReportSubscription 模型尚未在 finpilot.database.models 中定义，导入会失败。
from finpilot.database.models import ReportSubscription  # noqa: F401

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/report-subscriptions", tags=["Report Subscriptions"])


# ---------------------------------------------------------------------------
# 内联 Schemas（简化的 Pydantic 模型，待后续统一收敛到 schemas 模块）
# TODO: 待迁移到 finpilot/api/schemas.py 或新建 schemas 模块统一管理
# ---------------------------------------------------------------------------


class ReportSubscriptionCreate(BaseModel):
    """报告订阅创建请求."""

    name: str = Field(..., description="订阅名称")
    template_id: str | None = Field(default=None, description="关联模板 ID")
    schedule_cron: str | None = Field(default=None, description="调度 cron 表达式")
    is_active: bool = True
    config: dict[str, Any] = Field(default_factory=dict, description="订阅配置")


class ReportSubscriptionUpdate(BaseModel):
    """报告订阅更新请求."""

    name: str | None = None
    template_id: str | None = None
    schedule_cron: str | None = None
    is_active: bool | None = None
    config: dict[str, Any] | None = None


class ReportSubscriptionResponse(BaseModel):
    """报告订阅响应."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    template_id: str | None = None
    schedule_cron: str | None = None
    is_active: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
    last_run_at: str | None = None
    last_report_id: str | None = None
    last_error: str | None = None


class ReportSubscriptionRunResponse(BaseModel):
    """报告订阅执行响应."""

    subscription_id: str
    report_id: str | None = None
    status: str
    error: str | None = None


def _to_response(sub: ReportSubscription) -> dict[str, Any]:
    """将 ReportSubscription ORM 对象转为响应字典."""
    return ReportSubscriptionResponse.model_validate(sub).model_dump()


@router.post("", status_code=status.HTTP_201_CREATED)
def create_subscription_api(
    data: ReportSubscriptionCreate,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
) -> dict[str, Any]:
    """创建报告订阅."""
    # TODO: 待 finpilot.services.subscription_service 实现后接入。
    from finpilot.services.subscription_service import create_subscription

    sub = create_subscription(
        db=db,
        tenant_id=str(current_user.get("user_id", "default")),
        user=current_user,
        data=data,
    )
    return {"code": 0, "message": "ok", "data": _to_response(sub)}


@router.get("")
def list_subscriptions_api(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
    page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    active_only: bool = Query(default=False, description="仅返回启用的订阅"),
) -> dict[str, Any]:
    """查询当前租户的订阅列表."""
    # TODO: 待 finpilot.services.subscription_service 实现后接入。
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
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """获取单个订阅."""
    # TODO: 待 finpilot.services.subscription_service 实现后接入。
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
    current_user: dict = Depends(require_admin),
) -> dict[str, Any]:
    """更新订阅."""
    # TODO: 待 finpilot.services.subscription_service 实现后接入。
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
    updated = update_subscription(db=db, sub=sub, data=data, user=current_user)
    return {"code": 0, "message": "ok", "data": _to_response(updated)}


@router.delete("/{subscription_id}")
def delete_subscription_api(
    subscription_id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
) -> dict[str, Any]:
    """删除订阅."""
    # TODO: 待 finpilot.services.subscription_service 实现后接入。
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
    delete_subscription(db=db, sub=sub, user=current_user)
    return {"code": 0, "message": "ok", "data": {"id": subscription_id, "deleted": True}}


@router.post("/{subscription_id}/run")
def run_subscription_api(
    subscription_id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
) -> dict[str, Any]:
    """手动触发订阅执行（不改变 next_run_at，但更新 last_run_at）."""
    # TODO: 待 finpilot.services.subscription_service 与 audit_service 实现后接入。
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
                resource=f"report_subscription://{sub.id}",
                user=current_user,
                reason=f"report_id={outcome['report_id']}",
                result="success",
            )
        except ImportError:
            logger.warning("audit_service 未实现，跳过审计日志")
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
        logger.warning(
            "report_subscription.run_failed subscription_id=%s error=%s",
            sub.id,
            exc,
        )
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
                resource=f"report_subscription://{sub.id}",
                user=current_user,
                reason="run_failed",
                result="fail",
            )
        except ImportError:
            logger.warning("audit_service 未实现，跳过审计日志")
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
