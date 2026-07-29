# -*- coding: utf-8 -*-
"""``/context`` —— 上下文管理（板块D：占位补全 + 字段对齐 + 长期记忆持久化）。

本模块从原 ``compat.py`` 拆分而来，行为与原 ``context_router`` 完全一致。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func as _func
from sqlalchemy.orm import Session

from finpilot.database.models import Conversation, Memory, Message

from ._compat_helpers import ok, parse_int_id, tenant_of
from .deps import get_current_user, get_db_session

router = APIRouter(prefix="/context", tags=["context"])


def _estimate_tokens(text: str) -> int:
    """估算文本 token 数.

    按字符类型分别计数：CJK 字符 ≈ 1 token/字，其余 ≈ 1 token/4 字符（约 0.25/字符）。
    比此前 ``chars * 1.5`` 更贴合实际 tokenizer 行为。
    """
    if not text:
        return 0
    cjk = 0
    other = 0
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff" or "\u3000" <= ch <= "\u303f" or "\uff00" <= ch <= "\uffef":
            cjk += 1
        else:
            other += 1
    return cjk + max(other // 4, 0)


@router.post("/count-tokens")
def count_tokens(payload: dict, _: dict = Depends(get_current_user)):
    """计算文本 token 数.

    板块D：字段对齐前端 TokenCountResult —— token_count / char_count / model。
    此前返回 tokens/chars 导致前端 token_count 永远显示 0。
    """
    text = payload.get("text", "") or ""
    model = payload.get("model")
    chars = len(text)
    return ok({
        "token_count": _estimate_tokens(text),
        "char_count": chars,
        "model": model,
    })


@router.post("/optimize")
def optimize_context(payload: dict, _: dict = Depends(get_current_user)):
    """优化上下文 —— 保留 system_prompt，按 token 预算从末尾裁剪历史消息.

    板块D：字段对齐前端 OptimizeContextResult —— messages / system_prompt /
    estimated_tokens / truncated。此前原样返回 messages 且字段名错位。
    策略：预算 6000 token；保留 system_prompt 全文 + 最后若干条消息，
    超预算则从最早的消息开始丢弃，直到剩余 <= 预算。
    """
    messages = payload.get("messages", []) or []
    system_prompt = payload.get("system_prompt", "") or ""
    model = payload.get("model")  # noqa: F841  保留以备后续按模型分桶
    token_budget = 6000

    # system_prompt 占用
    system_tokens = _estimate_tokens(system_prompt)
    remaining_budget = max(token_budget - system_tokens, 0)

    # 倒序保留消息，超出预算的从最旧开始丢弃
    kept_reversed: list = []
    used = 0
    truncated = False
    for msg in reversed(messages):
        content = ""
        if isinstance(msg, dict):
            content = str(msg.get("content", ""))
        else:
            content = str(msg)
        t = _estimate_tokens(content)
        if used + t > remaining_budget:
            truncated = True
            break
        kept_reversed.append(msg)
        used += t

    optimized = list(reversed(kept_reversed))
    estimated_tokens = system_tokens + used
    return ok({
        "messages": optimized,
        "system_prompt": system_prompt,
        "estimated_tokens": estimated_tokens,
        "truncated": truncated,
    })


def _serialize_memory(m: Memory) -> dict:
    """Memory ORM → 前端 MemoryItem 字段."""
    return {
        "id": str(m.id),
        "user_id": m.user_id,
        "category": m.category,
        "content": m.content,
        "importance": m.importance,
        "source_conversation_id": m.source_conversation_id,
        "created_at": m.created_at.isoformat(sep=" ") if m.created_at else None,
        "updated_at": m.updated_at.isoformat(sep=" ") if m.updated_at else None,
    }


@router.get("/memories")
def list_memories(
    user_id: str = Query("", description="按用户 ID 筛选"),
    category: str = Query("", description="按分类筛选"),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """列出长期记忆.

    板块D：真实读取 memories 表。前端 getMemories 期望 data 为数组（非分页对象），
    故直接返回 [MemoryItem]。按重要性降序 + 创建时间降序，限制条数。
    """
    tenant_id = tenant_of(current_user)
    q = db.query(Memory).filter(Memory.tenant_id == tenant_id)
    if user_id:
        q = q.filter(Memory.user_id == user_id)
    if category:
        q = q.filter(Memory.category == category)
    rows = (
        q.order_by(Memory.importance.desc().nullslast(), Memory.created_at.desc())
        .limit(limit)
        .all()
    )
    return ok([_serialize_memory(m) for m in rows])


@router.post("/memories/search")
def search_memories(
    payload: dict,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """语义搜索长期记忆.

    板块D：基于 content LIKE 关键词搜索（无向量索引时的 best-effort）。
    前端 searchMemories 期望 data 为数组，故返回 [MemoryItem]。
    """
    query = (payload.get("query", "") or "").strip()
    tenant_id = tenant_of(current_user)
    q = db.query(Memory).filter(Memory.tenant_id == tenant_id)
    if query:
        q = q.filter(Memory.content.ilike(f"%{query}%"))
    rows = (
        q.order_by(Memory.importance.desc().nullslast(), Memory.created_at.desc())
        .limit(100)
        .all()
    )
    return ok([_serialize_memory(m) for m in rows])


@router.delete("/memories/{memory_id}")
def delete_memory(
    memory_id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """删除一条长期记忆.

    板块D：真实删除 memories 表记录。前端 deleteMemory 期望 data 为 {deleted: boolean}。
    """
    tenant_id = tenant_of(current_user)
    pk = parse_int_id(memory_id, "记忆")
    m = (
        db.query(Memory)
        .filter(Memory.id == pk, Memory.tenant_id == tenant_id)
        .first()
    )
    if not m:
        raise HTTPException(status_code=404, detail=f"记忆 {memory_id} 不存在")
    db.delete(m)
    db.commit()
    return ok({"deleted": True})


@router.get("/stats")
def context_stats(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """上下文使用统计.

    板块D：字段对齐前端 ContextStats —— total_memories / total_conversations /
    avg_tokens_per_conversation。此前返回 total_tokens_used/token_limit/usage_ratio
    前端无法消费。
    """
    tenant_id = tenant_of(current_user)
    total_memories = db.query(Memory).filter(Memory.tenant_id == tenant_id).count()
    total_conversations = (
        db.query(Conversation).filter(Conversation.tenant_id == tenant_id).count()
    )
    # 平均 token/会话：基于 messages.tokens_in + tokens_out 聚合
    avg_tokens = 0.0
    try:
        # Message 无 tenant_id，通过 conversation 关联过滤
        total_tokens_row = (
            db.query(
                _func.coalesce(_func.sum(Message.tokens_in), 0)
                + _func.coalesce(_func.sum(Message.tokens_out), 0)
            )
            .join(Conversation, Conversation.id == Message.conversation_id)
            .filter(Conversation.tenant_id == tenant_id)
            .scalar()
        )
        total_tokens = int(total_tokens_row or 0)
        if total_conversations > 0:
            avg_tokens = round(total_tokens / total_conversations, 2)
    except Exception:  # noqa: BLE001
        avg_tokens = 0.0

    return ok({
        "total_memories": total_memories,
        "total_conversations": total_conversations,
        "avg_tokens_per_conversation": avg_tokens,
    })
