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


class TenantMixin:
    """多租户混入类 — 为模型提供统一的 tenant_id 字段。

    所有需要租户隔离的模型应同时继承 Base 和本 Mixin。
    查询时由 tenant_filter 模块的 do_orm_execute 事件自动注入 tenant_id 条件。
    """
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)


class User(Base):
    """用户表 - 平台用户账号"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255))
    name: Mapped[Optional[str]] = mapped_column(String(100))
    # 角色：支持 5 种角色 — admin / finance_manager / analyst / auditor / viewer，默认 analyst
    role: Mapped[str] = mapped_column(String(50), default="analyst")
    # 2FA TOTP 支持
    totp_secret: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 关系：一个用户拥有多个会话、API密钥、上传的文档
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="uploader")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}')>"


class Document(Base, TenantMixin):
    """文档表 - 用户上传的财务文档"""
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(500))
    file_type: Mapped[Optional[str]] = mapped_column(String(50))  # pdf/docx/xlsx/csv
    file_path: Mapped[str] = mapped_column(String(1000))
    file_size: Mapped[Optional[int]] = mapped_column(Integer)
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


class DocumentChunk(Base, TenantMixin):
    """文档分块表 - RAG 向量检索的最小单元"""
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    # embedding 存储为 JSON 字符串（向量序列化），SQLite 下用 Text 承载
    embedding: Mapped[Optional[str]] = mapped_column(Text)
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


class FinancialReport(Base, TenantMixin):
    """财务报表表 - 资产负债表/利润表/现金流量表等.

    document_id 溯源到用户上传的文档，使 text2sql 查询结果与上传内容挂钩。
    """
    __tablename__ = "financial_reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    report_name: Mapped[str] = mapped_column(String(200))
    company_name: Mapped[Optional[str]] = mapped_column(String(200))
    ticker: Mapped[Optional[str]] = mapped_column(String(50))
    report_type: Mapped[str] = mapped_column(String(50))  # balance_sheet/income_statement/cash_flow
    period: Mapped[Optional[str]] = mapped_column(String(50))  # 如 2024-Q1 / 2024-FY
    # data_json 存储报表的原始 JSON 数据，便于灵活扩展
    data_json: Mapped[Optional[str]] = mapped_column(Text)
    # 溯源到上传文档（文档解析抽取结构化报表时写入）
    document_id: Mapped[Optional[int]] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 关系
    accounts = relationship("FinancialAccount", back_populates="report", cascade="all, delete-orphan")
    document = relationship("Document", backref="financial_reports")

    def __repr__(self) -> str:
        return f"<FinancialReport(id={self.id}, name='{self.report_name}', type='{self.report_type}')>"


class Report(Base, TenantMixin):
    """研报表 — 用户通过前端 ReportsPage 创建的财务分析报告.

    与 FinPilot equity 的 ReportRequest（研报生成管线）不同，本表存储的是
    基于已有财务数据的即时分析报告，字段与前端 ``types/report.ts`` 中的
    ``Report`` 接口对齐。
    """
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
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
    # 溯源：报告基于哪些文档/数据连接/模板生成
    document_id: Mapped[Optional[int]] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), index=True)
    data_connection_id: Mapped[Optional[int]] = mapped_column(ForeignKey("data_connections.id", ondelete="SET NULL"), index=True)
    template_id: Mapped[Optional[int]] = mapped_column(ForeignKey("report_templates.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    # 关系
    document = relationship("Document", foreign_keys=[document_id])
    data_connection = relationship("DataConnection", foreign_keys=[data_connection_id])
    template = relationship("ReportTemplate", foreign_keys=[template_id])
    approvals = relationship("Approval", back_populates="report", cascade="all, delete-orphan")


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


class Conversation(Base, TenantMixin):
    """会话表 - 用户与AI的对话会话"""
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    title: Mapped[Optional[str]] = mapped_column(String(500))    # 是否归档：前端 ConversationsPage 按此分桶（active/archived）
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # 绑定的 Agent 配置（运行时按此配置实例化 agent）
    agent_config_id: Mapped[Optional[int]] = mapped_column(ForeignKey("agent_configs.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    # 关系
    user = relationship("User", back_populates="conversations")
    agent_config = relationship("AgentConfig", backref="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, title='{self.title}')>"


class Message(Base):
    """消息表 - 会话中的单条消息.

    扩展 LLM 运行时元数据（model_name/tokens/latency/tool_calls），
    用于会话维度的成本聚合与调用追溯。
    """
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String(20))  # user/assistant/system
    content: Mapped[str] = mapped_column(Text)
    # LLM 运行时元数据（仅 assistant 消息填充）
    model_name: Mapped[Optional[str]] = mapped_column(String(200))
    tokens_in: Mapped[Optional[int]] = mapped_column(Integer)
    tokens_out: Mapped[Optional[int]] = mapped_column(Integer)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    tool_calls: Mapped[Optional[str]] = mapped_column(Text)  # JSON 数组：调用的工具列表
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 关系
    conversation = relationship("Conversation", back_populates="messages")

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, role='{self.role}')>"


class AuditLog(Base, TenantMixin):
    """审计日志表 - 记录 LLM 调用与安全事件（迁移自 legacy audit_service）.

    落库内容经 PII 脱敏，不存明文敏感信息。用于合规追溯、注入攻击取证、
    调用量统计。tenant_id / user_id 缺失时记为 None / 匿名。

    target_object_type/target_object_id 支持结构化关联业务对象
    （report/document/query/subscription/user 等），便于按对象反查审计历史。
    """
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_target", "target_object_type", "target_object_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 事件类型：llm_call / injection_blocked / login / document_upload / report_create / approval / query_exec 等
    action: Mapped[str] = mapped_column(String(50), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    # 结果：ok / blocked / error
    status: Mapped[str] = mapped_column(String(20), default="ok")
    # 脱敏后的输入摘要（PII 已替换为占位符）
    detail: Mapped[Optional[str]] = mapped_column(Text)
    # 结构化元数据 JSON（模型名、耗时、威胁分等）
    meta_json: Mapped[Optional[str]] = mapped_column(Text)
    # 业务对象关联（结构化）：report / document / query / subscription / user / agent_config / data_connection 等
    target_object_type: Mapped[Optional[str]] = mapped_column(String(32))
    target_object_id: Mapped[Optional[str]] = mapped_column(String(64))
    # 操作资源描述（前端 audit.ts 期望的 resource 字段）
    resource: Mapped[Optional[str]] = mapped_column(String(255))
    # 来源 IP
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action='{self.action}', status='{self.status}')>"


class ApiKey(Base, TenantMixin):
    """API 密钥表 - 用户访问平台的密钥.

    扩展字段（板块C）：tenant_id 隔离、expires_at 过期、usage_count/first_used_at
    调用统计、rotated_from 轮换溯源、updated_at。
    """
    __tablename__ = "api_keys"
    __table_args__ = (
        Index("ix_api_keys_tenant_active", "tenant_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    key_hash: Mapped[str] = mapped_column(String(255))  # 密钥哈希值
    # 明文前缀（如 fp_live_a1b2c3d4），用于列表展示识别，不泄露完整密钥
    key_prefix: Mapped[Optional[str]] = mapped_column(String(32))
    name: Mapped[Optional[str]] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    scopes: Mapped[Optional[str]] = mapped_column(Text, default="", comment="逗号分隔的权限范围")
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    first_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    # 轮换溯源：新 Key 指向被轮换的旧 Key id
    rotated_from: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

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


class McpServerConfig(Base, TenantMixin):
    """MCP 服务器配置 — 连接外部 MCP 服务器."""
    __tablename__ = "mcp_server_configs"
    __table_args__ = (
        Index("ix_mcp_tenant_active", "tenant_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
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


class ReportSubscription(Base, TenantMixin):
    """定时报告订阅 — 按 daily/weekly/monthly 频率自动生成报告并推送."""
    __tablename__ = "report_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
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
    # 上次生成的报告 ID（FK 到 reports）
    last_report_id: Mapped[Optional[int]] = mapped_column(ForeignKey("reports.id", ondelete="SET NULL"))
    last_error: Mapped[Optional[str]] = mapped_column(Text)  # 上次执行错误信息
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    def __repr__(self) -> str:
        return f"<ReportSubscription(id={self.id}, name='{self.name}', freq='{self.frequency}')>"


class ReportTemplate(Base, TenantMixin):
    """持久化的报告模板 — 覆盖内置模板渲染逻辑."""
    __tablename__ = "report_templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
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


class SandboxConfig(Base, TenantMixin):
    """沙箱配置 — SQL 白名单 + 代码沙箱配置."""
    __tablename__ = "sandbox_configs"
    __table_args__ = (
        Index("ix_sandbox_tenant_type", "tenant_id", "config_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)    # 配置类型: sql_whitelist / code_sandbox / file_upload
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


class SandboxExecution(Base, TenantMixin):
    """沙箱执行记录 — 持久化每次代码执行的输入输出.

    用于审计、调试、回放，以及前端"执行历史"展示。
    """
    __tablename__ = "sandbox_executions"
    __table_args__ = (
        Index("ix_sandbox_exec_tenant_config", "tenant_id", "config_id"),
        Index("ix_sandbox_exec_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
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


class PromptTemplate(Base, TenantMixin):
    """可复用的提示词模板 — 支持 {variable} 占位符."""
    __tablename__ = "prompt_templates"
    __table_args__ = (
        Index("ix_prompt_tenant_type", "tenant_id", "template_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
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


class PromptABTest(Base, TenantMixin):
    """提示词 A/B 测试配置 — 为同一 prompt_key 配置对照/实验变体并按流量分流."""
    __tablename__ = "prompt_ab_tests"
    __table_args__ = (
        Index("ix_prompt_ab_test_tenant_key", "tenant_id", "prompt_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True) # 租户 ID
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


class FewShotExample(Base, TenantMixin):
    """Few-shot 示例样本 — 按 prompt_key 分组，渲染时按 quality_score 取 Top-N 注入提示词."""
    __tablename__ = "prompt_few_shot_examples"
    __table_args__ = (
        Index("ix_few_shot_tenant_key", "tenant_id", "prompt_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True) # 租户 ID
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


class Skill(Base, TenantMixin):
    """技能 — 面向特定场景的 Agent 能力组合（一组工具 + 提示词）."""
    __tablename__ = "skills"
    __table_args__ = (
        Index("ix_skill_tenant_category", "tenant_id", "category"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
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


class Tool(Base, TenantMixin):
    """工具注册表 — Agent 可调用的工具（内置 built-in / 自定义 custom）."""
    __tablename__ = "tools"
    __table_args__ = (
        Index("ix_tool_tenant_type", "tenant_id", "type"),
        Index("ix_tool_tenant_builtin", "tenant_id", "is_builtin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
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


# ============================================================
# Phase 1 第四批新增模型：预算管理 + 日记账 + 科目表 + 发票
# ============================================================


class Account(Base, TenantMixin):
    """科目表 (Chart of Accounts) — 统一会计科目编码体系."""
    __tablename__ = "accounts"
    __table_args__ = (
        Index("ix_accounts_tenant_code", "tenant_id", "code", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32))          # 科目编码，如 1001/2202
    name: Mapped[str] = mapped_column(String(128))         # 科目名称
    category: Mapped[str] = mapped_column(String(32))      # 资产/负债/权益/收入/费用
    sub_category: Mapped[Optional[str]] = mapped_column(String(64))  # 明细分类
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, default=None)  # 上级科目
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 关系：科目下的日记账分录
    journal_entries = relationship("JournalEntry", back_populates="account")

    def __repr__(self) -> str:
        return f"<Account(id={self.id}, code='{self.code}', name='{self.name}')>"


class JournalEntry(Base, TenantMixin):
    """日记账分录表 — 复式记账的每笔分录."""
    __tablename__ = "journal_entries"
    __table_args__ = (
        Index("ix_journal_entries_tenant_date", "tenant_id", "entry_date"),
        Index("ix_journal_entries_tenant_account", "tenant_id", "account_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    entry_date: Mapped[datetime] = mapped_column(DateTime, index=True)
    account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    description: Mapped[Optional[str]] = mapped_column(String(500))
    debit_amount: Mapped[float] = mapped_column(Float, default=0.0)
    credit_amount: Mapped[float] = mapped_column(Float, default=0.0)
    reference: Mapped[Optional[str]] = mapped_column(String(128))  # 凭证编号
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 关系
    account = relationship("Account", back_populates="journal_entries")

    def __repr__(self) -> str:
        return (f"<JournalEntry(id={self.id}, date='{self.entry_date}', "
                f"debit={self.debit_amount}, credit={self.credit_amount})>")


class Invoice(Base, TenantMixin):
    """发票/票据表 — 应收账款与应付账款管理."""
    __tablename__ = "invoices"
    __table_args__ = (
        Index("ix_invoices_tenant_status", "tenant_id", "status"),
        Index("ix_invoices_tenant_due", "tenant_id", "due_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    invoice_number: Mapped[str] = mapped_column(String(64))      # 发票号
    invoice_type: Mapped[str] = mapped_column(String(16), default="receivable")  # receivable/payable
    vendor: Mapped[Optional[str]] = mapped_column(String(200))    # 供应商/客户
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    tax_amount: Mapped[float] = mapped_column(Float, default=0.0)
    total_amount: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/paid/overdue/cancelled
    issue_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    paid_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<Invoice(id={self.id}, number='{self.invoice_number}', status='{self.status}')>"


class Budget(Base, TenantMixin):
    """预算主表 — 年度/部门预算头信息."""
    __tablename__ = "budgets"
    __table_args__ = (
        Index("ix_budgets_tenant_year", "tenant_id", "year"),
        Index("ix_budgets_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))              # 预算名称
    year: Mapped[int] = mapped_column(Integer)                  # 预算年份
    department: Mapped[Optional[str]] = mapped_column(String(100))  # 部门
    total_amount: Mapped[float] = mapped_column(Float, default=0.0)  # 预算总额
    status: Mapped[str] = mapped_column(String(32), default="draft")  # draft/pending/approved/rejected
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    reject_reason: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    items = relationship("BudgetItem", back_populates="budget", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Budget(id={self.id}, name='{self.name}', year={self.year}, status='{self.status}')>"


class BudgetItem(Base, TenantMixin):
    """预算明细项 — 预算的具体科目行项."""
    __tablename__ = "budget_items"
    __table_args__ = (
        Index("ix_budget_items_budget", "budget_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    budget_id: Mapped[int] = mapped_column(ForeignKey("budgets.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(64))           # 科目类别
    description: Mapped[Optional[str]] = mapped_column(String(500))  # 明细说明
    amount: Mapped[float] = mapped_column(Float, default=0.0)   # 预算金额
    account_code: Mapped[Optional[str]] = mapped_column(String(32))  # 关联科目编码
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    budget = relationship("Budget", back_populates="items")

    def __repr__(self) -> str:
        return f"<BudgetItem(id={self.id}, budget_id={self.budget_id}, category='{self.category}')>"


class BalanceSheet(Base, TenantMixin):
    """资产负债表 — 三表审计关系核心表之一."""
    __tablename__ = "balance_sheets"
    __table_args__ = (
        Index("ix_balance_sheets_tenant_period", "tenant_id", "period_end"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    period_end: Mapped[datetime] = mapped_column(DateTime, index=True)  # 报表截止日期
    total_assets: Mapped[float] = mapped_column(Float, default=0.0)
    current_assets: Mapped[float] = mapped_column(Float, default=0.0)
    non_current_assets: Mapped[float] = mapped_column(Float, default=0.0)
    total_liabilities: Mapped[float] = mapped_column(Float, default=0.0)
    current_liabilities: Mapped[float] = mapped_column(Float, default=0.0)
    non_current_liabilities: Mapped[float] = mapped_column(Float, default=0.0)
    total_equity: Mapped[float] = mapped_column(Float, default=0.0)
    retained_earnings: Mapped[float] = mapped_column(Float, default=0.0)  # 留存收益（用于净利润勾稽）
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<BalanceSheet(id={self.id}, period_end='{self.period_end}')>"


class IncomeStatement(Base, TenantMixin):
    """利润表 — 三表审计关系核心表之二."""
    __tablename__ = "income_statements"
    __table_args__ = (
        Index("ix_income_statements_tenant_period", "tenant_id", "period_end"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    period_end: Mapped[datetime] = mapped_column(DateTime, index=True)
    revenue: Mapped[float] = mapped_column(Float, default=0.0)
    operating_cost: Mapped[float] = mapped_column(Float, default=0.0)
    gross_profit: Mapped[float] = mapped_column(Float, default=0.0)
    operating_expenses: Mapped[float] = mapped_column(Float, default=0.0)
    operating_income: Mapped[float] = mapped_column(Float, default=0.0)
    net_income: Mapped[float] = mapped_column(Float, default=0.0)  # 净利润（用于三表勾稽）
    eps: Mapped[float] = mapped_column(Float, default=0.0)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<IncomeStatement(id={self.id}, period_end='{self.period_end}')>"


class CashFlowStatement(Base, TenantMixin):
    """现金流量表 — 三表审计关系核心表之三."""
    __tablename__ = "cash_flow_statements"
    __table_args__ = (
        Index("ix_cash_flow_statements_tenant_period", "tenant_id", "period_end"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    period_end: Mapped[datetime] = mapped_column(DateTime, index=True)
    operating_activities: Mapped[float] = mapped_column(Float, default=0.0)  # 经营活动现金流净额
    investing_activities: Mapped[float] = mapped_column(Float, default=0.0)
    financing_activities: Mapped[float] = mapped_column(Float, default=0.0)
    net_cash_change: Mapped[float] = mapped_column(Float, default=0.0)  # 现金净增减
    beginning_cash: Mapped[float] = mapped_column(Float, default=0.0)  # 期初现金
    ending_cash: Mapped[float] = mapped_column(Float, default=0.0)  # 期末现金
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<CashFlowStatement(id={self.id}, period_end='{self.period_end}')>"


class RuntimeLog(Base, TenantMixin):
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

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)    # 日志分类：api_call / llm_call / agent_run / document_parse / sandbox_exec / chat_message / system
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


class AssumptionSet(Base):
    """三表联动的外部化假设参数集。"""
    __tablename__ = "assumption_sets"
    __table_args__ = (
        Index("ix_assumption_sets_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    name: Mapped[str] = mapped_column(String(128))
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    periods: Mapped[int] = mapped_column(Integer, default=4)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return (
            f"<AssumptionSet(id={self.id}, name='{self.name}', "
            f"periods={self.periods})>"
        )


class DataConnection(Base, TenantMixin):
    """数据连接 — 外部数据源连接配置（API Key / 数据库 / SFTP / S3 / 自定义）。

    config 字段为 JSON，存储连接参数。密钥字段（client_secret / api_key /
    password / secret_key / access_key 等）在 API 返回时一律替换为
    ``***REDACTED***`` 占位符。
    """
    __tablename__ = "data_connections"
    __table_args__ = (
        Index("ix_data_connections_tenant_type", "tenant_id", "connection_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))                    # 连接名称
    connection_type: Mapped[str] = mapped_column(String(32))          # api_key / database / sftp / s3 / custom
    config: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)  # 连接参数 JSON
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    def __repr__(self) -> str:
        return (
            f"<DataConnection(id={self.id}, name='{self.name}', "
            f"type='{self.connection_type}')>"
        )


class AgentConfig(Base, TenantMixin):
    """智能体配置 — 管理后台 Dashboard 中展示的 Agent 配置项。

    用于定义每个租户下可用的 AI Agent 实例。Agent 可以绑定特定的 LLM 模型、
    工具集、技能集和系统提示词，实现不同业务场景的差异化智能体行为。
    """
    __tablename__ = "agent_configs"
    __table_args__ = (
        Index("ix_agent_configs_tenant_active", "tenant_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))                  # Agent 名称
    display_name: Mapped[str] = mapped_column(String(128))          # 展示名称
    description: Mapped[Optional[str]] = mapped_column(Text)       # 描述
    # 绑定的 LLM 模型 ID
    model_id: Mapped[Optional[int]] = mapped_column(ForeignKey("llm_models.id", ondelete="SET NULL"))
    # 系统提示词
    system_prompt: Mapped[Optional[str]] = mapped_column(Text)
    # 关联的工具 ID 列表（JSON 数组）
    tool_ids: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    # 关联的技能 ID 列表（JSON 数组）
    skill_ids: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    def __repr__(self) -> str:
        return f"<AgentConfig(id={self.id}, name='{self.name}', active={self.is_active})>"


class ModelConfig(Base, TenantMixin):
    """模型配置 — 管理后台 Dashboard 中展示的 LLM 模型配置项。

    独立于 LlmProvider/LlmModel 的轻量级模型配置表，用于 Dashboard 统计和
    快速模型开关管理。与 llm_providers/llm_models 分工不同：后者是实际调用
    链路中使用的详细配置，本表是面向管理员的简化配置入口。
    """
    __tablename__ = "model_configs"
    __table_args__ = (
        Index("ix_model_configs_tenant_active", "tenant_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))                  # 配置名称
    model_name: Mapped[str] = mapped_column(String(200))            # 模型标识（如 gpt-4o）
    provider: Mapped[Optional[str]] = mapped_column(String(100))    # 供应商（openai/anthropic 等）
    # 关联的 LLM Provider 模型
    llm_model_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("llm_models.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)   # 是否默认模型
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    def __repr__(self) -> str:
        return (
            f"<ModelConfig(id={self.id}, model='{self.model_name}', "
            f"active={self.is_active})>"
        )


class SearchEngine(Base):
    """搜索引擎配置 — 管理后台 Dashboard 中展示的搜索引擎配置项。

    管理 Agent 可用的外部搜索服务（自定义搜索、Web 搜索等），支持多种搜索引擎
    后端（Google/Bing/自定义 API），统一管理 API Key 和搜索参数。
    """
    __tablename__ = "search_engines"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))                  # 引擎名称
    engine_type: Mapped[str] = mapped_column(String(32), default="custom")   # google/bing/custom
    base_url: Mapped[Optional[str]] = mapped_column(String(500))    # API 基础 URL
    api_key: Mapped[Optional[str]] = mapped_column(String(1000))    # API 密钥
    max_results: Mapped[int] = mapped_column(Integer, default=10)   # 单次搜索最大结果数
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    def __repr__(self) -> str:
        return (
            f"<SearchEngine(id={self.id}, name='{self.name}', "
            f"type='{self.engine_type}', active={self.is_active})>"
        )


# ============================================================
# 因果链条修复：独立审批表 + text2sql 查询记录
# ============================================================


class Approval(Base, TenantMixin):
    """审批记录表 — 独立于 Report.status 的结构化审批历史.

    每次审批动作（approve/reject/request_changes）落一条记录，
    持久化审批人身份、意见、时间，支持完整审批历史追溯。
    target_object_type 扩展支持 report/budget/data_connection 等多业务对象。
    """
    __tablename__ = "approvals"
    __table_args__ = (
        Index("ix_approvals_tenant_target", "tenant_id", "target_object_type", "target_object_id"),
        Index("ix_approvals_tenant_action", "tenant_id", "action"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 审批对象类型：report / budget / data_connection / agent_config 等
    target_object_type: Mapped[str] = mapped_column(String(32), default="report")
    # 审批对象 ID（多数情况为 report.id）
    target_object_id: Mapped[int] = mapped_column(Integer, index=True)
    # 反向关联 Report（target_object_type='report' 时使用）
    report_id: Mapped[Optional[int]] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    # 审批人
    reviewer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    reviewer_name: Mapped[Optional[str]] = mapped_column(String(100))
    # 审批动作：approve / reject / request_changes
    action: Mapped[str] = mapped_column(String(32))
    # 审批意见
    comments: Mapped[Optional[str]] = mapped_column(Text)
    # 审批前状态 → 审批后状态
    prev_status: Mapped[Optional[str]] = mapped_column(String(32))
    new_status: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 关系
    report = relationship("Report", back_populates="approvals")

    def __repr__(self) -> str:
        return (
            f"<Approval(id={self.id}, target='{self.target_object_type}:"
            f"{self.target_object_id}', action='{self.action}')>"
        )


class QueryRecord(Base, TenantMixin):
    """text2sql 查询记录表 — 持久化每次自然语言查询的全链路上下文.

    保存 question/sql/rows/confidence/engine，支持查询回放、失败统计、
    审计追溯。与 RuntimeLog 互补：RuntimeLog 记运行事件，本表记业务查询语义。
    """
    __tablename__ = "query_records"
    __table_args__ = (
        Index("ix_query_records_tenant_created", "tenant_id", "created_at"),
        Index("ix_query_records_tenant_conv", "tenant_id", "conversation_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    conversation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"), index=True)
    # 用户自然语言问题
    question: Mapped[str] = mapped_column(Text)
    # 识别的意图
    intent: Mapped[Optional[str]] = mapped_column(String(64))
    # 生成的 SQL
    sql_text: Mapped[Optional[str]] = mapped_column(Text)
    # 执行引擎：rule / llm
    engine: Mapped[Optional[str]] = mapped_column(String(16))
    # 规则引擎置信度
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    # 执行结果（JSON 序列化，截断到合理大小）
    rows_json: Mapped[Optional[str]] = mapped_column(Text)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    # 执行状态：success / failed / blocked
    status: Mapped[str] = mapped_column(String(16), default="success")
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    # 耗时（毫秒）
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return (
            f"<QueryRecord(id={self.id}, status='{self.status}', "
            f"rows={self.row_count})>"
        )


# ============================================================
# 板块C 新增模型：补齐前端 404 页面对应的后端数据模型.
#
# - AccessPolicy: ABAC 访问策略（访问策略页）
# - HitlRequest:  Human-in-the-loop 人工介入请求（HITL 页）
# - EvalRecord:   NL2SQL / RAG 评估记录（评估管理页）
# - ReflectionLog: 错误自省日志（自省页）
# ============================================================


class AccessPolicy(Base, TenantMixin):
    """ABAC 访问策略 — 基于资源类型 + 动作 + 条件的访问控制.

    优先级数字越小越先匹配；effect=allow/deny。
    conditions 为 JSON（如 {"role": "auditor"}），可空。
    """
    __tablename__ = "access_policies"
    __table_args__ = (
        Index("ix_access_policies_tenant_resource", "tenant_id", "resource_type", "action"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    # 资源类型：report / document / audit / approval / user / api_key
    resource_type: Mapped[str] = mapped_column(String(64))
    # 动作：read / write / delete / export / approve
    action: Mapped[str] = mapped_column(String(64))
    # 效果：allow / deny
    effect: Mapped[str] = mapped_column(String(16), default="allow")
    # 优先级：数字越小越先匹配
    priority: Mapped[int] = mapped_column(Integer, default=100)
    # 条件 JSON（可空），如 {"role": "auditor"}
    conditions: Mapped[Optional[dict]] = mapped_column(JSON)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    def __repr__(self) -> str:
        return (
            f"<AccessPolicy(id={self.id}, name='{self.name}', "
            f"{self.resource_type}:{self.action}={self.effect})>"
        )


class HitlRequest(Base, TenantMixin):
    """Human-in-the-loop 人工介入请求 — 高风险动作需人工审批后执行.

    status: pending / approved / rejected
    risk_level: low / medium / high
    action_type: 触发 HITL 的动作类型（如 tool_call / report_export / data_delete）
    """
    __tablename__ = "hitl_requests"
    __table_args__ = (
        Index("ix_hitl_tenant_status", "tenant_id", "status"),
        Index("ix_hitl_tenant_risk", "tenant_id", "risk_level"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 动作类型
    action_type: Mapped[str] = mapped_column(String(64))
    # 人类可读描述
    description: Mapped[Optional[str]] = mapped_column(Text)
    # 风险等级：low / medium / high
    risk_level: Mapped[str] = mapped_column(String(16), default="medium")
    # 动作参数（JSON）
    action_params: Mapped[Optional[dict]] = mapped_column(JSON)
    # 上下文（JSON，如会话/工具链快照）
    context: Mapped[Optional[dict]] = mapped_column(JSON)
    # 状态：pending / approved / rejected
    status: Mapped[str] = mapped_column(String(16), default="pending")
    # 请求人
    requested_by: Mapped[Optional[str]] = mapped_column(String(100))
    # 审批人
    resolved_by: Mapped[Optional[str]] = mapped_column(String(100))
    # 审批意见
    comment: Mapped[Optional[str]] = mapped_column(Text)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return (
            f"<HitlRequest(id={self.id}, action='{self.action_type}', "
            f"status='{self.status}', risk='{self.risk_level}')>"
        )


class EvalRecord(Base, TenantMixin):
    """评估记录 — NL2SQL / RAG 系统评估.

    eval_type: nl2sql / rag
    eval_method: 评估方法（如 llm_judge / exact_match / ragas）
    score: 评分（0-1 或 0-100，前端归一化）
    metrics: JSON，附加指标（如 mrr/ndcg/hit_rate for rag, sql_valid for nl2sql）
    """
    __tablename__ = "eval_records"
    __table_args__ = (
        Index("ix_eval_tenant_type", "tenant_id", "eval_type"),
        Index("ix_eval_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 评估类型：nl2sql / rag
    eval_type: Mapped[str] = mapped_column(String(16))
    # 评估问题
    question: Mapped[str] = mapped_column(Text)
    # 评估方法
    eval_method: Mapped[Optional[str]] = mapped_column(String(64))
    # 评分
    score: Mapped[float] = mapped_column(Float, default=0.0)
    # 附加指标 JSON
    metrics: Mapped[Optional[dict]] = mapped_column(JSON)
    # 评估详情（如生成 SQL、检索文档等）
    detail: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return (
            f"<EvalRecord(id={self.id}, type='{self.eval_type}', "
            f"score={self.score})>"
        )


class ReflectionLog(Base, TenantMixin):
    """错误自省日志 — 任务失败时记录异常、根因分析、修复建议.

    与 RuntimeLog 互补：RuntimeLog 记运行事件，本表记错误自省语义，
    支持 resolved 标记与 resolution 记录。
    error_category: retryable / business / config / security / unknown
    """
    __tablename__ = "reflection_logs"
    __table_args__ = (
        Index("ix_reflection_tenant_category", "tenant_id", "error_category"),
        Index("ix_reflection_tenant_resolved", "tenant_id", "resolved"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 任务名（如 agent.chat_stream / llm.client）
    task_name: Mapped[Optional[str]] = mapped_column(String(128))
    # 任务 ID / 追踪 ID
    task_id: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    # 资源类型与 ID（如 report:123）
    resource_type: Mapped[Optional[str]] = mapped_column(String(64))
    resource_id: Mapped[Optional[str]] = mapped_column(String(64))
    # 异常信息
    exception_type: Mapped[str] = mapped_column(String(255))
    exception_message: Mapped[str] = mapped_column(Text)
    stack_trace: Mapped[Optional[str]] = mapped_column(Text)
    # 错误分类：retryable / business / config / security / unknown
    error_category: Mapped[str] = mapped_column(String(32), default="unknown")
    # 根因分析与修复建议（best-effort，由自省服务填充）
    root_cause: Mapped[Optional[str]] = mapped_column(Text)
    suggested_fix: Mapped[Optional[str]] = mapped_column(Text)
    # 是否已重试
    retried: Mapped[bool] = mapped_column(Boolean, default=False)
    # 是否已解决
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    # 解决方案记录
    resolution: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return (
            f"<ReflectionLog(id={self.id}, type='{self.exception_type}', "
            f"category='{self.error_category}', resolved={self.resolved})>"
        )
