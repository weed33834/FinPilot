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
    # 可选：关联会话，便于查询历史按会话回放
    conversation_id: Optional[int] = None


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


# ---------------------------------------------------------------------------
# 提示词模板 (prompts)
# ---------------------------------------------------------------------------

class PromptTemplateCreate(BaseModel):
    """提示词模板创建请求."""
    name: str = Field(..., description="模板名称")
    description: str | None = Field(default=None, description="模板描述")
    template_type: str = Field(..., description="模板类型")
    content: str = Field(..., description="模板内容")
    variables: list[str] | None = Field(default=None, description="变量列表")


class PromptTemplateUpdate(BaseModel):
    """提示词模板更新请求."""
    name: str | None = None
    description: str | None = None
    template_type: str | None = None
    content: str | None = None
    variables: list[str] | None = None


class PromptTemplateResponse(BaseModel):
    """提示词模板响应."""
    model_config = ConfigDict(from_attributes=True)
    id: str
    tenant_id: str | None = None
    name: str
    description: str | None = None
    template_type: str
    content: str
    variables: list[str] | None = None
    is_system: bool = False
    is_active: bool = True
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class PromptRenderRequest(BaseModel):
    """提示词渲染请求."""
    template_id: str | None = Field(default=None, description="模板 ID")
    content: str | None = Field(default=None, description="直接传入模板内容")
    variables: dict[str, Any] = Field(default_factory=dict, description="变量映射")


class PromptAIGenerateRequest(BaseModel):
    """AI 自动生成提示词请求."""
    description: str = Field(..., min_length=2, description="需求描述（自然语言）")
    template_type: str = Field(default="general", description="目标分类")
    tone: str = Field(default="professional", description="风格：professional/concise/friendly")
    language: str = Field(default="zh", description="输出语言：zh/en")


class PromptAIGenerateResponse(BaseModel):
    name: str
    description: str
    template_type: str
    content: str
    variables: list[str]


class PromptImportItem(BaseModel):
    """单个待导入的提示词模板."""
    name: str
    description: str | None = None
    template_type: str = "general"
    content: str
    variables: list[str] | None = None
    is_active: bool = True


class PromptImportRequest(BaseModel):
    """批量导入提示词请求."""
    items: list[PromptImportItem] = Field(..., min_length=1, max_length=200)


class PromptTestRequest(BaseModel):
    """测试渲染请求."""
    variables: dict[str, Any] = Field(default_factory=dict, description="样例变量")
    include_few_shot: bool = Field(default=False, description="是否注入 few-shot 示例")


class PromptEvaluateRequest(BaseModel):
    """批量评估请求."""
    test_cases: list[dict[str, Any]] = Field(..., description="测试用例列表")
    use_llm: bool = Field(default=False, description="是否调用 LLM (llm_judge)")
    pass_threshold: float = Field(default=0.6, ge=0, le=1, description="通过阈值")
    include_few_shot: bool = Field(default=False, description="是否注入 few-shot 示例")


# ---------------------------------------------------------------------------
# 报告订阅 (report_subscriptions)
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


# ---------------------------------------------------------------------------
# 技能管理 (skills)
# ---------------------------------------------------------------------------

class SkillCreate(BaseModel):
    """技能创建请求."""
    name: str = Field(..., description="技能名称")
    display_name: str = Field(..., description="展示名称")
    description: str | None = None
    category: str = Field(..., description="技能分类")
    prompt_id: str | None = Field(default=None, description="关联提示词模板 ID")
    system_prompt_override: str | None = None
    icon: str | None = None
    tool_ids: list[str] = Field(default_factory=list, description="关联工具 ID 列表")
    is_active: bool = True


class SkillUpdate(BaseModel):
    """技能更新请求."""
    name: str | None = None
    display_name: str | None = None
    description: str | None = None
    category: str | None = None
    prompt_id: str | None = None
    system_prompt_override: str | None = None
    icon: str | None = None
    tool_ids: list[str] | None = None
    is_active: bool | None = None


class SkillResponse(BaseModel):
    """技能响应."""
    model_config = ConfigDict(from_attributes=True)
    id: str
    tenant_id: str | None = None
    name: str
    display_name: str
    description: str | None = None
    category: str
    prompt_id: str | None = None
    system_prompt_override: str | None = None
    is_active: bool = True
    icon: str | None = None
    tool_ids: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class SkillTestRequest(BaseModel):
    """技能测试请求."""
    query: str = Field(..., description="测试查询文本")


# ---------------------------------------------------------------------------
# 工具管理 (tools)
# ---------------------------------------------------------------------------

class ToolCreate(BaseModel):
    """工具创建请求."""
    name: str = Field(..., description="工具名称")
    display_name: str = Field(..., description="展示名称")
    description: str | None = None
    type: str = Field(..., description="工具类型")
    config: dict[str, Any] = Field(default_factory=dict, description="工具配置")
    api_key: str | None = None


class ToolUpdate(BaseModel):
    """工具更新请求."""
    name: str | None = None
    display_name: str | None = None
    description: str | None = None
    type: str | None = None
    config: dict[str, Any] | None = None
    api_key: str | None = None
    is_active: bool | None = None


class ToolResponse(BaseModel):
    """工具响应."""
    model_config = ConfigDict(from_attributes=True)
    id: str
    tenant_id: str | None = None
    name: str
    display_name: str
    description: str | None = None
    type: str
    is_builtin: bool = False
    is_active: bool = True
    has_api_key: bool = False
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class ToolTestRequest(BaseModel):
    """工具测试请求."""
    parameters: dict[str, Any] = Field(default_factory=dict, description="测试参数")
