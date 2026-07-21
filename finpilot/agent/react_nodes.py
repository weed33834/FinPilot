"""ReAct 模式智能体节点。

图结构::

    agent → [should_continue]
        ├─ FinalAnswer / error / 超过5轮 → finalize → END
        └─ 否则 → tools → agent（回环）

设计要点：
- ``react_agent_node`` 用 ModelRouter 选档位、LLMClient 出 Thought/Action/Action Input，
  ``stop=["\\nObservation"]`` 阻止模型自编工具结果。
- LLM 不可用（无配置 / 调用失败）时降级为规则匹配：按 intent 直接调用对应工具给出答案。
- 解析失败回灌一条错误 Observation 让 LLM 下轮自愈（``__retry__`` 标记），工具节点遇
  ``__retry__`` 空转回环，不消耗真实工具调用。
- 最多 5 轮工具调用，超出后终止。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from finpilot.llm.client import LLMClient, LLMUnavailableError
from finpilot.llm.config import get_default_config, get_tier_config
from finpilot.llm.router import ModelRouter
from finpilot.parser import ParserError

from .guardrails import (
    annotate_answer_with_confidence,
    check_hallucination,
    compress_context,
    detect_tool_loop,
    make_tool_error_observation,
)
from .state import AgentState
from .tool_registry import ToolContext, tool_registry

logger = logging.getLogger(__name__)

# 最大 ReAct 工具调用轮数
MAX_REACT_STEPS = 5

# FinalAnswer 的多种写法，统一归一化判断
_FINAL_ANSWER_TOKENS = {"finalanswer", "final_answer", "final answer"}

# 工具执行可预期的异常类型：捕获后回灌为 Observation，让 LLM 自纠
_TOOL_ERRORS = (
    ParserError,
    SQLAlchemyError,
    LLMUnavailableError,
    ValueError,
    TypeError,
    KeyError,
)

# 终止时无明确答案的兜底回复
_FALLBACK_ANSWER = (
    "抱歉，我暂时无法完成这个任务。我可以帮您：\n"
    "1. 查询财务数据（如：2024年Q2营业收入是多少）\n"
    "2. 基于已上传文档进行问答\n"
    "3. 解析财务文档（PDF/Excel/CSV/Word）\n"
    "请用以上方式提问。"
)

_REACT_SYSTEM_PROMPT = """你是一个企业财务AI助手，使用 ReAct（推理-行动）模式解决用户问题。

可用工具：
{tools}

请严格按以下格式输出，不要输出任何额外内容：

Thought: <你对问题的思考与推理>
Action: <工具名称，或 FinalAnswer 表示给出最终答案>
Action Input: <工具参数的 JSON，或最终答案文本>

当你已获得足够信息可以直接回答用户时，使用：
Thought: <推理>
Action: FinalAnswer
Action Input: <最终答案>

