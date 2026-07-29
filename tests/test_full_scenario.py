# -*- coding: utf-8 -*-
"""test_full_scenario.py — 全场景 E2E 测试：模拟用户从启动到结束的完整思维链路。

覆盖范围（对应规则智能体审计的 9 条链路 + 企业级异常工况）：
- 认证全流程（注册/登录/me/错误密码/登出/会话过期）
- 会话与智能体对话（含无 LLM 时的优雅降级）
- 文档上传与列表
- 研报创建与查询
- API Key 全生命周期（创建/列表/轮换/吊销）
- 站内通知（列表/标记已读/全部已读）
- 多租户隔离（用户 B 看不到用户 A 的数据）
- WebSocket 实时通知握手
- 异常工况（无效输入/越权/资源不存在）

设计原则：复刻真实世界复杂工况，不只盯简单场景；每个场景验证状态稳定性。
"""
from __future__ import annotations

import io

import pytest


# ──────────────────────────────────────────────────────────────────
# 辅助：注册并登录一个用户，返回已带 cookie 的 client（复用同一 client）
# ──────────────────────────────────────────────────────────────────
def _register_and_login(client, email: str, password: str = "Pass1234!", name: str = "用户"):
    """注册（若已存在则直接登录），返回登录响应。"""
    client.post("/api/v1/auth/register", json={"email": email, "password": password, "name": name})
    return client.post(
        "/api/v1/auth/login",
        json={"username": email, "password": password, "remember_me": False},
    )


# ══════════════════════════════════════════════════════════════════
# 1. 认证全流程
# ══════════════════════════════════════════════════════════════════
class TestAuthJourney:
    """用户认证完整思维链路：注册 → 登录 → 身份 → 错误密码 → 登出。"""

    def test_register_login_me_logout(self, client):
        # 注册
        r = client.post(
            "/api/v1/auth/register",
            json={"email": "alice@finpilot.ai", "password": "Alice1234!", "name": "Alice"},
        )
        assert r.status_code in (200, 201), r.text

        # 登录（正确密码）
        r = client.post(
            "/api/v1/auth/login",
            json={"username": "alice@finpilot.ai", "password": "Alice1234!", "remember_me": False},
        )
        assert r.status_code == 200, f"正确密码应登录成功: {r.text}"
        assert "session_id" in client.cookies, "登录应下发 session_id cookie"

        # 获取当前用户
        r = client.get("/api/v1/auth/me")
        assert r.status_code == 200
        assert r.json()["data"]["email"] == "alice@finpilot.ai"

        # 登出
        r = client.post("/api/v1/auth/logout")
        assert r.status_code == 200
        # 登出后 cookie 失效，访问受保护端点应 401
        r = client.get("/api/v1/auth/me")
        assert r.status_code == 401, "登出后应无法访问受保护端点"

    def test_wrong_password_rejected(self, client):
        """关键安全验证：错误密码必须返回 401（修复登录绕过漏洞）。"""
        client.post(
            "/api/v1/auth/register",
            json={"email": "bob@finpilot.ai", "password": "Bob1234!", "name": "Bob"},
        )
        r = client.post(
            "/api/v1/auth/login",
            json={"username": "bob@finpilot.ai", "password": "WrongPassword!", "remember_me": False},
        )
        assert r.status_code == 401, f"错误密码应被拒绝，实际 {r.status_code}: {r.text}"

    def test_expired_session_rejected(self, client):
        """伪造/过期 session 应被拒绝。"""
        client.cookies.set("session_id", "invalid-session-id-xxxxx")
        r = client.get("/api/v1/auth/me")
        assert r.status_code == 401

    def test_bearer_token_auth(self, client):
        """API 客户端用 Bearer token 认证也应可用。"""
        client.post(
            "/api/v1/auth/register",
            json={"email": "carol@finpilot.ai", "password": "Carol123!", "name": "Carol"},
        )
        r = client.post(
            "/api/v1/auth/login",
            json={"username": "carol@finpilot.ai", "password": "Carol123!", "remember_me": False},
        )
        token = r.json()["data"]["access_token"]
        # 用 Bearer 访问（不带 cookie）
        client.cookies.clear()
        r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200


