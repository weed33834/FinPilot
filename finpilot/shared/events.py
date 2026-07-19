"""跨服务共享事件定义.

定义领域事件的数据结构，用于服务间解耦通信。
当前同步调用，预留给消息总线用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass
class DomainEvent:
    """领域事件基类."""

    event_id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = ""
    tenant_id: str | None = None
    user_id: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }


@dataclass
class ReportGeneratedEvent(DomainEvent):
    """报告生成完成事件."""

    event_type: str = "report.generated"

    @property
    def report_id(self) -> str:
        return self.payload.get("report_id", "")


@dataclass
class DocumentParsedEvent(DomainEvent):
    """文档解析完成事件."""

    event_type: str = "document.parsed"

    @property
    def document_id(self) -> str:
        return self.payload.get("document_id", "")


@dataclass
class ApprovalCompletedEvent(DomainEvent):
    """审批完成事件."""

    event_type: str = "approval.completed"

    @property
    def report_id(self) -> str:
        return self.payload.get("report_id", "")

    @property
    def action(self) -> str:
        return self.payload.get("action", "")
