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

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from finpilot.agent import run_agent
from finpilot.agent.graph import build_agent, make_thread_id
from finpilot.llm.intent import classify_intent, extract_parameters
from finpilot.database import crud
from finpilot.database.models import Conversation, Message, LlmProvider, LlmModel

from .deps import get_current_user, get_db_session, tenant_of
from .rate_limit import limiter, get_user_key
from .schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/agent", tags=["agent"])

# ---------------------------------------------------------------------------
# 公开模型列表（无需管理员权限，所有已认证用户可查看可用的聊天模型）
# ---------------------------------------------------------------------------
@router.get("/models")
def list_chat_models(
    db: Session = Depends(get_db_session),
    _: dict = Depends(get_current_user),
):
    """返回所有激活供应商下激活模型的列表，供前端模型选择器使用"""
    models = (
        db.query(LlmModel)
        .join(LlmProvider, LlmModel.provider_id == LlmProvider.id)
        .filter(LlmProvider.is_active.is_(True), LlmModel.is_active.is_(True))
        .order_by(LlmModel.display_name.asc())
        .all()
    )
    return {
        "code": 0,
        "data": [
            {
                "id": m.model_name,
                "label": m.display_name or m.model_name,
                "tier": m.tier,
            }
            for m in models
        ],
    }


# ---------------------------------------------------------------------------
# 系统健康检查
# ---------------------------------------------------------------------------
@router.get("/health")
def health_check():
    """轻量健康探针，用于负载均衡和监控"""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# 智能体能力清单（MCP / Skill / Tool / Sandbox 等）
# ---------------------------------------------------------------------------
@router.get("/capabilities")
def list_capabilities():
    """返回当前启用的智能体能力列表，供前端动态展示能力面板。

    能力来源：
    - 内置工具（File / Web / SQL / Python 等）
    - 扩展路由模块（MCP Servers / Skills / Tools / Sandbox / Backtesting / Factor Mining）
    - 增强模块（Validation / Debate / Explainability / Risk）
    """
    capabilities = [
        {"id": "file", "name": "文件操作", "type": "builtin", "status": "active",
         "description": "上传、解析、查询 PDF/Excel/CSV/DOCX 文件"},
        {"id": "web", "name": "联网搜索", "type": "builtin", "status": "active",
         "description": "搜索引擎查询与网页内容抓取"},
        {"id": "sql", "name": "SQL 查询", "type": "builtin", "status": "active",
         "description": "对上传的结构化数据执行 SQL 查询"},
        {"id": "python", "name": "Python 沙盒", "type": "builtin", "status": "active",
         "description": "在隔离沙盒中执行 Python 代码进行数据分析"},
        {"id": "charts", "name": "图表生成", "type": "builtin", "status": "active",
         "description": "从查询结果自动生成可视化图表"},
    ]

    # 扩展能力（来自扩展路由模块的状态）
    ext_modules = [
        ("mcp_servers", "MCP 服务", "接入外部 MCP 协议工具与服务"),
        ("skills", "技能库", "可注册的技能模板与工作流"),
        ("tools", "工具管理", "自定义工具注册与生命周期管理"),
        ("sandbox_configs", "沙盒配置", "Python 沙盒执行环境配置"),
        ("backtesting", "策略回测", "多因子策略历史回测"),
        ("factor_mining", "因子挖掘", "财务因子自动挖掘与筛选"),
        ("valuation", "估值模型", "DCF / PE / PB 等多模型估值"),
        ("validation", "校验引擎", "智能体输出交叉校验"),
        ("debate", "多智能体辩论", "多模型协同辩论与观点汇总"),
        ("explainability", "可解释性", "模型推理过程可视化"),
        ("risk", "风险分析", "多维风险指标监控"),
    ]

    import importlib
    for mod_name, cap_name, cap_desc in ext_modules:
        try:
            importlib.import_module(f"finpilot.api.{mod_name}")
            status = "available"
        except ImportError:
            status = "unavailable"
        capabilities.append({
            "id": mod_name,
            "name": cap_name,
            "type": "extension",
            "status": status,
            "description": cap_desc,
        })

    return {"code": 0, "data": capabilities}


