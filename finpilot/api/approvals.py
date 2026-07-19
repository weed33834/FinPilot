# -*- coding: utf-8 -*-
"""报告审批路由（管理员/审计员）。

响应统一包裹为 ``{code, message, data}`` 格式。

- GET    /              列出审批历史记录
- POST   /{id}/action   对报告执行审批动作（approve/reject/modify）

前端 ApprovalsPage.tsx 期望：
- GET /approvals?limit=50 返回 ApprovalRecord[]：
  { id, report_id, reviewer_id, action, comments, created_at }
- POST /approvals/{reportId}/action { action, comments? } 将报告状态推进

由于 FinPilot 当前没有独立 approvals 表，审批记录复用 Report.status 字段：
- approve   -> report.status = 'approved'
- reject    -> report.status = 'rejected'
- modify    -> report.status = 'draft'（退回修改）
审批历史以「已审批过的报告」（status in approved/rejected）+ 当前 reviewing 为来源返回。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from finpilot.database.models import Report

from .deps import get_db_session, require_admin

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _ok(data: Any, message: str = "success") -> dict:
    return {"code": 0, "message": message, "data": data}


# 已完成审批的 report.status 取值
_FINAL_STATUSES = ("approved", "rejected")
# 审批动作 -> 目标状态
_ACTION_TO_STATUS = {
    "approve": "approved",
    "reject": "rejected",
    "modify": "draft",
}


@router.get("")
def list_approvals(
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """列出审批历史记录。

    返回 ApprovalRecord[]，按 created_at 倒序。
    来源：Report 表中 status 处于已审批状态（approved/rejected）的记录。
    """
    rows = (
        db.query(Report)
        .filter(Report.status.in_(_FINAL_STATUSES))
        .order_by(Report.updated_at.desc().nullsfirst(), Report.created_at.desc())
        .limit(limit)
        .all()
    )
    return _ok([
        {
            "id": str(r.id),
            "report_id": str(r.id),
            "reviewer_id": str(r.created_by) if r.created_by is not None else "",
            # status 即审批结论：approved -> approve / rejected -> reject
            "action": "approve" if r.status == "approved" else "reject",
            "comments": r.summary or None,
            "created_at": (r.updated_at or r.created_at).isoformat()
            if (r.updated_at or r.created_at)
            else None,
        }
        for r in rows
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
    """
    action = (payload.get("action") or "").strip().lower()
    if action not in _ACTION_TO_STATUS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效动作: {action}，支持 approve/reject/modify",
        )
    r = db.get(Report, report_id)
    if not r:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在")
    if r.status not in ("reviewing", "draft", "approved", "rejected"):
        # 兼容各种中间状态，都允许操作
        pass

    r.status = _ACTION_TO_STATUS[action]
    comments = (payload.get("comments") or "").strip()
    if comments:
        # 把审批意见追加到 summary（无独立字段），保留原内容
        prefix = r.summary + "\n\n" if r.summary else ""
        r.summary = f"{prefix}[审批-{action}] {comments}"
    r.updated_at = datetime.utcnow()
    try:
        db.commit()
        db.refresh(r)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"审批失败: {exc}"
        ) from exc
    return _ok({
        "report_id": str(r.id),
        "status": r.status,
        "reviewer_id": str(current_user.get("user_id", "")),
        "action": action,
    }, f"已{ {'approve': '通过', 'reject': '驳回', 'modify': '退回修改'}[action] }")