规则：
- 每次只调用一个工具。
- 调用工具时 Action Input 必须是合法 JSON（如 {{"question": "..."}}），给出最终答案时为纯文本。
- 不要自行编造 Observation，工具结果将由系统在下轮提供。
- 最多进行 {max_steps} 轮工具调用，之后必须给出 FinalAnswer。
"""


# ---------------------------------------------------------------------------
# LLM 输出解析
# ---------------------------------------------------------------------------


def _is_final_answer(action: str) -> bool:
    return action.strip().lower() in _FINAL_ANSWER_TOKENS


def parse_react_output(text: str) -> dict[str, Any]:
    """解析 LLM 的 ReAct 三段式输出。

    支持的格式（按优先级）：
    1. 标准 ReAct：Thought:/Action:/Action Input:/Final Answer:（兼容中英文冒号）
    2. ``<tool_call>`` XML 风格：``<function=NAME><parameter=KEY>VAL</parameter></function>``
       （部分 LLM 如 Qwen / Mistral 会输出这种格式而非 ReAct 三段式）
    3. ``<answer>...</answer>`` 或 ``<final_answer>...</final_answer>`` 作为最终答案

    成功返回 ``{"thought","action","action_input","final_answer","parse_ok": True}``；
    解析失败返回 ``{"parse_ok": False, "error": "..."}`` 作为 retry 信号。
    """
    text = (text or "").strip()

    # Thought 段落：到 Action / Final Answer / 文末为止
    thought_match = re.search(
        r"thought\s*[:：]\s*(.*?)(?=\n\s*action\s*[:：]|\n\s*final\s*answer\s*[:：]|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    thought = thought_match.group(1).strip() if thought_match else ""

    # Action 段落：到 Action Input / 文末为止（不会被 "Action Input:" 误匹配）
    action_match = re.search(
        r"action\s*[:：]\s*(.*?)(?=\n\s*action\s*input\s*[:：]|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    action = action_match.group(1).strip() if action_match else ""

    # Action Input 段落：到文末
    input_match = re.search(
        r"action\s*input\s*[:：]\s*(.*)", text, re.DOTALL | re.IGNORECASE
    )
    action_input = input_match.group(1).strip() if input_match else ""

    # Final Answer 段落（独立出现，等价于 Action: FinalAnswer）
    final_match = re.search(
        r"final\s*answer\s*[:：]\s*(.*)", text, re.DOTALL | re.IGNORECASE
    )
    final_answer = final_match.group(1).strip() if final_match else ""

    # Action: FinalAnswer 时，Action Input 即最终答案
    if not final_answer and _is_final_answer(action):
        final_answer = action_input

    if final_answer:
        return {
            "thought": thought,
            "action": "FinalAnswer",
            "action_input": final_answer,
            "final_answer": final_answer,
            "parse_ok": True,
        }
    if action:
        return {
            "thought": thought,
            "action": action,
            "action_input": action_input,
            "final_answer": "",
            "parse_ok": True,
        }

    # ---- 兼容 <tool_call> / <function=NAME> XML 风格（Qwen / Mistral 系） ----
    # 形如：
    #   <tool_call>
    #   <function=nl2sql>
    #   <parameter=question>查询本月营业收入</parameter>
    #   </function>
    #   </tool_call>
    tool_call_match = re.search(
        r"<tool_call>\s*<function=(\w+)(.*?)</tool_call>",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if tool_call_match:
        tc_action = tool_call_match.group(1).strip()
        params_block = tool_call_match.group(2)
        # 抽取所有 <parameter=KEY>VAL</parameter>
        params: dict[str, str] = {}
        for pm in re.finditer(
            r"<parameter=(\w+)>\s*(.*?)\s*</parameter>",
            params_block,
            re.DOTALL | re.IGNORECASE,
        ):
            params[pm.group(1).strip()] = pm.group(2).strip()
        # 思考取 <tool_call> 之前的文本（若有）
        if not thought:
            thought = text[: tool_call_match.start()].strip()
        # action_input 统一序列化为 JSON（与 _parse_action_input_json 配合）
        try:
            tc_action_input = json.dumps(params, ensure_ascii=False)
        except Exception:  # noqa: BLE001
            tc_action_input = params.get("question", "")
        return {
            "thought": thought,
            "action": tc_action,
            "action_input": tc_action_input,
            "final_answer": "",
            "parse_ok": True,
        }

    # ---- 兼容裸 <function=NAME>...</function>（无 <tool_call> 包裹） ----
    bare_fn_match = re.search(
        r"<function=(\w+)(.*?)</function>",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if bare_fn_match:
        bf_action = bare_fn_match.group(1).strip()
        params_block = bare_fn_match.group(2)
        params: dict[str, str] = {}
        for pm in re.finditer(
            r"<parameter=(\w+)>\s*(.*?)\s*</parameter>",
            params_block,
            re.DOTALL | re.IGNORECASE,
        ):
            params[pm.group(1).strip()] = pm.group(2).strip()
        if not thought:
            thought = text[: bare_fn_match.start()].strip()
        try:
            bf_action_input = json.dumps(params, ensure_ascii=False)
        except Exception:  # noqa: BLE001
            bf_action_input = params.get("question", "")
        return {
            "thought": thought,
            "action": bf_action,
            "action_input": bf_action_input,
            "final_answer": "",
            "parse_ok": True,
        }

    # ---- 兼容 <answer> / <final_answer> 标签作为最终答案 ----
    tag_final_match = re.search(
        r"<(?:answer|final_answer)>(.*?)</(?:answer|final_answer)>",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if tag_final_match:
        tag_answer = tag_final_match.group(1).strip()
        if not thought:
            thought = text[: tag_final_match.start()].strip()
        return {
            "thought": thought,
            "action": "FinalAnswer",
            "action_input": tag_answer,
            "final_answer": tag_answer,
            "parse_ok": True,
        }

    # 既无工具动作也无最终答案 → 解析失败，返回 retry 信号
    return {
        "thought": thought,
        "action": "",
        "action_input": "",
        "final_answer": "",
        "parse_ok": False,
        "error": f"无法解析 Action / Final Answer / tool_call，原始输出: {text[:200]}",
    }


def _parse_action_input_json(action_input: str) -> dict[str, Any]:
    """把 Action Input 解析为参数 dict。

    优先按 JSON 解析；失败时退化为 ``{"question": <原文>}``，兼容 LLM 输出纯文本的常见情况。
    """
    raw = (action_input or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, str):
            return {"question": parsed}
    except json.JSONDecodeError:
        pass
    return {"question": raw}


# ---------------------------------------------------------------------------
# LLM 配置解析与降级
# ---------------------------------------------------------------------------


def _resolve_llm_config(db: Any, tier: str, fallbacks: list[str]) -> Any:
    """按档位解析 LLM 配置：tier → fallbacks → 默认。

    db 为空或查询异常时返回 None，触发降级路径。
    """
    if db is None:
        return None
    try:
        for t in [tier] + list(fallbacks):
            cfg = get_tier_config(db, t)
            if cfg is not None:
                return cfg
        return get_default_config(db)
    except SQLAlchemyError as exc:
        # 表未初始化/查询失败属可预期情况，降级而非崩溃
        logger.warning("resolve_llm_config_failed: %s", exc)
        return None


def _map_intent_to_tool(
    intent: str, question: str, params: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """降级时按 intent 映射到工具与参数。"""
    if intent == "nl2sql":
        return "nl2sql", {"question": question}
    if intent == "document_qa":
        return "document_qa", {
            "question": question,
            "document_id": params.get("document_id"),
        }
    if intent == "parse_document":
        file_path = params.get("file_path") or _extract_file_path(question)
        return "parse_document", {"file_path": file_path or ""}
    return "", {}


def _extract_file_path(question: str) -> str:
    """从问题文本中尝试抽取带扩展名的文件路径。"""
    match = re.search(
        r"[\w\-\\/:\.]+\.(?:pdf|xlsx|xls|csv|docx|doc)",
        question,
        re.IGNORECASE,
    )
    return match.group(0) if match else ""


def _safe_call_tool(
    spec: Any, ctx: ToolContext, params: dict[str, Any]
) -> dict[str, Any]:
    """调用工具，捕获可预期异常为错误字典，避免单次工具失败终止整个 ReAct。"""
    try:
        return spec.func(ctx, **params)
    except _TOOL_ERRORS as exc:
        logger.warning("tool_exec_failed name=%s error=%s", spec.name, exc)
        return {"error": f"工具执行失败({type(exc).__name__}): {exc}"}


def _format_tool_result(action: str, result: dict[str, Any]) -> str:
    """把工具结果格式化为可直接给用户的答案文本（降级路径使用，无 LLM 摘要）。"""
    if not isinstance(result, dict):
        return str(result)
    if result.get("error"):
        return f"执行失败：{result['error']}"
    if action == "nl2sql":
        sql = result.get("sql", "")
        rows = result.get("rows", [])
        cols = result.get("columns", [])
        expl = result.get("explanation", "")
        if not rows:
            return f"未查询到数据。{expl}"
        header = " | ".join(str(c) for c in cols)
        lines = [header]
        for r in rows[:5]:
            lines.append(" | ".join(str(r.get(c, "")) for c in cols))
        preview = "\n".join(lines)
        return (
            f"SQL：{sql}\n说明：{expl}\n"
            f"结果（共{len(rows)}行，展示前{min(5, len(rows))}行）：\n{preview}"
        )
    if action == "document_qa":
        ans = result.get("answer", "")
        if ans:
            return ans
        chunks = result.get("chunks", [])
        if chunks:
            return "检索到相关片段：\n" + "\n".join(
                f"- {c.get('text', '')[:100]}" for c in chunks[:3]
            )
        return "未检索到相关文档内容。"
    if action == "parse_document":
        return (
            f"已解析文档 {result.get('filename', '')}"
            f"（类型 {result.get('file_type', '')}，"
            f"共 {len(result.get('pages', []))} 页，"
            f"表格 {len(result.get('tables', []))} 张）。"
        )
    return json.dumps(result, ensure_ascii=False, default=str)[:1000]


def _degrade_to_rule(
    state: AgentState,
    db: Any,
    tenant_id: str,
    user_id: str | None,
    reason: str,
) -> dict[str, Any]:
    """LLM 不可用时的降级：按 intent 直接调用工具给出答案。"""
    question = state.get("question", "")
    intent = state.get("intent") or "unknown"
    params = state.get("parameters") or {}

    # 优先处理「已注入文件上下文」场景：用户在 chat 里上传了文件，前端把
    # base64 注入到 question 头部（参见 api/agent.py 的 _inject_file_context）。
    # 此时文件内容已经在 question 文本里，无需再调 parse_document / document_qa
    # 工具（这俩工具都依赖磁盘文件或 document_id，chat 上传的文件两者都没有）。
    if "# 上传文档上下文" in question:
        answer_text = _format_injected_file_answer(question, reason)
        return {
            "react_action": "FinalAnswer",
            "react_action_input": answer_text,
            "react_thought": f"[降级] {reason}；已注入文件上下文，直接回灌解析摘要",
            "tool_result": {"injected_files": True},
            "error": "",
        }

    ctx = ToolContext(
        tenant_id=tenant_id,
        user_id=user_id,
        db=db,
        conversation_id=state.get("conversation_id"),
        history=state.get("messages") or [],
    )

    action, tool_params = _map_intent_to_tool(intent, question, params)
    tool_result: dict[str, Any] = {}
    if action:
        spec = tool_registry.get(action)
        if spec is not None:
            tool_result = _safe_call_tool(spec, ctx, tool_params)
            answer_text = _format_tool_result(action, tool_result)
        else:
            answer_text = f"降级：未找到工具 {action}"
    else:
        answer_text = "降级：无法识别可执行的工具，请提供更明确的问题。"

    # 标记为 FinalAnswer，让 should_continue → finalize 直接采纳
    return {
        "react_action": "FinalAnswer",
        "react_action_input": answer_text,
        "react_thought": f"[降级] {reason}",
        "tool_result": tool_result,
        "error": "",
    }


def _format_injected_file_answer(question: str, reason: str) -> str:
    """从注入了文件上下文的 question 中提取文件摘要，组装成给用户的答案。

    注入格式（见 api/agent.py:_extract_uploaded_context）::

        # 上传文档上下文

        ## 文件：xxx.xlsx（类型=xlsx, 页数=N, 表格数=M）
        ### 文本摘要
        ...
        ### 首表预览
        ...

        ---

        ## 用户问题
        ...

    本函数把上下文部分（首个 ``---`` 之前）原样回灌，并附上提示：LLM 不可用，
    无法基于内容回答具体问题，但用户能看到解析出的结构化数据。
    """
    # 切掉用户问题部分，只保留文件上下文
    parts = question.split("\n---\n", 1)
    ctx_block = parts[0] if parts else question
    # 去掉 markdown 标题前缀，让答案更紧凑
    lines = ctx_block.split("\n")
    cleaned = "\n".join(ln for ln in lines if not ln.startswith("# "))
    return (
        f"已解析您上传的文件，结构化内容如下：\n\n{cleaned.strip()}\n\n"
        f"—— 由于 LLM 暂时不可用（{reason}），无法基于以上内容"
        "生成自然语言回答。请参考上方解析出的表格/文本数据，"
        "或稍后重试。"
    )


# ---------------------------------------------------------------------------
# ReAct 节点
# ---------------------------------------------------------------------------


def _build_user_prompt(
    question: str, history: list[Any], steps: list[dict[str, Any]]
) -> str:
    """拼装 ReAct 用户提示：历史对话 + 问题 + 草稿本。"""
    parts: list[str] = []
    if history:
        hist_lines: list[str] = []
        for m in history[-6:]:
            if isinstance(m, dict):
                role = m.get("role", "")
                content = m.get("content", "")
                hist_lines.append(f"{role}: {content}")
            elif isinstance(m, str):
                hist_lines.append(m)
        if hist_lines:
            parts.append("历史对话：\n" + "\n".join(hist_lines))
    parts.append(f"用户问题：{question}")
    if steps:
        scratch: list[str] = []
        for s in steps:
            scratch.append(f"Thought: {s.get('thought', '')}")
            scratch.append(f"Action: {s.get('action', '')}")
            scratch.append(f"Action Input: {s.get('action_input', '')}")
            scratch.append(f"Observation: {s.get('observation', '')}")
        parts.append("\n".join(scratch))
    return "\n\n".join(parts)


def react_agent_node(
    state: AgentState,
    db: Any = None,
    tenant_id: str = "default",
    user_id: str | None = None,
) -> dict[str, Any]:
    """LLM 推理节点：生成下一轮 Thought/Action/Action Input。"""
    question = state.get("question", "")
    intent = state.get("intent")
    steps = state.get("react_steps") or []

    # 上下文压缩：草稿本累计 token 超阈值时折叠旧步骤，避免上下文溢出
    compression = compress_context(steps)
    if compression.compressed:
        logger.info("guardrails_compress: %s", compression.reason)
        steps = compression.new_steps
        state = {**state, "react_steps": steps}

    system_prompt = _REACT_SYSTEM_PROMPT.format(
        tools=tool_registry.build_description(),
        max_steps=MAX_REACT_STEPS,
    )

    # 按问题复杂度路由模型档位
    decision = ModelRouter().route(question, intent=intent)
    config = _resolve_llm_config(db, decision.tier, decision.fallback_tiers)
    if config is None:
        # LLM 配置不可用 → 规则降级
        return _degrade_to_rule(state, db, tenant_id, user_id, "LLM 配置不可用")

    user_prompt = _build_user_prompt(
        question, state.get("messages") or [], steps
    )
    try:
        client = LLMClient(config)
        # stop=["\nObservation"] 防止模型自编工具结果
        content = client.chat(
            system_prompt,
            user_prompt,
            temperature=0.2,
            max_tokens=800,
            stop=["\nObservation"],
        )
    except LLMUnavailableError as exc:
        logger.warning("react_llm_unavailable: %s", exc)
        return _degrade_to_rule(state, db, tenant_id, user_id, f"LLM 调用失败: {exc}")

    # Demo fallback 返回的是占位文本而非 ReAct 格式 — 直接降级，避免解析失败循环
    if content and "[DEMO FALLBACK]" in content:
        return _degrade_to_rule(
            state, db, tenant_id, user_id,
            "LLM 不可用（演示模式返回占位文本）",
        )

    parsed = parse_react_output(content)

    if not parsed.get("parse_ok"):
        # 解析失败：回灌错误 Observation 让 LLM 下轮自愈
        retry_count = state.get("retry_count", 0) + 1
        if len(steps) < MAX_REACT_STEPS:
            new_steps = steps + [
                {
                    "thought": parsed.get("thought", ""),
                    "action": "__retry__",
                    "action_input": "",
                    "observation": (
                        f"输出格式错误：{parsed.get('error')}。请严格用格式：\n"
                        "Thought: <推理>\nAction: <工具名或FinalAnswer>\n"
                        "Action Input: <JSON参数或最终答案>"
                    ),
                }
            ]
            return {
                "react_steps": new_steps,
                "react_action": "__retry__",
                "react_thought": parsed.get("thought", ""),
                "retry_count": retry_count,
            }
        # 超出轮数仍解析失败 → 降级
        return _degrade_to_rule(
            state, db, tenant_id, user_id, "ReAct 输出解析多次失败"
        )

    return {
        "react_thought": parsed["thought"],
        "react_action": parsed["action"],
        "react_action_input": parsed["action_input"],
    }


def react_tool_executor_node(
    state: AgentState,
    db: Any = None,
    tenant_id: str = "default",
    user_id: str | None = None,
) -> dict[str, Any]:
    """工具执行节点：按 Action 调用工具，把 Observation 追加到草稿本。"""
    action = state.get("react_action", "")
    action_input = state.get("react_action_input", "")
    steps = state.get("react_steps") or []

    # __retry__ 是解析失败的自愈标记：agent 已写入错误 Observation，
    # 此处空转回环，不再追加无用步骤。
    if action == "__retry__":
        return {"react_action": ""}

    # 死循环检测：基于上一轮草稿本判定（当前 action 尚未执行）
    # 注意：steps 中最后一项是上一轮的，本次 action 与上一轮相同则可触发
    if steps:
        last_step = steps[-1]
        if last_step.get("action") == action:
            # 临时把当前 action 拼到末尾用于检测
            probe_steps = steps + [{
                "action": action,
                "action_input": action_input,
                "observation": last_step.get("observation", ""),
            }]
            loop = detect_tool_loop(probe_steps)
            if loop.is_looping:
                logger.warning("guardrails_loop: %s", loop.reason)
                # 强制终止：让 should_continue 走 end 分支
                return {
                    "react_action": "FinalAnswer",
                    "react_action_input": (
                        f"检测到工具 {action} 进入死循环（连续 {loop.consecutive_count} 次"
                        f"无进展），已强制终止。建议：1) 更换查询参数 2) 换用其他工具 "
                        f"3) 联系运维检查工具上游服务。"
                    ),
                    "react_thought": f"[guardrails] {loop.reason}",
                    "react_steps": steps,
                }

    spec = tool_registry.get(action)
    if spec is None:
        observation = make_tool_error_observation(
            action,
            ValueError(f"工具 '{action}' 不存在"),
            available_tools=tool_registry.names(),
        )
        new_steps = steps + [
            {
                "thought": state.get("react_thought", ""),
                "action": action,
                "action_input": action_input,
                "observation": observation,
            }
        ]
        return {"react_steps": new_steps}

    params = _parse_action_input_json(action_input)
    ctx = ToolContext(
        tenant_id=tenant_id,
        user_id=user_id,
        db=db,
        conversation_id=state.get("conversation_id"),
        history=state.get("messages") or [],
    )

    result = _safe_call_tool(spec, ctx, params)
    # 工具失败时用结构化错误 Observation 引导 LLM 自愈
    if isinstance(result, dict) and result.get("error"):
        observation = make_tool_error_observation(
            action,
            result["error"],
            available_tools=tool_registry.names(),
        )
    else:
        observation = json.dumps(result, ensure_ascii=False, default=str)
    new_steps = steps + [
        {
            "thought": state.get("react_thought", ""),
            "action": action,
            "action_input": action_input,
            "observation": observation,
        }
    ]
    update: dict[str, Any] = {"react_steps": new_steps}
    # 首次工具结果写入 tool_result；intent 缺失时用 action 兜底
    if not state.get("tool_result"):
        update["tool_result"] = result
    if not state.get("intent"):
        update["intent"] = action
    return update


def _calculate_confidence(
    steps: list[dict[str, Any]], error: str, thought: str
) -> float:
    """基于执行步骤与是否降级计算置信度。"""
    # 降级路径：规则直调，置信度受限
    if "[降级]" in (thought or ""):
        return round(0.4 if not error else 0.2, 2)

    if not steps:
        base = 0.3 if error else 0.5
    else:
        total = len(steps)
        errors = sum(
            1
            for s in steps
            if "错误" in str(s.get("observation", ""))
            or "失败" in str(s.get("observation", ""))
        )
        base = (total - errors) / total * 0.7
        if 2 <= total <= 4:
            base += 0.15
        elif total == 1:
            base += 0.05

    if error:
        base *= 0.5
    return round(min(max(base, 0.1), 0.95), 2)


def react_finalize_node(state: AgentState) -> dict[str, Any]:
    """终止节点：提取 FinalAnswer，计算置信度，幻觉校验，或给出兜底回复。"""
    action = state.get("react_action", "")
    action_input = state.get("react_action_input", "")
    error = state.get("error")
    thought = state.get("react_thought", "")
    steps = state.get("react_steps") or []
    confidence = _calculate_confidence(steps, error, thought)

    if _is_final_answer(action) and action_input:
        # 幻觉校验：抽取答案中的事实（日期/金额/凭证号），回查 Observation
        answer = action_input
        try:
            hallucination = check_hallucination(answer, steps)
            if hallucination.is_enabled:
                # 命中率低时降低置信度，并给答案加低可信前缀
                if hallucination.should_flag:
                    confidence = round(confidence * 0.5, 2)
                    answer = annotate_answer_with_confidence(answer, hallucination)
                logger.info(
                    "guardrails_hallucination: hit_rate=%.2f flag=%s",
                    hallucination.hit_rate, hallucination.should_flag,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("hallucination_check_failed: %s", exc)
        return {"answer": answer, "confidence": confidence}
    if error:
        return {"answer": f"处理失败：{error}", "confidence": confidence}
    return {"answer": _FALLBACK_ANSWER, "confidence": confidence}


def should_continue(state: AgentState) -> str:
    """条件边：继续工具调用还是终止。

    - error → "end"
    - FinalAnswer → "end"
    - 超过 5 轮 → "end"
    - 否则 → "tools"
    """
    if state.get("error"):
        return "end"
    if _is_final_answer(state.get("react_action", "")):
        return "end"
    if len(state.get("react_steps") or []) >= MAX_REACT_STEPS:
        return "end"
    return "tools"
