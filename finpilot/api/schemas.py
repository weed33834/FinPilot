# -*- coding: utf-8 -*-
"""Pydantic 请求/响应模型 - API 数据契约。

所有对外接口的入参/出参均在此定义，便于前端 TypeScript 类型对齐。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------- 认证 ----------
class LoginRequest(BaseModel):
    # 前端传 username（兼容 email），remember_me 可选
    username: str
    password: str
    remember_me: bool = False
    # 兼容旧字段：直接传 email
    email: Optional[str] = None


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str


class AuthResponse(BaseModel):
    user: dict
    message: str


class LoginData(BaseModel):
    """前端 LoginData 契约 — 与 types/twoFactor.ts 对齐"""
    access_token: Optional[str] = None
    token_type: str = "session"
    expires_in: int = 7 * 24 * 60 * 60
    requires_2fa: bool = False
    challenge_token: Optional[str] = None
    challenge_expires_in: Optional[int] = None


# ---------- 文档 ----------
class DocumentResponse(BaseModel):
    # from_attributes=True：允许直接从 SQLAlchemy ORM 对象构造
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    file_type: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None


# ---------- NL2SQL 查询 ----------
class QueryRequest(BaseModel):
    question: str
    deep: bool = False


class QueryResponse(BaseModel):
    sql: str
    rows: list[dict[str, Any]]
    columns: list[str]
    explanation: str
    confidence: float = 0.0


# ---------- 智能体对话 ----------
class ChatRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    intent: str
    confidence: float
    steps: list[Any]


# ---------- 研报 ----------
class ReportRequest(BaseModel):
    ticker: str
    company_name: str
    peer_tickers: list[str] = Field(default_factory=list)


# ---------- LLM 供应商 ----------
class LlmProviderModelRequest(BaseModel):
    """供应商下模型的最小创建参数。"""
    model_name: str
    display_name: Optional[str] = None
    tier: str = "medium"
    is_active: bool = True


class LlmProviderRequest(BaseModel):
    name: str
    provider_type: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    is_default: bool = False
    # 允许创建供应商时一并创建模型（前端 LlmProviderForm 期望一次性提交）
    models: list[LlmProviderModelRequest] = Field(default_factory=list)


# ---------- 管理后台 ----------
class DashboardResponse(BaseModel):
    documents_count: int
    reports_count: int
    conversations_count: int
    queries_count: int
