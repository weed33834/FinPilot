"""
意图识别 - 判定用户问题意图并抽取结构化参数
- 优先规则匹配（关键词 -> 意图），无匹配时调用 LLM 分类
- 所有 LLM 调用均有失败降级（LLM 不可用时返回规则/默认结果）
"""
import json
import logging
import re
from typing import Optional

from .client import LLMClient, LLMUnavailableError
from .config import get_default_config

logger = logging.getLogger(__name__)

# 合法意图集合
VALID_INTENTS = {"nl2sql", "create_report", "parse_document", "document_qa", "unknown"}

# 关键词 -> 意图 规则映射（按匹配优先级排列）
_INTENT_RULES = [
    ("create_report", ("生成报告", "创建报告", "出一份报告", "写报告", "做报告")),
    ("parse_document", ("解析文档", "解析文件", "提取文档", "读取文档", "上传文档")),
    ("document_qa", ("文档里", "文档中", "根据文档", "这份文档", "文章里", "合同里")),
    ("nl2sql", (
        "查询", "统计", "汇总", "列表", "多少条", "排序", "分组", "SQL",
        # 常见财务问句模式：借贷 / 总额 / 余额 / 收入 / 利润 / 资产 / 负债
        "借贷", "总额", "余额", "收入", "利润", "资产", "负债",
        "是多少", "多少", "占比", "同比", "环比", "增长率",
        "账龄", "科目", "凭证", "分录", "试算", "报表",
    )),
]


def classify_intent(
    question: str,
    history: Optional[list] = None,
    db=None,
) -> dict:
    """
    识别用户意图，返回 {"intent": str, "reasoning": str}
    优先规则匹配，无匹配时调用 LLM 分类（失败则降级为 unknown）
    """
    # 1. 规则匹配优先
    intent, reasoning = _match_rule(question)
    if intent is not None:
        return {"intent": intent, "reasoning": reasoning}

    # 2. 无 db 时直接降级
    if db is None:
        return {"intent": "unknown", "reasoning": "无 db 上下文，规则未命中，降级为 unknown"}

    # 3. LLM 分类（带降级）
    llm_result = _classify_by_llm(question, history, db)
    if llm_result is not None:
        return llm_result

    # 4. 降级：规则与 LLM 均未命中
    return {"intent": "unknown", "reasoning": "规则与 LLM 均未命中，降级为 unknown"}


def _match_rule(question: str) -> tuple[Optional[str], str]:
    """关键词规则匹配，返回 (意图, 推理说明)；未命中返回 (None, "")"""
    for intent, keywords in _INTENT_RULES:
        for kw in keywords:
            if kw in question:
                return intent, f"规则命中关键词「{kw}」-> {intent}"
    return None, ""


def _classify_by_llm(question: str, history: Optional[list], db) -> Optional[dict]:
    """调用 LLM 进行意图分类，失败时返回 None 触发降级"""
    try:
        config = get_default_config(db)
        if config is None:
            return None
        client = LLMClient(config)
        system_prompt = (
            "你是意图分类器。将用户问题分类为以下意图之一："
            "nl2sql(数据查询), create_report(生成报告), "
            "parse_document(解析文档), document_qa(文档问答), unknown(无法判断)。"
            '仅输出 JSON：{"intent": "...", "reasoning": "..."}'
        )
        user_prompt = f"问题：{question}"
        raw = client.chat(system_prompt, user_prompt, temperature=0.0, max_tokens=200)
        return _parse_llm_intent(raw)
    except LLMUnavailableError as exc:
        # LLM 不可用时降级
        logger.warning("LLM 意图分类失败，降级处理: %s", exc)
        return None


def _parse_llm_intent(raw: str) -> Optional[dict]:
    """解析 LLM 返回的 JSON 意图结果，校验意图合法性"""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    intent = data.get("intent", "unknown")
    if intent not in VALID_INTENTS:
        intent = "unknown"
    return {"intent": intent, "reasoning": data.get("reasoning", "LLM 分类")}


def extract_parameters(
    question: str,
    intent: str,
    history: Optional[list] = None,
    db=None,
) -> dict:
    """
    从问题中抽取结构化参数
    返回 {"title", "report_type", "year", "period", "document_id", "question"}
    优先规则抽取，复杂场景调用 LLM 增强（失败降级为规则结果）
    """
    params = _extract_by_rule(question, intent)

    # 仅在需要结构化参数的意图下尝试 LLM 增强（带降级）
    if db is not None and intent in ("create_report", "nl2sql"):
        llm_params = _extract_by_llm(question, intent, db)
        if llm_params is not None:
            # LLM 结果覆盖规则结果中为空的字段
            for key, value in llm_params.items():
                if value:
                    params[key] = value

    params["question"] = question
    return params


def _extract_by_rule(question: str, intent: str) -> dict:
    """基于正则的参数抽取"""
    params = {
        "title": None,
        "report_type": None,
        "year": None,
        "period": None,
        "document_id": None,
    }

    # 年份抽取：4 位数字年份（2000-2099）
    year_match = re.search(r"(20\d{2})", question)
    if year_match:
        params["year"] = year_match.group(1)

    # 报表类型识别
    if "资产负债" in question or "balance" in question.lower():
        params["report_type"] = "balance_sheet"
    elif "利润" in question or "损益" in question or "income" in question.lower():
        params["report_type"] = "income_statement"
    elif "现金流" in question or "cash" in question.lower():
        params["report_type"] = "cash_flow"

    # 期间识别：如 2024-Q1 / Q1 / H1 / FY / 年度 / 季度
    period_match = re.search(r"(\d{4}[-]?)?(Q[1-4]|H[12]|FY|年度|季度)", question)
    if period_match:
        params["period"] = period_match.group(0)

    # 报告标题：create_report 意图下取书名号/引号内文本，否则截取前缀
    if intent == "create_report":
        title_match = re.search(r"[《\"](.+?)[》\"]", question)
        params["title"] = title_match.group(1) if title_match else question[:30]

    return params


def _extract_by_llm(question: str, intent: str, db) -> Optional[dict]:
    """调用 LLM 抽取参数，失败返回 None 触发降级"""
    try:
        config = get_default_config(db)
        if config is None:
            return None
        client = LLMClient(config)
        system_prompt = (
            "你是参数抽取器。从用户问题中抽取以下字段，缺失填 null："
            "title(报告标题), report_type(balance_sheet/income_statement/cash_flow), "
            "year(4位年份), period(如 2024-Q1), document_id(文档ID)。"
            "仅输出 JSON。"
        )
        raw = client.chat(system_prompt, question, temperature=0.0, max_tokens=300)
        return _parse_llm_params(raw)
    except LLMUnavailableError as exc:
        # LLM 不可用时降级为规则结果
        logger.warning("LLM 参数抽取失败，降级处理: %s", exc)
        return None


def _parse_llm_params(raw: str) -> Optional[dict]:
    """解析 LLM 返回的 JSON 参数，做类型归一化"""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    def _str_or_none(value) -> Optional[str]:
        """非空值统一转为字符串，None/空保留为 None"""
        if value is None or value == "":
            return None
        return str(value)

    return {
        "title": _str_or_none(data.get("title")),
        "report_type": _str_or_none(data.get("report_type")),
        "year": _str_or_none(data.get("year")),
        "period": _str_or_none(data.get("period")),
        "document_id": _str_or_none(data.get("document_id")),
    }
