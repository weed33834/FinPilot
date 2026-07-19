"""
SQLAlchemy 2.0 ORM 模型 - 企业财务AI平台数据层
包含：用户、文档、文档分块、LLM供应商/模型、财务报表/科目、会话/消息、API密钥
所有模型使用 SQLAlchemy 2.0 风格（DeclarativeBase + Mapped + mapped_column）。
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, ForeignKey, JSON, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """所有 ORM 模型的声明式基类"""
    pass


class User(Base):
    """用户表 - 平台用户账号"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255))
    name: Mapped[Optional[str]] = mapped_column(String(100))
    # 角色：默认 analyst（分析师），可扩展 admin/auditor 等
    role: Mapped[str] = mapped_column(String(50), default="analyst")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 关系：一个用户拥有多个会话、API密钥、上传的文档
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="uploader")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}')>"


class Document(Base):
    """文档表 - 用户上传的财务文档"""
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(500))
    file_type: Mapped[Optional[str]] = mapped_column(String(50))  # pdf/docx/xlsx/csv
    file_path: Mapped[str] = mapped_column(String(1000))
    file_size: Mapped[Optional[int]] = mapped_column(Integer)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    uploaded_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    # 文档处理状态：pending(待处理)/indexed(已索引)/failed(失败)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    # 关系
    uploader = relationship("User", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, filename='{self.filename}', status='{self.status}')>"


class DocumentChunk(Base):
    """文档分块表 - RAG 向量检索的最小单元"""
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    # embedding 存储为 JSON 字符串（向量序列化），SQLite 下用 Text 承载
    embedding: Mapped[Optional[str]] = mapped_column(Text)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 关系
    document = relationship("Document", back_populates="chunks")

    def __repr__(self) -> str:
        return f"<DocumentChunk(id={self.id}, document_id={self.document_id}, idx={self.chunk_index})>"


class LlmProvider(Base):
    """LLM 供应商表 - 管理 openai/anthropic/ollama 等供应商"""
    __tablename__ = "llm_providers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    provider_type: Mapped[str] = mapped_column(String(50))  # openai/anthropic/ollama
    base_url: Mapped[Optional[str]] = mapped_column(String(500))
    # api_key 使用 base64 编码存储（简单编码，非强加密）
    api_key: Mapped[Optional[str]] = mapped_column(String(1000))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 关系：删除供应商时级联删除其下模型
    models = relationship("LlmModel", back_populates="provider", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<LlmProvider(id={self.id}, name='{self.name}', type='{self.provider_type}')>"


class LlmModel(Base):
    """LLM 模型表 - 供应商下的具体模型配置"""
    __tablename__ = "llm_models"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 级联删除：供应商删除时一并删除其模型
    provider_id: Mapped[int] = mapped_column(ForeignKey("llm_providers.id", ondelete="CASCADE"))
    model_name: Mapped[str] = mapped_column(String(200))  # 调用接口用的模型标识
    display_name: Mapped[Optional[str]] = mapped_column(String(200))  # 前端展示名称
    # 性能层级：low/medium/high，用于按需路由模型
    tier: Mapped[str] = mapped_column(String(20), default="medium")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # 关系
    provider = relationship("LlmProvider", back_populates="models")

    def __repr__(self) -> str:
        return f"<LlmModel(id={self.id}, model_name='{self.model_name}', tier='{self.tier}')>"


class FinancialReport(Base):
    """财务报表表 - 资产负债表/利润表/现金流量表等"""
    __tablename__ = "financial_reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    report_name: Mapped[str] = mapped_column(String(200))
    company_name: Mapped[Optional[str]] = mapped_column(String(200))
    ticker: Mapped[Optional[str]] = mapped_column(String(50))
    report_type: Mapped[str] = mapped_column(String(50))  # balance_sheet/income_statement/cash_flow
    period: Mapped[Optional[str]] = mapped_column(String(50))  # 如 2024-Q1 / 2024-FY
    # data_json 存储报表的原始 JSON 数据，便于灵活扩展
    data_json: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 关系
    accounts = relationship("FinancialAccount", back_populates="report", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<FinancialReport(id={self.id}, name='{self.report_name}', type='{self.report_type}')>"


class Report(Base):
    """研报表 — 用户通过前端 ReportsPage 创建的财务分析报告.

    与 FinPilot equity 的 ReportRequest（研报生成管线）不同，本表存储的是
    基于已有财务数据的即时分析报告，字段与前端 ``types/report.ts`` 中的
    ``Report`` 接口对齐。
    """
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(500))
    # profit/balance/cash/custom/comparison
    report_type: Mapped[str] = mapped_column(String(64))
    # 生成参数 JSON: {year, period, years[], template_id, ...}
    parameters: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    # 生成内容 JSON: {title, year, period, sections, summary, chart}
    content: Mapped[Optional[dict]] = mapped_column(JSON)
    # 导出文件 URL（若有）
    content_url: Mapped[Optional[str]] = mapped_column(String(500))
    # LLM 生成的摘要
    summary: Mapped[Optional[str]] = mapped_column(Text)
    # 状态: draft/processing/reviewing/approved/rejected/failed
    status: Mapped[str] = mapped_column(String(32), default="processing")
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    # 关联模板 ID（可选）
    template_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())


