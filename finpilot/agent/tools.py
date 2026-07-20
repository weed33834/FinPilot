"""内置工具注册 - nl2sql / document_qa / parse_document / validate / debate / explain / risk。

每个工具用 ``@tool_registry.register`` 装饰器注册，函数签名统一为
``(ctx: ToolContext, **kwargs) -> dict``。导入本模块即完成注册（副作用）。
"""
from __future__ import annotations

import json
from typing import Any

from finpilot.parser import ParserError, get_parser
from finpilot.rag.service import RagService
from finpilot.text2sql.engine import NL2SQLEngine

from .tool_registry import ToolContext, tool_registry


@tool_registry.register(
    name="nl2sql",
    description=(
        "将自然语言问题转换为 SQL 并在财务数据库上执行，"
        "返回 sql/columns/rows/explanation。用于财务数据查询、统计、汇总。"
    ),
    parameters_schema={"question": "str,必填,自然语言查询问题"},
    tags=["data", "sql"],
)
def nl2sql(ctx: ToolContext, **kwargs: Any) -> dict:
    question = kwargs.get("question") or ""
    if not question:
        return {"error": "缺少参数: question"}
    if ctx.db is None:
        # 无数据库会话无法执行 SQL，返回错误供上层降级/回灌
        return {"error": "无数据库会话，无法执行 SQL"}
    # 双引擎：规则优先，LLM 兜底；execute 内部完成生成+沙箱+执行
    engine = NL2SQLEngine(ctx.db)
    return engine.execute(question, ctx.db)


@tool_registry.register(
    name="document_qa",
    description=(
        "基于已索引的文档进行检索问答，返回 answer/chunks/document_id。"
        "用于针对上传文档内容提问。"
    ),
    parameters_schema={
        "question": "str,必填,问题",
        "document_id": "int,可选,限定文档ID",
    },
    tags=["rag", "document"],
)
def document_qa(ctx: ToolContext, **kwargs: Any) -> dict:
    question = kwargs.get("question") or ""
    document_id = kwargs.get("document_id")
    if not question:
        return {"error": "缺少参数: question"}
    # document_id 归一化为 int 或 None，容忍 LLM 传字符串
    if document_id is not None:
        try:
            document_id = int(document_id)
        except (TypeError, ValueError):
            document_id = None
    service = RagService(ctx.db)
    return service.query(
        question, tenant_id=ctx.tenant_id, document_id=document_id
    )


@tool_registry.register(
    name="parse_document",
    description=(
        "解析上传的文档文件(pdf/xlsx/xls/csv/docx)，返回 filename/file_type/"
        "pages/tables/metadata。用于读取财务文档内容。"
    ),
    parameters_schema={"file_path": "str,必填,文档路径"},
    tags=["parser", "document"],
)
def parse_document(ctx: ToolContext, **kwargs: Any) -> dict:
    file_path = kwargs.get("file_path") or ""
    if not file_path:
        return {"error": "缺少参数: file_path"}
    try:
        parser = get_parser(file_path)
        doc = parser.parse(file_path)
    except ParserError as exc:
        # 文件不存在/格式不支持等可预期错误，包装为错误字典
        return {"error": str(exc)}
    return {
        "filename": doc.filename,
        "file_type": doc.file_type,
        "pages": [
            {"page_number": p.page_number, "text": p.text} for p in doc.pages
        ],
        "tables": doc.tables,
        "metadata": doc.metadata,
    }


# ---------------------------------------------------------------------------
# 财务智能体增强工具（阶段 C 引入）
# 4 个工具分别对接 P0-3 数据校验 / P0-4 多智能体辩论 / P0-5 可解释 AI / P0-6 风险预警
# 工具签名统一 (ctx, **kwargs) -> dict，便于 ReAct 调用
# ---------------------------------------------------------------------------


@tool_registry.register(
    name="validate_financial_data",
    description=(
        "对企业财务数据做 9 类异常校验（试算平衡/除零/时间穿越/负数资产/精度损失/"
        "汇率异常/账龄异常/凭证号格式/关联交易），返回 ValidationReport。"
        "用于上传数据后入口校验、报表生成前自检。"
    ),
    parameters_schema={
        "data": "dict,必填,待校验数据，键可为 journal_lines/division/transactions/"
        "assets/receivables/vouchers/exchange_rates/related_party_transactions/closing_date/opening_date",
    },
    tags=["validation", "finance"],
)
def validate_financial_data(ctx: ToolContext, **kwargs: Any) -> dict:
    raw = kwargs.get("data")
    if raw is None:
        # 兼容 LLM 直接传 journal_lines 等顶层字段
        raw = {k: v for k, v in kwargs.items() if k != "question"}
    if not raw:
        return {"error": "缺少参数: data（或 journal_lines/transactions 等字段）"}

    from finpilot.validation import validate_financial_data as _validate

    # 解析 date 字段（ISO 字符串 → date）
    parsed: dict[str, Any] = dict(raw)
    for k in ("closing_date", "opening_date"):
        v = parsed.get(k)
        if isinstance(v, str):
            try:
                from datetime import date as _date
                parsed[k] = _date.fromisoformat(v)
            except ValueError:
                parsed[k] = None
    try:
        report = _validate(**parsed)
    except TypeError as exc:
        return {"error": f"参数格式错误: {exc}"}
    return report.to_dict()