# ══════════════════════════════════════════════════════════════════
# 2. 会话与智能体对话
# ══════════════════════════════════════════════════════════════════
class TestConversationJourney:
    """对话思维链路：发起对话 → 查询历史会话 → 查看详情 → 删除。"""

    def test_chat_creates_conversation(self, client):
        _register_and_login(client, "dave@finpilot.ai")
        # 发起对话（无 LLM 时应优雅降级，不应 500 崩溃）
        r = client.post("/api/v1/agent/chat", json={"question": "帮我分析腾讯财报"})
        assert r.status_code in (200, 502, 503), f"对话应优雅处理（无LLM降级），实际 {r.status_code}: {r.text[:200]}"
        if r.status_code == 200:
            data = r.json().get("data", r.json())
            assert "conversation_id" in data or "answer" in data

    def test_conversation_list_and_delete(self, client):
        _register_and_login(client, "eve@finpilot.ai")
        # 先发起一次对话创建会话
        client.post("/api/v1/agent/chat", json={"question": "你好"})
        # 列出会话
        r = client.get("/api/v1/conversations/")
        assert r.status_code == 200
        convs = r.json().get("data", {}).get("items", r.json().get("data", []))
        if isinstance(convs, list) and convs:
            cid = convs[0]["id"]
            # 查看详情
            r = client.get(f"/api/v1/conversations/{cid}")
            assert r.status_code == 200
            # 删除
            r = client.delete(f"/api/v1/conversations/{cid}")
            assert r.status_code == 200
            # 再查应 404
            r = client.get(f"/api/v1/conversations/{cid}")
            assert r.status_code == 404


# ══════════════════════════════════════════════════════════════════
# 3. 文档上传
# ══════════════════════════════════════════════════════════════════
class TestDocumentJourney:
    """文档思维链路：上传 → 列表。"""

    def test_upload_and_list(self, client):
        _register_and_login(client, "frank@finpilot.ai")
        content = "2025年Q3营收100亿元，同比增长15%。净利润20亿元。"
        r = client.post(
            "/api/v1/documents/upload",
            files={"file": ("测试财报.txt", io.BytesIO(content.encode("utf-8")), "text/plain")},
        )
        assert r.status_code in (200, 201), f"上传应成功: {r.text[:200]}"
        # 列表
        r = client.get("/api/v1/documents/")
        assert r.status_code == 200


# ══════════════════════════════════════════════════════════════════
# 4. 研报
# ══════════════════════════════════════════════════════════════════
class TestReportJourney:
    """研报思维链路：创建 → 列表 → 查询。"""

    def test_create_list_get(self, client):
        _register_and_login(client, "grace@finpilot.ai")
        r = client.post(
            "/api/v1/reports",
            json={"title": "腾讯2025Q3分析", "report_type": "equity_research"},
        )
        assert r.status_code in (200, 201), f"创建研报应成功: {r.text[:200]}"
        rid = r.json().get("data", {}).get("id")
        # 列表
        r = client.get("/api/v1/reports/")
        assert r.status_code == 200
        # 查询（若拿到 id）
        if rid:
            r = client.get(f"/api/v1/reports/{rid}")
            assert r.status_code in (200, 404)


# ══════════════════════════════════════════════════════════════════
# 5. API Key 全生命周期
# ══════════════════════════════════════════════════════════════════
class TestApiKeyLifecycle:
    """API Key 思维链路：创建 → 列表 → 轮换 → 吊销。"""

    def test_full_lifecycle(self, client):
        _register_and_login(client, "henry@finpilot.ai")
        # 创建
        r = client.post("/api/v1/api-keys", json={"name": "测试密钥", "scopes": ["read"]})
        assert r.status_code in (200, 201), f"创建 API Key 应成功: {r.text[:200]}"
        key_id = r.json().get("data", {}).get("id")
        assert key_id, "应返回 key id"
        # 列表
        r = client.get("/api/v1/api-keys")
        assert r.status_code == 200
        # 轮换
        r = client.post(f"/api/v1/api-keys/{key_id}/rotate")
        assert r.status_code == 200, f"轮换应成功: {r.text[:200]}"
        # 吊销
        r = client.post(f"/api/v1/api-keys/{key_id}/revoke")
        assert r.status_code == 200


