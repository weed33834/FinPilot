# -*- coding: utf-8 -*-
"""RBAC 角色与权限定义 — 支持 5 种角色细粒度权限控制。

角色层级（权限依次递减）：
  admin > finance_manager > analyst > auditor > viewer
"""
from __future__ import annotations

from enum import Enum, auto

from fastapi import Depends, HTTPException


class Role(str, Enum):
    """5 种平台角色。"""
    ADMIN = "admin"
    FINANCE_MANAGER = "finance_manager"
    ANALYST = "analyst"
    AUDITOR = "auditor"
    VIEWER = "viewer"


class Permission(Enum):
    """细粒度权限点。"""
    VIEW_FINANCIALS = auto()
    EDIT_JOURNAL_ENTRIES = auto()
    APPROVE_REPORTS = auto()
    EXPORT_REPORTS = auto()
    CREATE_BUDGET = auto()
    APPROVE_BUDGET = auto()
    VIEW_BUDGET = auto()
    MANAGE_USERS = auto()
    MANAGE_ROLES = auto()
    CONFIGURE_SYSTEM = auto()
    VIEW_AUDIT_LOGS = auto()
    MANAGE_API_KEYS = auto()


ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.ADMIN: set(Permission),
    Role.FINANCE_MANAGER: {
        Permission.VIEW_FINANCIALS,
        Permission.EDIT_JOURNAL_ENTRIES,
        Permission.APPROVE_REPORTS,
        Permission.EXPORT_REPORTS,
        Permission.CREATE_BUDGET,
        Permission.APPROVE_BUDGET,
        Permission.VIEW_BUDGET,
        Permission.VIEW_AUDIT_LOGS,
    },
    Role.ANALYST: {
        Permission.VIEW_FINANCIALS,
        Permission.VIEW_BUDGET,
        Permission.EXPORT_REPORTS,
    },
    Role.AUDITOR: {
        Permission.VIEW_FINANCIALS,
        Permission.VIEW_AUDIT_LOGS,
        Permission.VIEW_BUDGET,
    },
    Role.VIEWER: {
        Permission.VIEW_FINANCIALS,
    },
}


def require_permission(perm: Permission):
    """FastAPI 依赖：校验当前用户是否持有指定权限。

    用法::

        @router.get("/reports", dependencies=[Depends(require_permission(Permission.VIEW_FINANCIALS))])
    """

    from finpilot.api.deps import get_current_user

    async def checker(current_user: dict = Depends(get_current_user)):
        role = Role(current_user.get("role", "viewer"))
        if perm not in ROLE_PERMISSIONS.get(role, set()):
            raise HTTPException(
                status_code=403,
                detail=f"Missing permission: {perm.name}",
            )
        return current_user

    return checker
