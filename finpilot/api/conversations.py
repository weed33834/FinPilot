"""会话历史路由 — 用户视角的对话列表 / 详情 / 归档 / 删除 / 导出.

前端 ``ConversationsPage`` 期望：
- ``GET /conversations?archived=false&page=1&page_size=20``
  → ``{code, message, data: {items, total, page, page_size}}``
- ``GET /conversations/{id}`` → ``{code, message, data: ConversationDetail}``
- ``PUT /conversations/{id}`` body ``{is_archived: bool}`` → ``{code, message, data: Conversation}``
- ``DELETE /conversations/{id}`` → ``{code, message, data: {id, deleted}}``
- ``POST /conversations/{id}/export?format=markdown``
  → ``{code, message, data: {content: <markdown>}}``

Conversation ORM 已扩展 ``is_archived`` / ``updated_at`` 字段；老库通过本模块
导入时触发的 ``_ensure_columns`` 自动 ALTER TABLE 补齐。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session

from finpilot.api.deps import get_current_user, get_db_session
from finpilot.database.models import Conversation, Message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["Conversations"])


# ---------------------------------------------------------------------------
# 自动迁移：为旧库补充新列。SQLite 不支持 IF NOT EXISTS 的 ADD COLUMN，
# 用 inspect 检查后 ALTER。
# ---------------------------------------------------------------------------


def _ensure_columns() -> None:
    """若 conversations 表已存在但缺 is_archived / updated_at，则 ALTER 补齐."""
    try:
        from finpilot.database.connection import engine

        insp = inspect(engine)
        if not insp.has_table("conversations"):
            return
        existing = {c["name"] for c in insp.get_columns("conversations")}
        with engine.begin() as conn:
            if "is_archived" not in existing:
                conn.execute(
                    text(
                        "ALTER TABLE conversations ADD COLUMN is_archived BOOLEAN DEFAULT 0 NOT NULL"
                    )
                )
            if "updated_at" not in existing:
                conn.execute(
                    text("ALTER TABLE conversations ADD COLUMN updated_at DATETIME")
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("conversations_ensure_columns_failed err=%s", exc)


_ensure_columns()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ConversationUpdate(BaseModel):
    """会话更新请求（目前仅支持 is_archived）."""

    is_archived: bool | None = None
    title: str | None = None


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _conv_to_dict(c: Conversation, message_count: int | None = None) -> dict[str, Any]:
    """ORM -> dict（与前端 Conversation 接口对齐）."""
    return {
        "id": str(c.id),
        "title": c.title or "",
        "is_archived": bool(c.is_archived),
        "message_count": int(message_count) if message_count is not None else 0,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": (c.updated_at or c.created_at).isoformat()
        if (c.updated_at or c.created_at)
        else None,
    }


def _msg_to_dict(m: Message) -> dict[str, Any]:
    """Message ORM -> dict（前端 ConversationMessage）."""
    return {
        "id": str(m.id),
        "role": m.role,
        "content": m.content,
        "timestamp": m.created_at.isoformat() if m.created_at else None,
    }


def _conv_to_detail(c: Conversation, messages: list[Message]) -> dict[str, Any]:
    """ORM + messages -> ConversationDetail dict."""
    base = _conv_to_dict(c, message_count=len(messages))
    base["messages"] = [_msg_to_dict(m) for m in messages]
    return base


def _get_owned_conv(db: Session, conv_id: str, user_id: int) -> Conversation:
    """加载并校验当前用户拥有的会话."""
    try:
        cid = int(conv_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在"
        ) from exc
    conv = db.get(Conversation, cid)
    if not conv or conv.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return conv


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------


@router.get("")
def list_conversations(
    archived: bool = Query(default=False, description="true=仅归档，false=仅活跃"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """列出当前用户的会话（按 archived 分桶，按 updated_at 倒序）."""
    user_id = current_user["user_id"]
    base_q = db.query(Conversation).filter(
        Conversation.user_id == user_id,
        Conversation.is_archived.is_(bool(archived)),
    )
    total = base_q.count()
    items = (
        base_q.order_by(
            Conversation.updated_at.desc().nullslast(),
            Conversation.created_at.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    # 批量取 message_count
    counts = (
        db.query(Message.conversation_id, func.count(Message.id))
        .filter(Message.conversation_id.in_([c.id for c in items]))
        .group_by(Message.conversation_id)
        .all()
    )
    count_map = {cid: cnt for cid, cnt in counts}
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [_conv_to_dict(c, count_map.get(c.id, 0)) for c in items],
        },
    }


@router.get("/{conv_id}")
def get_conversation(
    conv_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """获取会话详情（含消息列表，按时间正序）."""
    conv = _get_owned_conv(db, conv_id, current_user["user_id"])
    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return {"code": 0, "message": "ok", "data": _conv_to_detail(conv, msgs)}


@router.put("/{conv_id}")
def update_conversation(
    conv_id: str,
    body: ConversationUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """更新会话（归档 / 取消归档 / 改标题）."""
    conv = _get_owned_conv(db, conv_id, current_user["user_id"])
    if body.is_archived is not None:
        conv.is_archived = bool(body.is_archived)
    if body.title is not None:
        conv.title = body.title
    conv.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(conv)
    msg_count = (
        db.query(func.count(Message.id))
        .filter(Message.conversation_id == conv.id)
        .scalar() or 0
    )
    return {"code": 0, "message": "ok", "data": _conv_to_dict(conv, msg_count)}


@router.delete("/{conv_id}")
def delete_conversation(
    conv_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """删除会话（含级联消息）."""
    conv = _get_owned_conv(db, conv_id, current_user["user_id"])
    cid = conv.id
    db.delete(conv)
    db.commit()
    return {"code": 0, "message": "ok", "data": {"id": str(cid), "deleted": True}}


@router.post("/{conv_id}/export", response_model=None)
def export_conversation(
    conv_id: str,
    format: str = Query(default="markdown", description="导出格式: markdown/json"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any] | Response:
    """导出会话为 Markdown / JSON."""
    conv = _get_owned_conv(db, conv_id, current_user["user_id"])
    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.created_at.asc())
        .all()
    )

    if format.lower() == "json":
        payload = {
            "id": str(conv.id),
            "title": conv.title,
            "messages": [_msg_to_dict(m) for m in msgs],
        }
        return {"code": 0, "message": "ok", "data": payload}

    # 默认 markdown
    lines = [f"# {conv.title or 'Conversation'}", ""]
    for m in msgs:
        role = "用户" if m.role == "user" else ("助手" if m.role == "assistant" else m.role)
        lines.append(f"## {role}")
        lines.append("")
        lines.append(m.content or "")
        lines.append("")
    md = "\n".join(lines)
    return {"code": 0, "message": "ok", "data": {"content": md, "format": "markdown"}}
