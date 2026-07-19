"""文档解析模块：统一接口导出。

用法:
    from finpilot.parser import get_parser, ParsedDocument, ParserError

    parser = get_parser("report.pdf")
    doc = parser.parse("report.pdf")
"""
from .base import (
    BaseParser,
    ParsedDocument,
    ParsedPage,
    ParserError,
    get_parser,
)

__all__ = [
    "BaseParser",
    "ParsedDocument",
    "ParsedPage",
    "ParserError",
    "get_parser",
]
