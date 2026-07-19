"""运行记录服务 — 统一记录 API 调用、LLM 调用、Agent 执行、文档解析等运行事件。

设计要点：
- best-effort 写入：失败不影响主流程
- 不依赖 request 上下文，可在任意位置调用
- 支持 payload（任意 dict），内部 JSON 序列化
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session

from finpilot.database.models import RuntimeLog

logger = logging.getLogger(__name__)


def log_runtime(
    db: Session | None = None,
    *,
    category: str,
    event: str,
    message: str = "",
    source: str = "",
    payload: dict[str, Any] | None = None,
    duration_ms: int = 0,
    status_code: int | None = None,
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    session_id: Optional[str] = None,
    success: bool = True,
    level: str = "info",
    commit: bool = True,
) -> Optional[int]:
    """记录一条运行日志。返回日志 ID（失败返回 None）。"""
    if db is None:
        return None
    try:
        payload_str: str | None = None
        if payload:
            try:
                payload_str = json.dumps(payload, ensure_ascii=False, default=str)[:16384]
            except (TypeError, ValueError):
                payload_str = None
        entry = RuntimeLog(
            tenant_id=tenant_id,
            category=category,
            level=level,
            source=source,
            event=event,
            message=(message or "")[:2000],
            payload_json=payload_str,
            duration_ms=duration_ms,
            status_code=status_code,
            user_id=user_id,
            ip_address=ip_address,
            session_id=session_id or str(uuid.uuid4()),
            success=success,
        )
        db.add(entry)
        if commit:
            db.commit()
            db.refresh(entry)
        return entry.id
    except Exception as exc:  # noqa: BLE001
        logger.warning("log_runtime failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return None


def new_session_id() -> str:
    """生成新的运行追踪会话 ID。"""
    return f"sess_{uuid.uuid4().hex[:16]}"
