# -*- coding: utf-8 -*-
"""报告审批路由（管理员/审计员）。

响应统一包裹为 ``{code, message, data}`` 格式。

- GET    /              列出审批历史记录（来自独立 approvals 表）
- POST   /{id}/action   对报告执行审批动作（approve/reject/modify）

前端 ApprovalsPage.tsx 期望：
- GET /approvals?limit=50 返回 ApprovalRecord[]：
  { id, report_id, reviewer_id, action, comments, created_at }
- POST /approvals/{reportId}/action { action, comments? } 将报告状态推进

因果链：每次审批动作落一条 Approval 记录（持久化审批人/意见/前后状态），
同时推进 Report.status，建立 报告生成→审批→发布 的完整可追溯链条。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from finpilot.database.models import Approval, Report

from .deps import get_db_session, require_admin, tenant_of

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _ok(data: Any, message: str = "success") -> dict:
    return {"code": 0, "message": message, "data": data}


# 审批动作 -> 目标 Report.status
_ACTION_TO_STATUS = {
    "approve": "approved",
    "reject": "rejected",
    "modify": "draft",  # 退回修改
}
_ACTION_LABEL = {"approve": "通过", "reject": "驳回", "modify": "退回修改"}


@router.get("")
def list_approvals(
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """列出审批历史记录。

    返回 ApprovalRecord[]，按 created_at 倒序。
    数据来源：独立 approvals 表（完整审批历史）。
    若 approvals 表为空（旧数据），回退到 Report 表中 status in (approved/rejected)。
    """
    rows = (
        db.query(Approval)
        .order_by(Approval.created_at.desc())
        .limit(limit)
        .all()
    )
    if rows:
        return _ok([
            {
                "id": str(r.id),
                "report_id": str(r.target_object_id)
                if r.target_object_type == "report" and r.report_id is None
                else (str(r.report_id) if r.report_id is not None else ""),
                "reviewer_id": str(r.reviewer_id) if r.reviewer_id is not None else "",
                "reviewer_name": r.reviewer_name or "",
                "action": r.action,
                "comments": r.comments,
                "prev_status": r.prev_status,
                "new_status": r.new_status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ])

    # 回退：旧数据从 Report 表推导
    final_statuses = ("approved", "rejected")
    reports = (
        db.query(Report)
        .filter(Report.status.in_(final_statuses))
        .order_by(Report.updated_at.desc().nullsfirst(), Report.created_at.desc())
        .limit(limit)
        .all()
    )
    return _ok([
        {
            "id": str(r.id),
            "report_id": str(r.id),
            "reviewer_id": str(r.created_by) if r.created_by is not None else "",
            "reviewer_name": "",
            "action": "approve" if r.status == "approved" else "reject",
            "comments": r.summary or None,
            "prev_status": None,
            "new_status": r.status,
            "created_at": (r.updated_at or r.created_at).isoformat()
            if (r.updated_at or r.created_at)
            else None,
        }
        for r in reports
    ])


@router.post("/{report_id}/action")
def approval_action(
    report_id: int,
    payload: dict,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """对报告执行审批动作。

    payload: { action: 'approve'|'reject'|'modify', comments?: string }

    实现：
    1. 落一条 Approval 记录（审批人/意见/前后状态）
    2. 推进 Report.status
    3. 审计埋点
    """
    action = (payload.get("action") or "").strip().lower()
    if action not in _ACTION_TO_STATUS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效动作: {action}，支持 approve/reject/modify",
        )
    # 带 tenant_id 过滤，防止跨租户审批他人报告（db.get 不触发 tenant_filter 事件）
    tenant_id = tenant_of(current_user)
    r = (
        db.query(Report)
        .filter(Report.id == report_id, Report.tenant_id == tenant_id)
        .first()
    )
    if not r:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在")

    prev_status = r.status
    new_status = _ACTION_TO_STATUS[action]
    comments = (payload.get("comments") or "").strip()

    reviewer_id = current_user.get("user_id")
    reviewer_name = (
        current_user.get("name")
        or current_user.get("email")
        or str(reviewer_id)
        if reviewer_id is not None
        else None
    )

    # 1. 落 Approval 记录
    approval = Approval(
        tenant_id=r.tenant_id,
        target_object_type="report",
        target_object_id=report_id,
        report_id=report_id,
        reviewer_id=reviewer_id,
        reviewer_name=reviewer_name,
        action=action,
        comments=comments or None,
        prev_status=prev_status,
        new_status=new_status,
    )
    db.add(approval)

    # 2. 推进 Report.status
    r.status = new_status
    if comments:
        prefix = (r.summary + "\n\n") if r.summary else ""
        r.summary = f"{prefix}[审批-{action}] {comments}"
    r.updated_at = datetime.utcnow()

    try:
        db.commit()
        db.refresh(r)
        db.refresh(approval)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"审批失败: {exc}"
        ) from exc

    # 3. 审计埋点（best-effort）
    try:
        from finpilot.services.audit_service import log_action

        log_action(
            db,
            action=f"report_{action}",
            resource=f"report:{r.id}",
            user=current_user,
            reason=comments or f"报告审批 {action}",
            commit=False,
            target_object_type="report",
            target_object_id=str(r.id),
            meta={
                "approval_id": approval.id,
                "prev_status": prev_status,
                "new_status": new_status,
            },
        )
    except Exception:  # noqa: BLE001
        pass

    # 4. 通知报告创建人：审批结果 + WebSocket 实时推送（best-effort）
    if r.created_by is not None:
        try:
            from .notifications import notify_user

            notify_user(
                db,
                f"user_{r.created_by}",
                channel="approval",
                title=f"报告审批{_ACTION_LABEL[action]}",
                content=(
                    f"《{r.title}》已{_ACTION_LABEL[action]}"
                    + (f"，意见：{comments}" if comments else "")
                ),
                tenant_id=r.tenant_id,
            )
        except Exception:  # noqa: BLE001
            pass

    return _ok({
        "report_id": str(r.id),
        "approval_id": str(approval.id),
        "status": r.status,
        "reviewer_id": str(reviewer_id) if reviewer_id is not None else "",
        "reviewer_name": reviewer_name or "",
        "action": action,
        "prev_status": prev_status,
        "new_status": new_status,
    }, f"已{_ACTION_LABEL[action]}")


@router.get("/{report_id}/history")
def approval_history(
    report_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
):
    """获取某报告的完整审批历史（按时间正序）。

    多租户隔离：即使管理员也只能查看本租户报告的审批历史，
    避免租户管理员越权读取其他租户数据。
    """
    tenant_id = tenant_of(current_user)
    r = db.query(Report).filter(Report.id == report_id, Report.tenant_id == tenant_id).first()
    if not r:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在")
    rows = (
        db.query(Approval)
        .filter(Approval.report_id == report_id)
        .order_by(Approval.created_at.asc())
        .all()
    )
    return _ok([
        {
            "id": str(a.id),
            "reviewer_id": str(a.reviewer_id) if a.reviewer_id is not None else "",
            "reviewer_name": a.reviewer_name or "",
            "action": a.action,
            "comments": a.comments,
            "prev_status": a.prev_status,
            "new_status": a.new_status,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in rows
    ])
