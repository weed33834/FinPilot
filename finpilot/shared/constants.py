"""跨服务共享常量."""

from __future__ import annotations

from enum import Enum


class ReportStatus(str, Enum):
    """报告状态."""

    PENDING = "pending"
    GENERATING = "generating"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"
    SUCCESS = "success"


class DocumentStatus(str, Enum):
    """文档解析状态."""

    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class TaskStatus(str, Enum):
    """异步任务状态."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


class AuditAction(str, Enum):
    """审计动作枚举."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    READ = "read"
    APPROVE = "approve"
    REJECT = "reject"
    EXPORT = "export"
    LOGIN = "login"
    LOGOUT = "logout"
    EXECUTE = "execute"


class AuditResult(str, Enum):
    """审计结果."""

    SUCCESS = "success"
    FAILED = "failed"
    DENIED = "denied"
    ERROR = "error"


# 事件主题名（用于消息总线 / 事件驱动架构预留）
EVENT_TOPIC_REPORT = "report.events"
EVENT_TOPIC_DOCUMENT = "document.events"
EVENT_TOPIC_APPROVAL = "approval.events"
EVENT_TOPIC_NOTIFICATION = "notification.events"
