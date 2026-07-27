"""提示词引擎 — 版本管理 + A/B测试 + 条件渲染 + Few-shot 注入 + 评估.

渲染流程:
1. 解析提示词 key → 获取 PromptTemplate（考虑 A/B 测试分流）
2. 加载激活版本内容
3. 渲染条件模板（Jinja2）
4. 注入 few-shot 示例
5. 替换变量
6. 返回最终提示词

条件模板语法（Jinja2）::

    {% if verbose %}详细模式{% endif %}
    {% if mode == "detailed" %}A{% else %}B{% endif %}
    {% for ex in examples %}输入: {{ ex.input }} 输出: {{ ex.output }}{% endfor %}

模板中使用 ``{name}`` 单花括号语法，渲染前自动转为 Jinja2 的 ``{{ name }}``。
未定义变量（如 ``{few_shot_examples}``）原样保留以供后续步骤处理。
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from jinja2 import BaseLoader, ChainableUndefined, Environment

from finpilot.database.models import (
    FewShotExample,
    PromptABTest,
    PromptABTestResult,
    PromptTemplate,
    PromptVersion,
)

logger = logging.getLogger(__name__)

# Few-shot 注入默认数量
DEFAULT_FEW_SHOT_LIMIT = 3
# 变量占位符：{name} 或 {name.field}
_VAR_RE = re.compile(r"\{([a-zA-Z_][\w]*(?:\.[\w]+)*)\}")
# for-loop 迭代对象添加 default([], true) 以兼容 None / undefined
_FOR_IN_RE = re.compile(r"(\{%\s*for\s+\w+\s+in\s+)(\w+(?:\.\w+)*)\s*%\}")


# ---------------------------------------------------------------------------
# 条件模板渲染（Jinja2）
# ---------------------------------------------------------------------------


class _KeepUndefined(ChainableUndefined):
    """未定义变量渲染回 ``{name}`` 形式，保留给后续步骤处理。

    继承 ChainableUndefined 以支持 ``{ex.input}`` 等属性访问；
    迭代为空、布尔值为 False，与原手写实现行为一致。
    """

    def __str__(self) -> str:
        name = self._undefined_name
        return "{" + str(name) + "}" if name else ""


def _finalize(value: Any) -> Any:
    """None 渲染为空字符串，与原实现一致。"""
    if value is None:
        return ""
    return value


_jinja_env = Environment(
    loader=BaseLoader(),
    undefined=_KeepUndefined,
    autoescape=False,
    finalize=_finalize,
)


def _convert_to_jinja_syntax(template: str) -> str:
    """将 ``{name}`` 占位符转为 Jinja2 的 ``{{ name }}``。

    同时为 ``{% for x in var %}`` 的迭代对象添加 ``|default([], true)``，
    使 None / undefined 变量安全退化为空迭代。
    """
    # {name} → {{ name }}
    template = _VAR_RE.sub(lambda m: "{{ " + m.group(1) + " }}", template)
    # {% for x in var %} → {% for x in var|default([], true) %}
    template = _FOR_IN_RE.sub(r"\1\2|default([], true) %}", template)
    return template


def _coerce_literal(token: str) -> Any:
    """把字面量字符串解析为 Python 值（字符串/数字），否则原样返回."""
    token = token.strip()
    if len(token) >= 2 and (
        (token[0] == token[-1] == '"') or (token[0] == token[-1] == "'")
    ):
        return token[1:-1]
    # 数字
    try:
        if "." in token:
            return float(token)
        return int(token)
    except ValueError:
        return token


def _resolve_value(name: str, variables: dict, ctx: dict) -> Any:
    """解析变量引用，支持点号属性访问.

    查找顺序：loop 上下文(ctx) → 顶层变量(variables) → 字面量。
    """
    name = name.strip()
    # 字面量
    lit = _coerce_literal(name)
    if lit != name:
        return lit
    parts = name.split(".")
    if parts[0] in ctx:
        val: Any = ctx[parts[0]]
    elif parts[0] in variables:
        val = variables[parts[0]]
    else:
        return None
    for p in parts[1:]:
        if isinstance(val, dict):
            val = val.get(p)
        elif val is None:
            return None
        else:
            val = getattr(val, p, None)
    return val


def render_conditionals(template: str, variables: dict[str, Any] | None = None) -> str:
    """渲染条件模板（{% if %} / {% for %}）.

    这是引擎对外暴露的纯函数渲染入口，``render_prompt`` 也复用它。
    循环变量在循环体内即时解析，顶层 ``{variable}`` 占位符被替换为已知变量，
    未知的（如 ``{few_shot_examples}``）原样保留以供后续步骤处理。
    """
    variables = variables or {}
    jinja_source = _convert_to_jinja_syntax(template)
    try:
        return _jinja_env.from_string(jinja_source).render(**variables)
    except Exception:
        # Jinja2 渲染失败时退回到仅替换已知变量
        return substitute_variables(template, variables)


def substitute_variables(template: str, variables: dict[str, Any]) -> str:
    """替换顶层 ``{variable}`` 占位符（步骤 5）.

    使用安全替换：仅替换存在于 variables 中的键，未知占位符原样保留，
    避免 ``str.format`` 在遇到 ``{%`` 或未知字段时抛错。
    """

    def repl(m: re.Match[str]) -> str:
        name = m.group(1)
        first = name.split(".")[0]
        if first in variables:
            val = _resolve_value(name, variables, {})
            return "" if val is None else str(val)
        return m.group(0)

    return _VAR_RE.sub(repl, template)


# ---------------------------------------------------------------------------
# Few-shot 注入
# ---------------------------------------------------------------------------

_FEW_SHOT_PLACEHOLDER = "{few_shot_examples}"


def get_few_shot_examples(
    prompt_key: str,
    tenant_id: str,
    db: Session,
    limit: int = DEFAULT_FEW_SHOT_LIMIT,
) -> list[FewShotExample]:
    """加载该 prompt_key 下激活的 few-shot 示例，按质量分降序取 Top-N."""
    query = (
        db.query(FewShotExample)
        .filter(
            FewShotExample.tenant_id == tenant_id,
            FewShotExample.prompt_key == prompt_key,
            FewShotExample.is_active.is_(True),
        )
        .order_by(
            FewShotExample.quality_score.desc(),
            FewShotExample.display_order.asc(),
        )
    )
    return query.limit(limit).all()


def _format_few_shot(examples: list[FewShotExample]) -> str:
    """将示例格式化为注入文本."""
    if not examples:
        return ""
    blocks: list[str] = ["示例:"]
    for ex in examples:
        blocks.append(f"输入: {ex.input_text}")
        blocks.append(f"输出: {ex.output_text}")
        blocks.append("")  # 空行分隔
    return "\n".join(blocks).rstrip()


def inject_few_shot(template: str, examples: list[FewShotExample]) -> str:
    """在 ``{few_shot_examples}`` 占位处注入示例文本."""
    text = _format_few_shot(examples)
    return template.replace(_FEW_SHOT_PLACEHOLDER, text)


# ---------------------------------------------------------------------------
# A/B 测试
# ---------------------------------------------------------------------------


def _now(db: Session) -> datetime:
    """获取数据库当前时间，失败则用本地 UTC."""
    try:
        from sqlalchemy import text as sql_text
        row = db.execute(sql_text("CURRENT_TIMESTAMP")).scalar()
        if isinstance(row, datetime):
            return row
    except Exception:  # noqa: BLE001
        pass
    return datetime.now(timezone.utc)


def find_active_ab_test(
    prompt_key: str,
    tenant_id: str,
    db: Session,
) -> PromptABTest | None:
    """查找该 prompt_key 下正在运行的 A/B 测试."""
    now = _now(db)
    return (
        db.query(PromptABTest)
        .filter(
            PromptABTest.tenant_id == tenant_id,
            PromptABTest.prompt_key == prompt_key,
            PromptABTest.status == "running",
        )
        .filter(
            PromptABTest.start_time.is_(None) | (PromptABTest.start_time <= now),
        )
        .order_by(PromptABTest.created_at.desc())
        .first()
    )


def assign_ab_variant(test_id: str, session_id: str, db: Session) -> str:
    """基于 session_id 哈希确定性分流，返回 'a' 或 'b'.

    同一 session_id 始终分到同一变体，保证用户体验一致。
    """
    test = db.query(PromptABTest).filter(PromptABTest.id == test_id).first()
    if test is None:
        return "a"
    split = test.traffic_split_b or 0.0
    # 将 session_id 哈希到 0-99 的整数
    digest = hashlib.md5((test_id + "|" + (session_id or "")).encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 100
    return "b" if bucket < split else "a"


def record_ab_result(
    test_id: str,
    variant: str,
    session_id: str | None,
    feedback: str | None,
    quality_score: float | None,
    latency_ms: int,
    token_count: int,
    db: Session,
) -> PromptABTestResult:
    """记录一次 A/B 测试结果."""
    result = PromptABTestResult(
        test_id=test_id,
        variant=variant,
        session_id=session_id,
        user_feedback=feedback,
        response_quality_score=quality_score,
        latency_ms=latency_ms,
        token_count=token_count,
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return result


# ---------------------------------------------------------------------------
# 版本管理
# ---------------------------------------------------------------------------


def create_version(
    prompt_id: str,
    content: str,
    change_description: str | None,
    db: Session,
    created_by: str | None = None,
    variables: dict | None = None,
) -> PromptVersion:
    """为模板创建新版本并设为激活，旧版本全部置为非激活."""
    # 计算下一个版本号
    last = (
        db.query(PromptVersion)
        .filter(PromptVersion.prompt_id == prompt_id)
        .order_by(PromptVersion.version.desc())
        .first()
    )
    next_version = (last.version + 1) if last else 1

    # 旧版本置为非激活
    db.query(PromptVersion).filter(
        PromptVersion.prompt_id == prompt_id,
        PromptVersion.is_active_version.is_(True),
    ).update({PromptVersion.is_active_version: False}, synchronize_session=False)

    version = PromptVersion(
        prompt_id=prompt_id,
        version=next_version,
        content=content,
        variables=variables,
        change_description=change_description,
        created_by=created_by,
        is_active_version=True,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    logger.info("prompt_version_created", prompt_id=prompt_id, version=next_version)
    return version


def rollback_to_version(
    prompt_id: str,
    version: int,
    db: Session,
    created_by: str | None = None,
) -> PromptTemplate:
    """回滚模板到指定历史版本.

    会把模板内容更新为该版本内容，并新建一条版本记录用于审计。
    """
    tpl = db.query(PromptTemplate).filter(PromptTemplate.id == prompt_id).first()
    if tpl is None:
        raise ValueError(f"模板 {prompt_id} 不存在")

    target = (
        db.query(PromptVersion)
        .filter(
            PromptVersion.prompt_id == prompt_id,
            PromptVersion.version == version,
        )
        .first()
    )
    if target is None:
        raise ValueError(f"版本 {version} 不存在")

    # 更新模板内容
    tpl.content = target.content
    if target.variables is not None:
        import json
        tpl.variables = json.dumps(target.variables, ensure_ascii=False) if isinstance(
            target.variables, (dict, list)
        ) else tpl.variables
    db.commit()
    db.refresh(tpl)

    # 新建审计版本
    create_version(
        prompt_id=prompt_id,
        content=target.content,
        change_description=f"回滚到版本 {version}",
        db=db,
        created_by=created_by,
        variables=target.variables,
    )

    # 失效缓存
    try:
        from finpilot.services.prompt_loader import _invalidate_cache
        _invalidate_cache()
    except Exception:  # noqa: BLE001
        pass

    logger.info("prompt_rolled_back", prompt_id=prompt_id, version=version)
    return tpl


# ---------------------------------------------------------------------------
# 高级渲染
# ---------------------------------------------------------------------------


def _load_template_content(
    key: str,
    tenant_id: str,
    db: Session | None,
) -> str:
    """加载模板内容，优先 DB 激活版本，降级硬编码默认.

    复用 prompt_loader.get_prompt 以保持默认值一致。
    """
    from finpilot.services.prompt_loader import get_prompt
    return get_prompt(key, tenant_id, db)


def render_prompt_advanced(
    key: str,
    tenant_id: str,
    variables: dict[str, Any],
    db: Session | None = None,
) -> str:
    """高级渲染入口 — A/B 分流 + 条件渲染 + few-shot + 变量替换.

    步骤:
      1. 检查是否有运行中的 A/B 测试 → 决定使用哪个变体
      2. 加载模板内容（激活版本 / 默认降级）
      3. 渲染条件模板（{% if %} / {% for %}）
      4. 注入 few-shot 示例
      5. 替换 {variable} 占位符
      6. 记录 A/B 分流结果
      7. 返回最终提示词
    """
    variables = variables or {}
    session_id = str(variables.get("session_id") or variables.get("_session_id") or "")

    # 1. A/B 测试分流
    content: str | None = None
    ab_test: PromptABTest | None = None
    variant = "a"
    if db is not None:
        ab_test = find_active_ab_test(key, tenant_id, db)
        if ab_test is not None:
            variant = assign_ab_variant(ab_test.id, session_id, db)
            variant_id = ab_test.variant_a_id if variant == "a" else ab_test.variant_b_id
            if variant_id:
                tpl = db.query(PromptTemplate).filter(PromptTemplate.id == variant_id).first()
                if tpl and tpl.content:
                    content = tpl.content

    # 2. 加载内容（A/B 变体或默认）
    if content is None:
        content = _load_template_content(key, tenant_id, db)

    # 3. 条件渲染
    rendered = render_conditionals(content, variables)

    # 4. 注入 few-shot 示例
    if db is not None:
        examples = get_few_shot_examples(key, tenant_id, db, DEFAULT_FEW_SHOT_LIMIT)
        rendered = inject_few_shot(rendered, examples)

    # 5. 变量替换
    rendered = substitute_variables(rendered, variables)

    # 6. 记录 A/B 分流
    if ab_test is not None and db is not None:
        try:
            _record_assignment(ab_test.id, variant, session_id, db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ab_assignment_record_failed", error=str(exc))

    return rendered


def _record_assignment(test_id: str, variant: str, session_id: str, db: Session) -> None:
    """记录分流结果，同一会话仅记录一次."""
    if not session_id:
        return
    existing = (
        db.query(PromptABTestResult)
        .filter(
            PromptABTestResult.test_id == test_id,
            PromptABTestResult.session_id == session_id,
        )
        .first()
    )
    if existing is not None:
        return
    result = PromptABTestResult(
        test_id=test_id,
        variant=variant,
        session_id=session_id,
        latency_ms=0,
        token_count=0,
    )
    db.add(result)
    db.commit()


# ---------------------------------------------------------------------------
# 评估
# ---------------------------------------------------------------------------


def _score_output(
    output: str,
    expected: str | None,
    match_type: str,
) -> float:
    """按匹配类型评分 (0-1)."""
    return score_output(output, expected, match_type)


def score_output(
    output: str,
    expected: str | None,
    match_type: str,
) -> float:
    """按匹配类型评分 (0-1).

    match_type:
      - exact: 渲染结果与期望完全一致得 1.0
      - contains: 渲染结果包含期望文本得 1.0
      - 其它/无期望: 0.0
    """
    if expected is None:
        return 0.0
    if match_type == "exact":
        return 1.0 if output.strip() == expected.strip() else 0.0
    if match_type == "contains":
        return 1.0 if expected.strip() in output else 0.0
    return 0.0


def evaluate_prompt(
    key: str,
    test_cases: list[dict],
    tenant_id: str,
    db: Session,
    use_llm: bool = False,
    pass_threshold: float = 0.6,
) -> dict:
    """对提示词运行测试用例并评分.

    每个 test_case 字段:
      - variables: 渲染变量
      - expected: 期望渲染结果（可选）
      - match_type: exact / contains / llm_judge（默认 contains）
      - input: llm_judge 时的用户输入（可选）

    返回 {total, passed, avg_score, avg_latency, results}。
    """
    results: list[dict] = []
    total_score = 0.0
    total_latency = 0.0
    passed = 0

    for idx, tc in enumerate(test_cases):
        variables = tc.get("variables", {}) or {}
        expected = tc.get("expected")
        match_type = tc.get("match_type", "contains")
        user_input = tc.get("input", "")

        start = time.monotonic()
        try:
            rendered = render_prompt_advanced(key, tenant_id, variables, db)
            output = rendered
            score: float

            if match_type == "llm_judge" and use_llm:
                try:
                    from finpilot.llm.client import LLMClient
                    client = LLMClient()
                    output = client.chat(system_prompt=rendered, user_prompt=user_input)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("evaluate_llm_failed", case=idx, error=str(exc))
                    output = rendered

            score = _score_output(output, expected, match_type)
        except Exception as exc:  # noqa: BLE001
            logger.warning("evaluate_case_failed", case=idx, error=str(exc))
            rendered = ""
            output = ""
            score = 0.0

        latency_ms = int((time.monotonic() - start) * 1000)
        total_score += score
        total_latency += latency_ms
        if score >= pass_threshold:
            passed += 1

        results.append({
            "case_index": idx,
            "rendered": rendered,
            "output": output,
            "expected": expected,
            "match_type": match_type,
            "score": round(score, 4),
            "latency_ms": latency_ms,
            "passed": score >= pass_threshold,
        })

    total = len(test_cases)
    return {
        "total": total,
        "passed": passed,
        "avg_score": round(total_score / total, 4) if total else 0.0,
        "avg_latency": int(total_latency / total) if total else 0,
        "results": results,
    }