class FinancialAccount(Base):
    """财务科目表 - 报表下的具体会计科目明细"""
    __tablename__ = "financial_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("financial_reports.id"))
    account_name: Mapped[str] = mapped_column(String(200))  # 科目名称（支持中文）
    account_category: Mapped[Optional[str]] = mapped_column(String(100))  # 科目分类
    period: Mapped[Optional[str]] = mapped_column(String(50))
    debit_amount: Mapped[Optional[float]] = mapped_column(Float, default=0.0)  # 借方金额
    credit_amount: Mapped[Optional[float]] = mapped_column(Float, default=0.0)  # 贷方金额
    balance: Mapped[Optional[float]] = mapped_column(Float, default=0.0)  # 余额

    # 关系
    report = relationship("FinancialReport", back_populates="accounts")

    def __repr__(self) -> str:
        return f"<FinancialAccount(id={self.id}, name='{self.account_name}', balance={self.balance})>"


class Conversation(Base):
    """会话表 - 用户与AI的对话会话"""
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    title: Mapped[Optional[str]] = mapped_column(String(500))
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    # 是否归档：前端 ConversationsPage 按此分桶（active/archived）
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    # 关系
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, title='{self.title}')>"


class Message(Base):
    """消息表 - 会话中的单条消息"""
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String(20))  # user/assistant/system
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 关系
    conversation = relationship("Conversation", back_populates="messages")

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, role='{self.role}')>"


class AuditLog(Base):
    """审计日志表 - 记录 LLM 调用与安全事件（迁移自 legacy audit_service）.

    落库内容经 PII 脱敏，不存明文敏感信息。用于合规追溯、注入攻击取证、
    调用量统计。tenant_id / user_id 缺失时记为 None / 匿名。
    """
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 事件类型：llm_call / injection_blocked / login / policy_denied 等
    action: Mapped[str] = mapped_column(String(50), index=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    # 结果：ok / blocked / error
    status: Mapped[str] = mapped_column(String(20), default="ok")
    # 脱敏后的输入摘要（PII 已替换为占位符）
    detail: Mapped[Optional[str]] = mapped_column(Text)
    # 结构化元数据 JSON（模型名、耗时、威胁分等）
    meta_json: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action='{self.action}', status='{self.status}')>"


class ApiKey(Base):
    """API 密钥表 - 用户访问平台的密钥"""
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    key_hash: Mapped[str] = mapped_column(String(255))  # 密钥哈希值
    name: Mapped[Optional[str]] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 关系
    user = relationship("User", back_populates="api_keys")

    def __repr__(self) -> str:
        return f"<ApiKey(id={self.id}, name='{self.name}', active={self.is_active})>"


# ============================================================
# 扩展业务模型：财务智能体平台配套 ORM 模型。
#
# 设计说明：
#   - 主键为整数自增（与 FinPilot 现有模型一致）
#   - tenant_id 字段保留为普通索引列（不加外键 / RLS）
#   - last_report_id 字段保留为普通字符串列（不加外键）
#   - 敏感字段加密由 Service 层统一处理（不依赖 ORM 层 EncryptedString）
#   - DateTime 不带 timezone=True 以兼容 SQLite；JSON 使用 sqlalchemy.JSON
#   - AuditLog 未重复添加：FinPilot 已存在功能等价的 AuditLog 模型
# ============================================================


