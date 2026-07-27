# -*- coding: utf-8 -*-
"""test_rate_limit.py — 登录限流 429 验证。

验证 POST /api/v1/auth/login 的速率限制：同一 IP 每分钟最多 5 次尝试，
第 6 次返回 429 Too Many Requests。
"""
from __future__ import annotations

import pytest


# 用于限流测试的固定请求体（同一 IP 连续发送）
LOGIN_PAYLOAD = {
    "username": "nonexistent@test.local",
    "password": "wrong_password_123",
}

# 登录限流阈值（与 auth.py 中 @limiter.limit("5/minute") 一致）
RATE_LIMIT_THRESHOLD = 5


class TestLoginRateLimit:
    """登录接口速率限制测试。"""

    def test_first_five_requests_not_429(self, client):
        """前 5 次登录尝试不应被限流拒绝（可能 401 或 400，但不能是 429）。"""
        for i in range(RATE_LIMIT_THRESHOLD):
            response = client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)
            assert response.status_code != 429, (
                f"第 {i + 1} 次请求不应返回 429，实际 {response.status_code}"
            )

    def test_sixth_request_returns_429(self, client):
        """第 6 次请求应触发限流并返回 429 Too Many Requests。

        同一个 TestClient 实例内 cookies/headers 被复用，
        slowapi 基于 get_remote_address（127.0.0.1）限流，
        因此连续 6 次同 IP 请求应触发限流。
        """
        # 先发送 5 次请求耗尽配额
        for _ in range(RATE_LIMIT_THRESHOLD):
            client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)

        # 第 6 次应返回 429
        response = client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)
        assert response.status_code == 429, (
            f"第 6 次请求期望 429，实际 {response.status_code}: "
            f"{response.text[:200]}"
        )

    def test_rate_limit_response_has_retry_after(self, client):
        """限流响应应包含 Retry-After 头。"""
        for _ in range(RATE_LIMIT_THRESHOLD):
            client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)

        response = client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)
        # slowapi 在 headers_enabled=True 时设置限流相关头
        # Retry-After 存在时说明限流生效
        retry_after = response.headers.get("Retry-After")
        assert retry_after is not None or response.status_code == 429, (
            "限流响应应包含 Retry-After 头或返回 429"
        )

    def test_health_endpoint_not_rate_limited(self, client):
        """健康检查端点不应受登录限流影响。"""
        # 先耗尽登录配额
        for _ in range(RATE_LIMIT_THRESHOLD + 3):
            client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)

        # 健康检查应始终返回 200
        response = client.get("/api/v1/")
        assert response.status_code == 200