# ---------------------------------------------------------------------------
# 上下文感知追问建议 — 差异化亮点
# ---------------------------------------------------------------------------

# 追问模板：基于已激活的能力自动生成自然语言追问
_SUGGESTION_TEMPLATES: list[str] = [
    "帮我分析这份财报中的关键财务指标",
    "对比最近两个季度的营收和利润变化",
    "这些数据中有哪些异常值需要关注？",
    "将分析结果导出为 PDF 报告",
    "用图表展示毛利率和净利率的趋势",
    "基于当前数据给我一个投资建议",
    "这份报告的风险点有哪些？",
    "有什么行业对标数据可以参考？",
]


@router.get("/suggestions")
def get_suggestions(
    conversation_id: int = Query(..., ge=1),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """返回基于当前会话上下文的追问建议。

    逻辑：
    1. 获取会话中最近的消息角色分布
    2. 若有已上传文档，优先推荐文档分析类追问
    3. 若最近一轮是回答，推荐追问/深挖类建议
    4. 默认返回通用建议模板
    """
    conv = db.get(Conversation, conversation_id)
    if not conv or conv.user_id != current_user["user_id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(10)
        .all()
    )

    suggestions: list[str] = []

    if not msgs:
        suggestions = [
            "上传一份财报 PDF 或 Excel，我来帮你分析",
            "搜索某家上市公司的财务数据",
            "帮我做一个行业对比分析",
        ]
    else:
        has_file_upload = any("上传" in (m.content or "") or "文件" in (m.content or "") for m in msgs)
        last_role = msgs[0].role if msgs else None

        if has_file_upload:
            suggestions = [
                "从这份文件中提取所有财务报表数据",
                "对比文件中的营收数据和去年同期",
                "将关键指标整理成表格",
                "这些数据中有哪些风险信号？",
            ]
        elif last_role == "assistant":
            suggestions = [
                "能展开说说吗？",
                "用更通俗的语言解释一下",
                "给我具体的数字和比例",
                "和行业平均水平对比如何？",
            ]
        else:
            suggestions = _SUGGESTION_TEMPLATES[:4]

    return {"code": 0, "data": suggestions}


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


def _load_agent_config(db: Session, conversation_id: str | None, user_id: int | None = None) -> Any:
    """从会话加载绑定的 AgentConfig（best-effort）。

    因果链：管理员在后台配置 AgentConfig → 会话绑定 agent_config_id →
    运行时读取该配置并注入 run_agent（覆盖 system_prompt / model_id）。
    会话未绑定或配置已被禁用/删除时返回 None，回退到默认 ReAct 行为。

    安全：传入 ``user_id`` 时校验会话归属当前用户，防止跨租户/跨用户
    通过伪造 conversation_id 读取他人会话绑定的 AgentConfig。
    """
    if not conversation_id:
        return None
    try:
        conv = db.get(Conversation, int(conversation_id))
        if not conv or conv.agent_config_id is None:
            return None
        # 校验会话归属当前用户，防止跨用户/跨租户读取 AgentConfig
        if user_id is not None and conv.user_id != user_id:
            return None
        from finpilot.database.models import AgentConfig

        cfg = db.get(AgentConfig, conv.agent_config_id)
        # 仅当配置存在且激活时才生效
        if cfg is None or not getattr(cfg, "is_active", True):
            return None
        return cfg
    except (ValueError, TypeError, Exception):  # noqa: BLE001
        return None


def _build_assistant_message_meta(result: dict[str, Any], started_at: float) -> dict[str, Any]:
    """从 run_agent 返回结果与计时构造 assistant 消息的运行时元数据.

    提取规则（best-effort，缺字段一律回退 None）：
    - model_name: result["model_name"]（run_agent 当前未填充，预留兼容）
    - tokens_in / tokens_out: result["tokens_in"] / result["tokens_out"]
      （run_agent 当前未填充，预留兼容）
    - latency_ms: 由 chat 入口的 started_at 计算总耗时（毫秒，取整）
    - tool_calls: result["steps"] 序列化为 JSON 字符串（ReAct 步骤草稿本）
    """
    latency_ms = int((time.time() - started_at) * 1000)

    tool_calls_json: Optional[str]
    steps = result.get("steps") or []
    if steps:
        try:
            tool_calls_json = json.dumps(steps, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            tool_calls_json = None
    else:
        tool_calls_json = None

    return {
        "model_name": result.get("model_name"),
        "tokens_in": result.get("tokens_in"),
        "tokens_out": result.get("tokens_out"),
        "latency_ms": latency_ms,
        "tool_calls": tool_calls_json,
    }


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("20/minute", key_func=get_user_key)
def chat(
    req: ChatRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """调用智能体运行时处理用户问题"""
    tenant_id = tenant_of(current_user)
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

    # 从会话加载绑定的 AgentConfig（若有），让管理员后台配置真正接入运行时
    agent_config = _load_agent_config(db, conversation_id, user_id=current_user["user_id"])

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
            intent_question=req.question,  # 意图识别用原始问题，避免被注入上下文污染
            agent_config=agent_config,
        )
    except HTTPException:
        # 业务层主动抛出的 HTTPException（如 404/403）原样上抛，保持语义
        success = False
        raise
    except Exception as exc:  # noqa: BLE001
        # LLM 不可用 / 工具执行失败等运行时异常：优雅降级为 502，
        # 不向上抛通用 Exception（否则会触发 slowapi 中间件与全局异常处理器冲突，
        # 报 "parameter response must be an instance of starlette.responses.Response"）。
        success = False
        error_msg = str(exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="智能体服务暂不可用，请稍后重试或检查 LLM 供应商配置",
        )
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

    # 记录助手回复（携带 LLM 运行时元数据：model/tokens/latency/tool_calls）
    assistant_meta = _build_assistant_message_meta(result, started_at)
    crud.add_message(
        db,
        int(conversation_id),
        "assistant",
        result.get("answer", ""),
        model_name=assistant_meta["model_name"],
        tokens_in=assistant_meta["tokens_in"],
        tokens_out=assistant_meta["tokens_out"],
        latency_ms=assistant_meta["latency_ms"],
        tool_calls=assistant_meta["tool_calls"],
    )

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
@limiter.limit("20/minute", key_func=get_user_key)
def chat_stream(
    req: ChatStreamRequest,
    request: Request,
    response: Response,
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
    tenant_id = tenant_of(current_user)
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

    # 从会话加载绑定的 AgentConfig（与 /chat 一致），让管理员后台配置
    # （system_prompt / model_id）在流式端点也生效，此前 stream 端点完全忽略
    agent_config = _load_agent_config(db, conversation_id, user_id=current_user["user_id"])

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
            # 意图分类必须基于用户原始问题，否则注入的「# 上传文档上下文」会被
            # 关键词规则误判为 parse_document，进而触发从磁盘读不存在的文件。
            intent_result = classify_intent(req.question, history=req.history or [], db=db)
            intent = intent_result.get("intent", "unknown")
            parameters = extract_parameters(req.question, intent, history=req.history or [], db=db)

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

            agent = build_agent(
                tenant_id=tenant_id, user_id=user_id, db=db, agent_config=agent_config,
            )
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

            # 4. 持久化助手回复（携带 LLM 运行时元数据，与 /chat 行为一致）
            try:
                assistant_meta = _build_assistant_message_meta(run_result, started_at)
                crud.add_message(
                    db,
                    int(conversation_id),
                    "assistant",
                    answer,
                    model_name=assistant_meta["model_name"],
                    tokens_in=assistant_meta["tokens_in"],
                    tokens_out=assistant_meta["tokens_out"],
                    latency_ms=assistant_meta["latency_ms"],
                    tool_calls=assistant_meta["tool_calls"],
                )
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
        tenant_id=tenant_of(current_user),
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