class McpServerConfig(Base):
    """MCP 服务器配置 — 连接外部 MCP 服务器."""
    __tablename__ = "mcp_server_configs"
    __table_args__ = (
        Index("ix_mcp_tenant_active", "tenant_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(128))  # 服务器名称，唯一标识
    display_name: Mapped[str] = mapped_column(String(128))  # 展示名称
    description: Mapped[Optional[str]] = mapped_column(Text)  # 描述
    # 传输方式: stdio / sse / streamable_http
    transport: Mapped[str] = mapped_column(String(32), default="stdio")
    # stdio 模式: 启动命令（如 'npx -y @modelcontextprotocol/server-sqlite'）
    command: Mapped[Optional[str]] = mapped_column(String(512))
    # stdio 模式: 命令参数（JSON 数组字符串）
    args: Mapped[Optional[str]] = mapped_column(Text)
    # sse/streamable_http 模式: 服务器 URL
    url: Mapped[Optional[str]] = mapped_column(String(512))
    # API Key（FinPilot 暂无加密类型层，按普通字符串存储，加密由 Service 层处理）
    api_key: Mapped[Optional[str]] = mapped_column(String(1000))
    # 环境变量（JSON 对象）
    env_vars: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # 是否启用
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否内置（不可删除）
    priority: Mapped[int] = mapped_column(Integer, default=0)  # 优先级（数字越小越优先）
    last_connected_at: Mapped[Optional[str]] = mapped_column(String(64))  # 最后连接时间
    # 最后连接状态: connected / error / untested
    last_status: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    def __repr__(self) -> str:
        return f"<McpServerConfig(id={self.id}, name='{self.name}', active={self.is_active})>"


class ReportSubscription(Base):
    """定时报告订阅 — 按 daily/weekly/monthly 频率自动生成报告并推送."""
    __tablename__ = "report_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(255))  # 订阅名称
    # 报告类型: profit/balance/cash/custom
    report_type: Mapped[str] = mapped_column(String(64))
    # 报告生成参数（JSON 对象）
    parameters: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    # 调度时间为 UTC（与定时任务默认时区一致），前端展示时标注
    frequency: Mapped[str] = mapped_column(String(16), default="daily")  # daily/weekly/monthly
    at_hour: Mapped[int] = mapped_column(Integer, default=8)  # 执行小时（UTC，0-23）
    at_minute: Mapped[int] = mapped_column(Integer, default=0)  # 执行分钟（0-59）
    # weekly 时生效（0=周一 ... 6=周日）
    day_of_week: Mapped[Optional[int]] = mapped_column(Integer)
    # monthly 时生效（1-28，封顶 28 避免月末歧义）
    day_of_month: Mapped[Optional[int]] = mapped_column(Integer)
    # 导出格式: pdf/xlsx/markdown/json
    export_format: Mapped[str] = mapped_column(String(16), default="pdf")
    # 通知渠道列表（JSON 数组）: in_app/email/im
    channels: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    # 接收方列表（JSON 数组，用户 ID / 邮箱 / IM ID）
    recipients: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    # 是否启用: Y/N（保留源端 Y/N 语义，未转为 Boolean 以避免数据迁移）
    is_active: Mapped[str] = mapped_column(String(1), default="Y")
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime)  # 上次执行时间
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)  # 下次执行时间
    # 上次生成的报告 ID（源端外键 reports.id 已移除：reports 表在 FinPilot 中不存在）
    last_report_id: Mapped[Optional[str]] = mapped_column(String(64))
    last_error: Mapped[Optional[str]] = mapped_column(Text)  # 上次执行错误信息
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    def __repr__(self) -> str:
        return f"<ReportSubscription(id={self.id}, name='{self.name}', freq='{self.frequency}')>"


