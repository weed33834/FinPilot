"""内置工具注册 - nl2sql / document_qa / parse_document。

每个工具用 ``@tool_registry.register`` 装饰器注册，函数签名统一为
``(ctx: ToolContext, **kwargs) -> dict``。导入本模块即完成注册（副作用）。
"""
from __future__ import annotations

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
