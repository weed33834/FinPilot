# -*- coding: utf-8 -*-
"""test_health.py — 健康检查端点验证。

验证 /api/v1/ 返回 200 且响应体包含 status 和 version 字段。
"""
from __future__ import annotations


class TestHealthCheck:
    """健康检查端点测试套件。"""

    def test_health_returns_200(self, client):
        """GET /api/v1/ 应返回 200 状态码。"""
        response = client.get("/api/v1/")
        assert response.status_code == 200

    def test_health_body_status_ok(self, client):
        """响应体 status 字段应为 'ok'。"""
        response = client.get("/api/v1/")
        body = response.json()
        assert body["status"] == "ok"

    def test_health_body_has_version(self, client):
        """响应体应包含 version 字段且非空。"""
        response = client.get("/api/v1/")
        body = response.json()
        assert "version" in body
        assert body["version"] is not None
        assert len(body["version"]) > 0

    def test_health_body_exact_fields(self, client):
        """响应体应至少包含 status 和 version 两个字段。"""
        response = client.get("/api/v1/")
        body = response.json()
        assert isinstance(body, dict)
        assert set(body.keys()) >= {"status", "version"}

    def test_health_content_type_json(self, client):
        """响应 Content-Type 应为 application/json。"""
        response = client.get("/api/v1/")
        assert "application/json" in response.headers.get("content-type", "")