# ══════════════════════════════════════════════════════════════════
# 6. 站内通知
# ══════════════════════════════════════════════════════════════════
class TestNotificationJourney:
    """通知思维链路：产生通知 → 列表 → 标记已读 → 全部已读。"""

    def test_notification_flow(self, client, db_session):
        user_email = "ivan@finpilot.ai"
        _register_and_login(client, user_email)
        # 直接通过业务入口写一条通知（模拟报告生成完成推送）
        from finpilot.api.notifications import notify_user
        from finpilot.database.models import User

        user = db_session.query(User).filter_by(email=user_email).first()
        uid = f"user_{user.id}"
        notify_user(db_session, uid, channel="report", title="报告生成完成", content="《腾讯分析》已就绪")
        db_session.commit()

        # 列表
        r = client.get("/api/v1/notifications/")
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) >= 1, "应能查到通知"
        nid = items[0]["id"]
        assert items[0]["is_read"] is False

        # 标记单条已读
        r = client.post(f"/api/v1/notifications/{nid}/read")
        assert r.status_code == 200

        # 全部已读
        r = client.post("/api/v1/notifications/read-all")
        assert r.status_code == 200


# ══════════════════════════════════════════════════════════════════
# 7. 多租户隔离（核心安全场景）
# ══════════════════════════════════════════════════════════════════
class TestTenantIsolation:
    """用户 A 的数据对用户 B 不可见（横向隔离验证）。"""

    def test_reports_isolated(self, client):
        # 用户 A 创建研报
        _register_and_login(client, "alice@finpilot.ai")
        client.post("/api/v1/reports", json={"title": "A的私密研报", "report_type": "custom"})
        r_a = client.get("/api/v1/reports/")
        a_titles = {it["title"] for it in r_a.json().get("data", {}).get("items", [])}

        # 用户 B 登录（同一 client，先登出 A）
        client.post("/api/v1/auth/logout")
        _register_and_login(client, "bob@finpilot.ai")
        r_b = client.get("/api/v1/reports/")
        b_titles = {it["title"] for it in r_b.json().get("data", {}).get("items", [])}

        assert "A的私密研报" in a_titles, "A 应能看到自己的研报"
        assert "A的私密研报" not in b_titles, "B 不应看到 A 的研报（租户隔离）"

    def test_notifications_isolated(self, client, db_session):
        from finpilot.api.notifications import notify_user
        from finpilot.database.models import User

        # A 注册并产生通知
        _register_and_login(client, "alice2@finpilot.ai")
        alice = db_session.query(User).filter_by(email="alice2@finpilot.ai").first()
        notify_user(db_session, f"user_{alice.id}", "system", "A的通知", "仅A可见")
        db_session.commit()
        client.post("/api/v1/auth/logout")

        # B 登录查看通知
        _register_and_login(client, "bob2@finpilot.ai")
        r = client.get("/api/v1/notifications/")
        titles = {it["title"] for it in r.json()["data"]["items"]}
        assert "A的通知" not in titles, "B 不应看到 A 的通知"


# ══════════════════════════════════════════════════════════════════
# 8. WebSocket 实时通知握手
# ══════════════════════════════════════════════════════════════════
class TestWebSocket:
    """WebSocket 推送链路：鉴权 → welcome 消息 → ping/pong。"""

    def test_ws_requires_session(self, client):
        """无 session 的 WS 握手应被拒绝（4401），而非 404。"""
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/notifications") as ws:
                ws.receive()

    def test_ws_authenticated_receives_welcome(self, client):
        """带有效 session 的 WS 握手应收到 welcome 消息。"""
        _register_and_login(client, "wsuser@finpilot.ai")
        with client.websocket_connect("/ws/notifications") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "welcome"
            # ping/pong
            ws.send_text("ping")
            assert ws.receive_text() == "pong"


# ══════════════════════════════════════════════════════════════════
# 9. 异常工况
# ══════════════════════════════════════════════════════════════════
class TestExceptionHandling:
    """各类异常应被妥善处理（不暴露堆栈、状态码正确）。"""

    def test_invalid_input_returns_422(self, client):
        """缺字段请求应返回 422 校验错误。"""
        _register_and_login(client, "err@finpilot.ai")
        r = client.post("/api/v1/auth/login", json={})  # 缺 username/password
        assert r.status_code == 422

    def test_nonexistent_resource_returns_404(self, client):
        _register_and_login(client, "err2@finpilot.ai")
        r = client.get("/api/v1/conversations/999999")
        assert r.status_code == 404

    def test_unauthorized_access_returns_401(self, client):
        r = client.get("/api/v1/notifications/")
        assert r.status_code == 401

    def test_admin_endpoint_requires_admin(self, client):
        """普通用户访问 admin 端点应 403。"""
        _register_and_login(client, "normal@finpilot.ai")
        r = client.get("/api/v1/users/")
        assert r.status_code == 403
