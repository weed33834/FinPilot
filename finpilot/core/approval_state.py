# -*- coding: utf-8 -*-
"""通用审批状态机 — Budget / Report 等模块共享。

状态流转：
    DRAFT → SUBMITTED → APPROVED
              ↓
           REJECTED → SUBMITTED（重新提交）
"""
from __future__ import annotations

from enum import Enum


class ApprovalState(str, Enum):
    """审批生命周期状态枚举。"""
    DRAFT = "draft"
    SUBMITTED = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# 合法转换表：{current: {allowed targets}}
_TRANSITION_TABLE: dict[ApprovalState, set[ApprovalState]] = {
    ApprovalState.DRAFT:     {ApprovalState.SUBMITTED},
    ApprovalState.SUBMITTED:  {ApprovalState.APPROVED, ApprovalState.REJECTED},
    ApprovalState.REJECTED:  {ApprovalState.SUBMITTED},
    ApprovalState.APPROVED:  set(),
}


def can_transition(current: str, target: str) -> bool:
    """检查 current → target 是否为合法状态迁移。"""
    cur = ApprovalState(current)
    tgt = ApprovalState(target)
    return tgt in _TRANSITION_TABLE.get(cur, set())


def validate_transition(current: str, target: str) -> None:
    """验证状态迁移合法性，非法时抛出 ValueError。"""
    if not can_transition(current, target):
        raise ValueError(
            f"Invalid approval state transition: "
            f"'{current}' → '{target}'"
        )


def get_next_states(current: str) -> list[str]:
    """获取当前状态下允许迁移到的所有目标状态列表。"""
    cur = ApprovalState(current)
    return [s.value for s in _TRANSITION_TABLE.get(cur, set())]