class ReportTemplate(Base):
    """持久化的报告模板 — 覆盖内置模板渲染逻辑."""
    __tablename__ = "report_templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(128))  # 模板名称
    # 关联报告类型: profit/balance/cash/custom/comparison
    report_type: Mapped[str] = mapped_column(String(64))
    # 模板 sections 定义（JSON 数组）: [{name, metric}]
    sections: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    # 摘要模板（string.Template 语法）
    summary_template: Mapped[str] = mapped_column(Text, default="")
    # 标题模板，空时用内置
    title_template: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    # 是否启用: Y/N（保留源端 Y/N 语义）
    is_active: Mapped[str] = mapped_column(String(1), default="Y")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    def __repr__(self) -> str:
        return f"<ReportTemplate(id={self.id}, name='{self.name}', type='{self.report_type}')>"


class SandboxConfig(Base):
    """沙箱配置 — SQL 白名单 + 代码沙箱配置."""
    __tablename__ = "sandbox_configs"
    __table_args__ = (
        Index("ix_sandbox_tenant_type", "tenant_id", "config_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    # 配置类型: sql_whitelist / code_sandbox / file_upload
    config_type: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(128))  # 配置名称
    description: Mapped[Optional[str]] = mapped_column(Text)  # 描述
    # 配置 JSON：
    #   SQL 白名单: {"tables": [...], "max_rows": 1000}
    #   代码沙箱: {"mode": "lightweight", "timeout": 30, "memory_mb": 256,
    #             "allowed_modules": [...], "blocked_modules": [...]}
    #   文件上传: {"max_size_mb": 50, "allowed_types": [...]}
    config: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # 是否启用
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否系统默认
    priority: Mapped[int] = mapped_column(Integer, default=0)  # 优先级
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    def __repr__(self) -> str:
        return f"<SandboxConfig(id={self.id}, type='{self.config_type}', name='{self.name}')>"


class SandboxExecution(Base):
    """沙箱执行记录 — 持久化每次代码执行的输入输出.

    用于审计、调试、回放，以及前端"执行历史"展示。
    """
    __tablename__ = "sandbox_executions"
    __table_args__ = (
        Index("ix_sandbox_exec_tenant_config", "tenant_id", "config_id"),
        Index("ix_sandbox_exec_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    config_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("sandbox_configs.id", ondelete="SET NULL"), index=True
    )
    # 触发来源: manual (手动测试) / agent (智能体调用) / nl2sql (SQL 沙箱)
    trigger_source: Mapped[str] = mapped_column(String(32), default="manual")
    language: Mapped[str] = mapped_column(String(16), default="python")
    code: Mapped[str] = mapped_column(Text)
    stdout: Mapped[Optional[str]] = mapped_column(Text)
    stderr: Mapped[Optional[str]] = mapped_column(Text)
    exit_code: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    executed_by: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<SandboxExecution(id={self.id}, config_id={self.config_id}, success={self.success})>"


class PromptTemplate(Base):
    """可复用的提示词模板 — 支持 {variable} 占位符."""
    __tablename__ = "prompt_templates"
    __table_args__ = (
        Index("ix_prompt_tenant_type", "tenant_id", "template_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(255))  # 模板名称
    description: Mapped[Optional[str]] = mapped_column(Text)  # 模板描述
    # 模板类型: general/query/report/audit/custom
    template_type: Mapped[str] = mapped_column(String(64), default="general")
    # 提示词模板内容（支持 {variable} 占位符）
    content: Mapped[str] = mapped_column(Text)
    # JSON 数组字符串，模板中的变量列表
    variables: Mapped[Optional[str]] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否系统内置（不可删除）
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # 是否启用
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    # 关系：一个模板对应多个历史版本
    versions = relationship("PromptVersion", back_populates="prompt", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<PromptTemplate(id={self.id}, name='{self.name}', type='{self.template_type}')>"


class PromptVersion(Base):
    """提示词版本快照 — 与 PromptTemplate 一对多，is_active_version=True 为当前生效版本."""
    __tablename__ = "prompt_versions"
    __table_args__ = (
        Index("ix_prompt_version_prompt_version", "prompt_id", "version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    prompt_id: Mapped[int] = mapped_column(ForeignKey("prompt_templates.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)  # 版本号，按模板自增
    content: Mapped[str] = mapped_column(Text)  # 该版本下的提示词内容
    # 该版本下的变量 schema（JSON）
    variables: Mapped[Optional[dict]] = mapped_column(JSON)
    change_description: Mapped[Optional[str]] = mapped_column(Text)  # 本次变更说明
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))  # 变更操作人
    is_active_version: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否当前生效版本
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 关系
    prompt = relationship("PromptTemplate", back_populates="versions")

    def __repr__(self) -> str:
        return f"<PromptVersion(id={self.id}, prompt_id={self.prompt_id}, v={self.version})>"


class PromptABTest(Base):
    """提示词 A/B 测试配置 — 为同一 prompt_key 配置对照/实验变体并按流量分流."""
    __tablename__ = "prompt_ab_tests"
    __table_args__ = (
        Index("ix_prompt_ab_test_tenant_key", "tenant_id", "prompt_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)  # 租户 ID
    name: Mapped[str] = mapped_column(String(255))  # 测试名称
    prompt_key: Mapped[str] = mapped_column(String(128))  # 被测试的提示词 key / 类型
    # 对照组变体模板 ID
    variant_a_id: Mapped[Optional[int]] = mapped_column(ForeignKey("prompt_templates.id", ondelete="SET NULL"))
    # 实验组变体模板 ID
    variant_b_id: Mapped[Optional[int]] = mapped_column(ForeignKey("prompt_templates.id", ondelete="SET NULL"))
    # 分流到变体 B 的流量百分比 (0-100)
    traffic_split_b: Mapped[float] = mapped_column(Float, default=50.0)
    # 状态: draft / running / completed
    status: Mapped[str] = mapped_column(String(32), default="draft")
    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime)  # 测试开始时间
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime)  # 测试结束时间
    winner: Mapped[Optional[str]] = mapped_column(String(8))  # 胜出变体: a / b / None
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    # 关系：一个测试对应多条结果记录
    results = relationship("PromptABTestResult", back_populates="test", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<PromptABTest(id={self.id}, name='{self.name}', status='{self.status}')>"


class PromptABTestResult(Base):
    """A/B 测试单次结果记录 — 每次渲染/反馈生成一条，用于聚合对比变体表现."""
    __tablename__ = "prompt_ab_test_results"
    __table_args__ = (
        Index("ix_prompt_ab_test_result_test_variant", "test_id", "variant"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    test_id: Mapped[int] = mapped_column(ForeignKey("prompt_ab_tests.id", ondelete="CASCADE"), index=True)
    variant: Mapped[str] = mapped_column(String(8))  # 命中的变体: a / b
    session_id: Mapped[Optional[str]] = mapped_column(String(128), index=True)  # 触发本次渲染的会话 ID
    # 用户反馈: thumbs_up / thumbs_down / None
    user_feedback: Mapped[Optional[str]] = mapped_column(String(32))
    response_quality_score: Mapped[Optional[float]] = mapped_column(Float)  # 质量评分 (0-1)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)  # 响应延迟（毫秒）
    token_count: Mapped[int] = mapped_column(Integer, default=0)  # token 消耗
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 关系
    test = relationship("PromptABTest", back_populates="results")

    def __repr__(self) -> str:
        return f"<PromptABTestResult(id={self.id}, test_id={self.test_id}, variant='{self.variant}')>"


class FewShotExample(Base):
    """Few-shot 示例样本 — 按 prompt_key 分组，渲染时按 quality_score 取 Top-N 注入提示词."""
    __tablename__ = "prompt_few_shot_examples"
    __table_args__ = (
        Index("ix_few_shot_tenant_key", "tenant_id", "prompt_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)  # 租户 ID
    prompt_key: Mapped[str] = mapped_column(String(128))  # 所属提示词 key / 类型
    input_text: Mapped[str] = mapped_column(Text)  # 示例输入
    output_text: Mapped[str] = mapped_column(Text)  # 期望输出
    # 示例分类，如 financial_query / report_gen
    category: Mapped[Optional[str]] = mapped_column(String(64))
    # 质量评分 (0-1)，越高越优先选取
    quality_score: Mapped[float] = mapped_column(Float, default=0.5)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # 是否启用
    display_order: Mapped[int] = mapped_column(Integer, default=0)  # 展示顺序（同分时排序用）
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    def __repr__(self) -> str:
        return f"<FewShotExample(id={self.id}, key='{self.prompt_key}', score={self.quality_score})>"


class Skill(Base):
    """技能 — 面向特定场景的 Agent 能力组合（一组工具 + 提示词）."""
    __tablename__ = "skills"
    __table_args__ = (
        Index("ix_skill_tenant_category", "tenant_id", "category"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(128))  # 技能标识名
    display_name: Mapped[str] = mapped_column(String(128))  # 展示名称
    description: Mapped[Optional[str]] = mapped_column(Text)  # 技能描述
    # 分类：财报分析/风险评估/指标计算等
    category: Mapped[Optional[str]] = mapped_column(String(64))
    # 关联的提示词模板 ID
    prompt_id: Mapped[Optional[int]] = mapped_column(ForeignKey("prompt_templates.id", ondelete="SET NULL"))
    # 覆盖关联模板的 system prompt（可选）
    system_prompt_override: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # 是否启用
    icon: Mapped[Optional[str]] = mapped_column(String(32))  # 图标标识
    # 关联工具 ID 列表（JSON 数组）
    tool_ids: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Skill(id={self.id}, name='{self.name}', category='{self.category}')>"


class Tool(Base):
    """工具注册表 — Agent 可调用的工具（内置 built-in / 自定义 custom）."""
    __tablename__ = "tools"
    __table_args__ = (
        Index("ix_tool_tenant_type", "tenant_id", "type"),
        Index("ix_tool_tenant_builtin", "tenant_id", "is_builtin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(128))  # 工具内部名称，唯一标识
    display_name: Mapped[str] = mapped_column(String(128))  # 展示名称
    description: Mapped[Optional[str]] = mapped_column(Text)  # 工具描述
    # 工具类型: python_function/http_api/sql_query/file_operation/search/web_search
    type: Mapped[str] = mapped_column(String(32))
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否内置工具（不可删除）
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # 是否启用
    # 工具配置 JSON（结构按 type 不同有各自 schema）：
    #   python_function: {code, entry_function, parameters: [...]}
    #   http_api: {url, method, headers, body_template, parameters: [...]}
    #   sql_query: {query_template, parameters: [...]}
    #   search: {search_engine, api_key, max_results}
    #   web_search: {engine, api_key, region, safe_search}
    config: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    # API Key（用于 search/web_search 类型；FinPilot 暂无加密类型层，加密由 Service 层处理）
    api_key: Mapped[Optional[str]] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Tool(id={self.id}, name='{self.name}', type='{self.type}')>"


class RuntimeLog(Base):
    """运行记录表 — 统一记录 API 调用、LLM 调用、Agent 执行、文档解析等运行事件.

    用于"设置板块内置日志与运行轨迹模块"，完整留存每一次 API 调用记录、
    所有问答交互内容，以及各功能模块的启用状态，实现对全流程运行状态的实时监测。
    """
    __tablename__ = "runtime_logs"
    __table_args__ = (
        Index("ix_runtime_logs_tenant_cat", "tenant_id", "category"),
        Index("ix_runtime_logs_created", "created_at"),
        Index("ix_runtime_logs_source", "source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    # 日志分类：api_call / llm_call / agent_run / document_parse / sandbox_exec / chat_message / system
    category: Mapped[str] = mapped_column(String(32))
    # 级别：info / warn / error / debug
    level: Mapped[str] = mapped_column(String(16), default="info")
    # 来源模块（如 agent.chat_stream / llm.client / sandbox.execute / documents.upload）
    source: Mapped[str] = mapped_column(String(64), default="")
    # 事件名（如 chat_request / llm_response / parse_complete / exec_finished）
    event: Mapped[str] = mapped_column(String(128), default="")
    # 简要消息
    message: Mapped[Optional[str]] = mapped_column(Text)
    # 完整结构化载荷（JSON 字符串），可包含请求/响应快照、token 数、耗时、退出码等
    payload_json: Mapped[Optional[str]] = mapped_column(Text)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)  # 耗时（毫秒）
    status_code: Mapped[Optional[int]] = mapped_column(Integer)  # HTTP 状态码或退出码
    user_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    session_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)  # 关联会话/追踪 ID
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return (
            f"<RuntimeLog(id={self.id}, category='{self.category}', "
            f"event='{self.event}', success={self.success})>"
        )
