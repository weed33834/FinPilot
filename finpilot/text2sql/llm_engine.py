# -*- coding: utf-8 -*-
"""
LLM 引擎
- 用 LLMClient 生成 SQL，system prompt 内嵌 schema 上下文
- 生成后自动走 SQLSandbox.validate
- LLM 不可用时返回 confidence=0 的空结果（降级）
"""
import re

from sqlalchemy.exc import SQLAlchemyError

from finpilot.database.connection import SessionLocal
from finpilot.llm.client import LLMClient, LLMUnavailableError
from finpilot.llm.config import get_default_config

from .engine import NL2SQLResult
from .sandbox import SQLSandbox
from .schema import FINANCIAL_TABLES, build_schema_context

# LLM 命中置信度
_LLM_CONFIDENCE = 0.85


def _get_client(db=None) -> LLMClient | None:
    """获取 LLM 客户端；db 为 None 时临时创建会话，配置命中 60s 缓存
    配置加载失败（表缺失/DB异常）视为 LLM 不可用，返回 None 触发降级"""
    session = db
    owned = False
    if session is None:
        session = SessionLocal()
        owned = True
    try:
        config = get_default_config(session)
    except SQLAlchemyError:
        # 配置表缺失或查询异常 -> LLM 不可用，降级返回 None
        return None
    finally:
        # 配置已缓存，临时会话即可关闭；LLMClient 构造后不再依赖会话
        if owned:
            session.close()

    if config is None:
        return None
    return LLMClient(config)


def _extract_sql(text: str) -> str:
    """从 LLM 输出中提取 SQL：优先代码块，其次首个 SELECT 语句"""
    # ```sql ... ```
    m = re.search(r"```sql\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # ``` ... ```
    m = re.search(r"```\s*(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # 首个 SELECT ... 到分号或结尾
    m = re.search(r"(SELECT\b.*?)(?:;|$)", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return text.strip()


class LLMEngine:
    """基于 LLMClient 的 NL2SQL 引擎"""

    def __init__(self) -> None:
        self.sandbox = SQLSandbox(list(FINANCIAL_TABLES.keys()))

    def generate_sql(self, question: str, db=None) -> NL2SQLResult:
        """用 LLM 生成 SQL，生成后自动校验；LLM 不可用降级为空结果"""
        client = _get_client(db)
        if client is None:
            return NL2SQLResult(
                confidence=0.0, backend="llm",
                explanation="LLM不可用", error="LLM不可用",
            )

        system_prompt = (
            build_schema_context()
            + "\n\n你是财务 SQL 生成专家。根据用户问题生成对应的 SELECT 查询，"
            "只输出纯 SQL，不要解释、不要 markdown 代码块、不要分号结尾。"
        )
        user_prompt = f"问题: {question}\n请生成对应的 SELECT SQL。"
        try:
            resp = client.chat(system_prompt, user_prompt, temperature=0.2, max_tokens=1000)
        except LLMUnavailableError as exc:
            # LLM 调用失败降级为空结果
            return NL2SQLResult(
                confidence=0.0, backend="llm",
                explanation="LLM调用失败", error=str(exc),
            )

        sql = _extract_sql(resp)
        # 生成后自动走沙箱校验
        ok, reason = self.sandbox.validate(sql)
        return NL2SQLResult(
            sql=sql,
            confidence=_LLM_CONFIDENCE if ok else 0.0,
            backend="llm",
            explanation="LLM生成" + ("" if ok else f"(校验未通过: {reason})"),
            error="" if ok else reason,
        )