@tool_registry.register(
    name="investment_debate",
    description=(
        "多智能体对抗辩论：4 角色（研究分析师/看多/看空/风控/投资经理）N 轮辩论，"
        "返回 DebateResult（含 bull/bear 论点、风险评估、PM 决策、证据链）。"
        "用于投资标的的深度分析（如：分析贵州茅台 2024 年投资价值）。"
    ),
    parameters_schema={
        "question": "str,必填,投研问题",
        "max_rounds": "int,可选,辩论轮数（默认3）",
    },
    tags=["debate", "investment"],
)
def investment_debate(ctx: ToolContext, **kwargs: Any) -> dict:
    question = kwargs.get("question") or ""
    if not question:
        return {"error": "缺少参数: question"}
    max_rounds = kwargs.get("max_rounds")
    if max_rounds is not None:
        try:
            max_rounds = int(max_rounds)
        except (TypeError, ValueError):
            max_rounds = None

    from .debate import run_debate

    try:
        result = run_debate(
            question, db=ctx.db, max_rounds=max_rounds
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": f"辩论执行失败({type(exc).__name__}): {exc}"}
    return result.to_dict()


@tool_registry.register(
    name="explain_decision",
    description=(
        "对 Agent 的最终答案做可解释性归因：因子归因（SHAP-lite）+ 决策追溯"
        "（证据链回查）+ LLM 自解释，返回 ExplainabilityReport。"
        "用于关键决策（投资/审计/风险预警）的事后解释与审计。"
    ),
    parameters_schema={
        "question": "str,必填,用户原始问题",
        "answer": "str,必填,Agent 最终答案",
        "steps": "list,可选,ReAct 草稿本",
        "features": "dict,可选,因子值字典",
        "confidence": "float,可选,模型置信度",
    },
    tags=["explainability", "audit"],
)
def explain_decision(ctx: ToolContext, **kwargs: Any) -> dict:
    question = kwargs.get("question") or ""
    answer = kwargs.get("answer") or ""
    if not question or not answer:
        return {"error": "缺少参数: question / answer"}
    steps = kwargs.get("steps") or []
    # steps 可能是 JSON 字符串（LLM 传字符串时）
    if isinstance(steps, str):
        try:
            steps = json.loads(steps)
        except json.JSONDecodeError:
            steps = []
    if not isinstance(steps, list):
        steps = []
    features = kwargs.get("features")
    if isinstance(features, str):
        try:
            features = json.loads(features)
        except json.JSONDecodeError:
            features = None
    confidence = kwargs.get("confidence") or 0.0
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0

    from .explainability import explain_decision as _explain

    try:
        report = _explain(
            question, answer, steps,
            features=features, confidence=confidence, db=ctx.db,
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": f"解释失败({type(exc).__name__}): {exc}"}
    return report.to_dict()


@tool_registry.register(
    name="assess_risk",
    description=(
        "风险预警引擎：时序预测（SMA/ETS）+ 风险区间分类（7 个指标阈值）+ "
        "财务舞弊识别（4 类信号：期末激增/营收应收背离/现金利润背离/存货毛利异常）"
        "+ 预警规则评估（5 条默认规则），返回 RiskReport。"
        "用于财务健康度监控、舞弊识别、风险预警。"
    ),
    parameters_schema={
        "data": "dict,必填,风险数据，键可为 metrics/monthly_revenue/revenue_growth/"
        "ar_growth/net_profit/operating_cash_flow/inventory_turnover_current/"
        "inventory_turnover_prev/gross_margin_current/gross_margin_prev/forecast_series",
    },
    tags=["risk", "finance"],
)
def assess_risk(ctx: ToolContext, **kwargs: Any) -> dict:
    raw = kwargs.get("data")
    if raw is None:
        raw = {k: v for k, v in kwargs.items() if k != "question"}
    if not raw:
        return {"error": "缺少参数: data（或 metrics/monthly_revenue 等字段）"}

    from finpilot.risk import assess_risk as _assess

    try:
        report = _assess(**dict(raw))
    except TypeError as exc:
        return {"error": f"参数格式错误: {exc}"}
    return report.to_dict()
