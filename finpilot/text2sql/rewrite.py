# -*- coding: utf-8 -*-
"""
多轮查询重写（指代消解）。

板块F：多轮意图重路由。text2sql 此前只看当前问题，无法处理"那净利润呢""同比呢"
这类依赖上文的省略问句。本模块在生成 SQL 前，先用 LLM 结合会话历史把省略问题
重写为自包含的完整问题；LLM 不可用或无历史时原样返回，保证降级安全。

重写后的 question 再喂给规则引擎 / LLM 生成 SQL，从而让 text2sql 具备多轮能力。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from finpilot.llm.client import LLMUnavailableError
from finpilot.llm.config import get_default_config

logger = logging.getLogger(__name__)

# 注入 LLM prompt 的历史轮数上限，避免 prompt 过长
_MAX_HISTORY_TURNS = 6


def _format_history(history: Optional[list[Any]]) -> str:
    """把历史消息裁剪并格式化为 ``角色: 内容`` 文本。

    兼容两种历史形态：
    - ORM Message 对象（有 role/content 属性）
    - dict（含 role/content 键，或 user/assistant 文本）
    无内容时返回空串。
    """
    if not history:
        return ""
    rows: list[str] = []
    for item in history[-_MAX_HISTORY_TURNS:]:
        role: str = ""
        content: str = ""
        if isinstance(item, dict):
            role = str(item.get("role") or item.get("intent") or "user")
            content = str(item.get("content") or item.get("question") or item.get("answer") or "")
        else:
            role = str(getattr(item, "role", "user") or "user")
            content = str(getattr(item, "content", "") or "")
        content = content.strip()
        if not content:
            continue
        rows.append(f"{role}: {content}")
    return "\n".join(rows)


def rewrite_query(question: str, history: Optional[list[Any]] = None, db=None) -> str:
    """基于会话历史重写省略问题为自包含问题。

    - 无历史 / 历史为空 → 原样返回 question。
    - LLM 不可用 / 调用失败 → 原样返回 question（降级）。
    - LLM 成功 → 返回重写后的完整问题（去除引号与多余空白）。
    """
    if not question or not history:
        return question

    history_text = _format_history(history)
    if not history_text:
        return question

    # db 缺失则无法加载 LLM 配置，直接降级
    if db is None:
        return question

    try:
        config = get_default_config(db)
    except Exception:  # noqa: BLE001  配置加载失败走降级
        return question
    if config is None:
        return question

    from finpilot.llm.client import LLMClient

    system_prompt = (
        "你是查询重写助手。根据对话历史，把用户当前可能省略/含指代的查询重写为一个"
        "自包含、可独立理解的完整问题。要求：\n"
        "1. 仅输出重写后的问题，不要解释、不要引号、不要多余标点；\n"
        "2. 若当前问题已自包含，原样输出；\n"
        "3. 保留原问题中的年份/公司/指标等关键信息，补全历史中提及但当前缺失的要素。"
    )
    user_prompt = (
        f"对话历史:\n{history_text}\n\n"
        f"当前问题: {question}\n"
        f"请输出重写后的完整问题。"
    )
    try:
        client = LLMClient(config)
        resp = client.chat(system_prompt, user_prompt, temperature=0.0, max_tokens=200)
    except LLMUnavailableError as exc:
        logger.warning("查询重写 LLM 调用失败，降级为原问题: %s", exc)
        return question

    rewritten = (resp or "").strip().strip("\"'""「」“”").strip()
    # LLM 偶尔回复带换行或前缀"重写后："，取最后一行并去掉前缀
    if "\n" in rewritten:
        rewritten = rewritten.strip().splitlines()[-1].strip()
    for prefix in ("重写后:", "重写后：", "重写:", "重写："):
        if rewritten.startswith(prefix):
            rewritten = rewritten[len(prefix):].strip()
    return rewritten or question
