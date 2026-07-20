# -*- coding: utf-8 -*-
"""智能体对话路由。

- POST /chat                          调用 run_agent 处理用户问题
- POST /chat/stream                   SSE 流式响应（前端 AgentChatPage 使用）
- GET  /conversations                 列出当前用户会话
- POST /conversations                 创建新会话
- GET  /conversations/{id}/messages   获取会话消息

run_agent 内部完成：意图识别 -> 参数抽取 -> ReAct 图执行 -> 结果归一化。
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from finpilot.agent import run_agent
from finpilot.agent.graph import build_agent, make_thread_id
from finpilot.llm.intent import classify_intent, extract_parameters
from finpilot.database import crud
from finpilot.database.models import Conversation, Message

from .deps import get_current_user, get_db_session
from .schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/agent", tags=["agent"])


class ChatStreamRequest(BaseModel):
    """前端 AgentChatPage 流式请求体"""
    question: str
    conversation_id: Optional[str] = None
    history: list[dict[str, Any]] = []
    deep_think: bool = False
    use_web: bool = False
    files: list[dict[str, Any]] = []
    model: Optional[str] = None


def _extract_uploaded_context(files: list[dict[str, Any]], tenant_id: str) -> str:
    """将上传的 base64 文件解析为可注入 agent 上下文的文本摘要.

    流程：base64 解码 → 写临时文件 → 调用 finpilot.parser.get_parser →
          抽取 pages/tables 关键内容 → 拼接为结构化上下文块。

    返回空字符串表示无可用文件或解析失败（best-effort，不抛异常）。
    """
    if not files:
        return ""

    import base64 as _b64
    import os
    import tempfile

    from finpilot.parser import get_parser, ParserError

    chunks: list[str] = []
    for f in files:
        name = str(f.get("name") or "")
        b64 = str(f.get("base64") or "")
        if not name or not b64:
            continue
        try:
            raw = _b64.b64decode(b64)
        except Exception as exc:  # noqa: BLE001
            chunks.append(f"[文件 {name}] base64 解码失败：{exc}")
            continue
        # 写临时文件让 parser 按扩展名分发
        suffix = os.path.splitext(name)[1]
        fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix="upload_")
        try:
            with os.fdopen(fd, "wb") as fp:
                fp.write(raw)
            parser = get_parser(tmp_path)
            doc = parser.parse(tmp_path)
            # 提取关键内容：每页文本前 1500 字 + 第一个表格
            page_texts: list[str] = []
            for page in doc.pages[:5]:  # 最多前 5 页
                txt = (page.text or "").strip()
                if txt:
                    page_texts.append(f"页{page.page_number}: {txt[:1500]}")
            tables_summary = ""
            if doc.tables:
                first_table = doc.tables[0]
                # 取前 8 行 × 前 8 列，避免上下文过长
                rows = first_table[:8]
                cells = [r[:8] for r in rows]
                tables_summary = "\n".join(
                    " | ".join(str(c) for c in row) for row in cells if row
                )
            section = [f"## 文件：{name}（类型={doc.file_type}, 页数={len(doc.pages)}, 表格数={len(doc.tables)}）"]
            if page_texts:
                section.append("### 文本摘要\n" + "\n\n".join(page_texts))
            if tables_summary:
                section.append("### 首表预览\n" + tables_summary)
            chunks.append("\n".join(section))
        except ParserError as exc:
            chunks.append(f"[文件 {name}] 解析失败：{exc}")
        except Exception as exc:  # noqa: BLE001
            chunks.append(f"[文件 {name}] 处理异常：{exc}")
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    if not chunks:
        return ""
    return "# 上传文档上下文\n\n" + "\n\n---\n\n".join(chunks)


def _inject_file_context(question: str, files: list[dict[str, Any]], tenant_id: str) -> str:
    """把上传文件解析后的上下文拼接到问题前。"""
    ctx = _extract_uploaded_context(files, tenant_id)
    if not ctx:
        return question
    return f"{ctx}\n\n---\n\n## 用户问题\n{question}"


class CreateConversationRequest(BaseModel):
    title: Optional[str] = None


def _tenant_of(user: dict) -> str:
    """按用户生成租户 ID"""
    return f"user_{user['user_id']}"


@router.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """调用智能体运行时处理用户问题"""
    tenant_id = _tenant_of(current_user)
    user_id = str(current_user["user_id"])

    # 无会话则自动创建一个，标题取问题前 50 字
    conversation_id = req.conversation_id
    if not conversation_id:
        conv = crud.create_conversation(
            db,
            user_id=current_user["user_id"],
            title=req.question[:50],
            tenant_id=tenant_id,
        )
        conversation_id = str(conv.id)

    # 记录用户消息
    crud.add_message(db, int(conversation_id), "user", req.question)

    # 把上传文件解析后注入问题上下文（best-effort，失败则用原问题）
    effective_question = _inject_file_context(req.question, getattr(req, "files", []) or [], tenant_id)

    # 运行智能体（内部按 thread_id 持久化 ReAct 状态）
    started_at = time.time()
    success = True
    error_msg = ""
    try:
        result = run_agent(
            question=effective_question,
            tenant_id=tenant_id,
            user_id=user_id,
            db=db,
            conversation_id=conversation_id,
        )
    except Exception as exc:  # noqa: BLE001
        success = False
        error_msg = str(exc)
        raise
    finally:
        # best-effort 埋点：记录 agent_run 日志
        try:
            from finpilot.services.runtime_log_service import log_runtime

            log_runtime(
                db,
                category="agent_run",
                event="chat_request",
                message=(req.question or "")[:200],
                source="agent.chat",
                payload={
                    "question": (req.question or "")[:500],
                    "answer": (result.get("answer", "") if 'result' in locals() else "")[:500],
                    "intent": result.get("intent") if 'result' in locals() else None,
                    "confidence": result.get("confidence") if 'result' in locals() else None,
                    "conversation_id": conversation_id,
                    "error": error_msg or None,
                },
                duration_ms=int((time.time() - started_at) * 1000),
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=conversation_id,
                success=success,
                level="info" if success else "error",
            )
        except Exception:  # noqa: BLE001
            pass

    # 记录助手回复
    crud.add_message(db, int(conversation_id), "assistant", result.get("answer", ""))

    return ChatResponse(
        answer=result.get("answer", ""),
        intent=result.get("intent", "unknown"),
        confidence=result.get("confidence", 0.0),
        steps=result.get("steps", []),
    )


def _sse(event_type: str, data: dict) -> str:
    """格式化 SSE 行：data: {json}\n\n"""
    payload = {"type": event_type, **data}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
def chat_stream(
    req: ChatStreamRequest,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """SSE 流式聊天 — 前端 AgentChatPage 使用 data: {json} 事件.

    事件类型：
      - {type: "conversation", conversation_id}
      - {type: "thinking", content}  — ReAct 思考步骤（可选）
      - {type: "token", content}     — 答案增量 token
      - {type: "done", message_id}
      - {type: "error", message}
    """
    tenant_id = _tenant_of(current_user)
    user_id = str(current_user["user_id"])

    # 复用 /chat 的会话管理逻辑
    conversation_id = req.conversation_id
    if not conversation_id:
        conv = crud.create_conversation(
            db,
            user_id=current_user["user_id"],
            title=req.question[:50],
            tenant_id=tenant_id,
        )
        conversation_id = str(conv.id)

    crud.add_message(db, int(conversation_id), "user", req.question)

    # 把上传文件解析后注入问题上下文（best-effort，失败则用原问题）
    effective_question = _inject_file_context(req.question, req.files or [], tenant_id)

    def event_generator():
        started_at = time.time()
        # 1. start 事件（携带 conversation_id 与原始问题）
        yield _sse("start", {
            "question": req.question,
            "conversation_id": conversation_id,
        })

        run_success = True
        run_error = ""
        run_result: dict = {}
        try:
            # 2. 运行 agent —— 用 agent.stream() 实时推送每个节点的思考步骤
            #    （此前用 run_agent 一次性同步执行，前端会卡 1-3 分钟看不到任何事件，
            #     误以为「网络错误 / 响应错误」；改成流式后，每个 ReAct 步骤都会即时推送）
            intent_result = classify_intent(effective_question, history=req.history or [], db=db)
            intent = intent_result.get("intent", "unknown")
            parameters = extract_parameters(effective_question, intent, history=req.history or [], db=db)

            initial_state: dict[str, Any] = {
                "question": effective_question,
                "intent": intent,
                "parameters": parameters,
                "tool_result": {},
                "answer": "",
                "error": "",
                "conversation_id": conversation_id or "",
                "messages": req.history or [],
                "retry_count": 0,
                "react_steps": [],
                "react_thought": "",
                "react_action": "",
                "react_action_input": "",
                "confidence": 0.0,
                "tenant_id": tenant_id,
            }

            agent = build_agent(tenant_id=tenant_id, user_id=user_id, db=db)
            thread_id = make_thread_id(tenant_id, conversation_id)
            config = {"configurable": {"thread_id": thread_id}}

            final_state: dict[str, Any] = initial_state
            steps: list[dict[str, Any]] = []
            last_heartbeat = time.time()

            # 用 stream() 而非 invoke() —— 每个节点完成后立即推送 thinking_token
            for chunk in agent.stream(initial_state, config=config, stream_mode="updates"):
                # chunk 形如 {"agent": {...partial_state...}} 或 {"tools": {...}} 或 {"finalize": {...}}
                for node_name, state_update in chunk.items():
                    if not isinstance(state_update, dict):
                        continue

                    # agent 节点：推送最新的 thought
                    if node_name == "agent":
                        thought = state_update.get("react_thought") or ""
                        action = state_update.get("react_action") or ""
                        if thought:
                            yield _sse("thinking_token", {"content": f"💭 {thought}\n"})
                        if action and action != "__retry__" and action != "FinalAnswer":
                            yield _sse("thinking_token", {"content": f"🔧 调用工具：{action}\n"})

                    # tools 节点：把新增步骤的 observation 推送出去
                    elif node_name == "tools":
                        new_steps = state_update.get("react_steps") or []
                        if new_steps and len(new_steps) > len(steps):
                            # 只推送本次新增的步骤
                            for step in new_steps[len(steps):]:
                                steps = new_steps
                                if isinstance(step, dict):
                                    observation = step.get("observation") or ""
                                    if observation:
                                        yield _sse("thinking_token", {"content": f"📋 结果：{observation[:200]}{'...' if len(observation) > 200 else ''}\n"})

                    # finalize 节点：拿到最终答案
                    elif node_name == "finalize":
                        if "answer" in state_update:
                            final_state = {**initial_state, **state_update}
                        else:
                            final_state = {**final_state, **state_update}

                    # 心跳保护：长时间无事件时推送 ping，防止前端误判超时
                    now = time.time()
                    if now - last_heartbeat > 15:
                        yield _sse("thinking_token", {"content": "…\n"})
                        last_heartbeat = now

            # 合并最终状态（防 finalize 节点没在 stream 中暴露 answer）
            if not final_state.get("answer"):
                # 兜底：再查一次最终状态
                try:
                    final_state = agent.get_state(config).values or final_state
                except Exception:
                    pass

            answer = final_state.get("answer", "") or ""
            confidence = float(final_state.get("confidence", 0.0) or 0.0)
            all_steps = final_state.get("react_steps", steps) or steps

            run_result = {
                "answer": answer,
                "intent": intent,
                "confidence": confidence,
                "steps": all_steps,
                "tool_result": final_state.get("tool_result", {}),
            }

            # 3. 分块推送最终答案 —— answer_token 累积到 content
            chunk_size = 12  # 中文字符，每 12 字一帧
            for i in range(0, len(answer), chunk_size):
                yield _sse("answer_token", {"content": answer[i:i + chunk_size]})
                time.sleep(0.015)  # 轻微延迟，前端能看到流式效果

            # 4. 持久化助手回复
            try:
                crud.add_message(db, int(conversation_id), "assistant", answer)
            except Exception:
                pass

            # 5. 完成事件 — 携带 thinking_time_ms 与 payload（react_steps/confidence）
            thinking_time_ms = int((time.time() - started_at) * 1000)
            yield _sse("done", {
                "thinking_time_ms": thinking_time_ms,
                "payload": {
                    "react_steps": all_steps,
                    "confidence": confidence,
                    "intent": intent,
                },
            })
        except Exception as exc:
            run_success = False
            run_error = str(exc)
            yield _sse("error", {"message": str(exc)})
        finally:
            # best-effort 埋点：记录 agent_run 日志
            try:
                from finpilot.services.runtime_log_service import log_runtime

                log_runtime(
                    db,
                    category="agent_run",
                    event="chat_stream",
                    message=(req.question or "")[:200],
                    source="agent.chat_stream",
                    payload={
                        "question": (req.question or "")[:500],
                        "answer": (run_result.get("answer", "") or "")[:500],
                        "intent": run_result.get("intent"),
                        "confidence": run_result.get("confidence"),
                        "conversation_id": conversation_id,
                        "error": run_error or None,
                    },
                    duration_ms=int((time.time() - started_at) * 1000),
                    tenant_id=tenant_id,
                    user_id=user_id,
                    session_id=conversation_id,
                    success=run_success,
                    level="info" if run_success else "error",
                )
            except Exception:  # noqa: BLE001
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/conversations")
def list_conversations(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """列出当前用户的会话"""
    convs = crud.get_conversations(
        db, user_id=current_user["user_id"], skip=skip, limit=limit
    )
    return [
        {
            "id": c.id,
            "title": c.title,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in convs
    ]


@router.post("/conversations")
def create_conversation(
    req: CreateConversationRequest,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """创建新会话"""
    conv = crud.create_conversation(
        db,
        user_id=current_user["user_id"],
        title=req.title or "新会话",
        tenant_id=_tenant_of(current_user),
    )
    return {
        "id": conv.id,
        "title": conv.title,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
    }


@router.get("/conversations/{conversation_id}/messages")
def get_messages(
    conversation_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """获取会话消息（按时间正序）"""
    conv = db.get(Conversation, conversation_id)
    # 会话不存在或不属于当前用户均返回 404
    if not conv or conv.user_id != current_user["user_id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in msgs
    ]
