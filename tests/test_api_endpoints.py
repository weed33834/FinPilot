# -*- coding: utf-8 -*-
"""test_api_endpoints.py — 核心端点未认证时的 401 冒烟测试。

覆盖 FinPilot 主要受保护路由：未携带任何认证凭据访问这些端点，
应统一返回 401 UNAUTHORIZED。
"""
from __future__ import annotations

import pytest


# 预期返回 401 的核心端点（method, path）
PROTECTED_ENDPOINTS = [
    # 认证相关（logout 是公开端点无需认证，不在此列）
    ("GET", "/api/v1/auth/me"),
    # 文档管理
    ("GET", "/api/v1/documents/"),
    # 查询历史
    ("GET", "/api/v1/queries/history"),
    # 会话
    ("GET", "/api/v1/conversations/"),
    # 智能体
    ("POST", "/api/v1/agent/chat"),
    # 用户管理（需要 admin，但未认证先返回 401）
    ("GET", "/api/v1/users/"),
    # LLM 供应商
    ("GET", "/api/v1/llm-providers/"),
    # 报表
    ("GET", "/api/v1/reports/"),
    # 审批
    ("GET", "/api/v1/approvals/"),
    # 审计日志
    ("GET", "/api/v1/audit/logs"),
]


class TestUnauthenticatedAccess:
    """未认证访问受保护端点应统一返回 401。"""

    @pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
    def test_unauthenticated_returns_401(self, client, method, path):
        """未携带 session cookie 或 Bearer token 访问受保护端点。"""
        if method == "GET":
            response = client.get(path)
        elif method == "POST":
            response = client.post(path, json={})
        else:
            pytest.skip(f"Unsupported method: {method}")

        assert response.status_code == 401, (
            f"{method} {path} 期望 401，实际 {response.status_code}: "
            f"{response.text[:200]}"
        )

    def test_health_does_not_require_auth(self, client):
        """健康检查端点 /api/v1/ 无需认证，应返回 200。"""
        response = client.get("/api/v1/")
        assert response.status_code == 200

    def test_login_page_does_not_require_auth(self, client):
        """登录页面 /api/v1/auth/login (GET) 行为——可能不存在或返回非401。"""
        # 注意：login 只有 POST，GET 可能 405 或 404，但不应是 401（401 意味着需要认证才能看登录页）
        response = client.get("/api/v1/auth/login")
        assert response.status_code != 401, (
            f"GET /api/v1/auth/login 不应返回 401（登录页应公开）"
        )
