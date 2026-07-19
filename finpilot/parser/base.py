"""文档解析层基类与统一数据模型。

定义解析结果的统一数据结构（ParsedDocument / ParsedPage）、
所有解析器的抽象基类 BaseParser，以及按扩展名分发的工厂函数 get_parser。
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class ParserError(Exception):
    """文档解析统一异常：文件不存在、格式错误、解析失败等均包装为本异常。"""


@dataclass
class ParsedPage:
    """单页解析结果。

    Attributes:
        page_number: 页码（从 1 开始；Excel 中即 sheet 序号）。
        text: 该页纯文本内容。
        tables: 该页表格列表，每张表为 list[list[str]]。
    """

    page_number: int
    text: str = ""
    tables: list[list[list[str]]] = field(default_factory=list)


@dataclass
class ParsedDocument:
    """整篇文档解析结果。

    Attributes:
        filename: 文件名（不含目录）。
        file_type: 文件类型标识，如 pdf/xlsx/xls/csv/docx。
        pages: 各页解析结果。
        tables: 全文档汇总的表格列表，每张表为 list[list[str]]。
        metadata: 附加元信息（页数、sheet 名等）。
    """

    filename: str
    file_type: str
    pages: list[ParsedPage] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseParser(ABC):
    """所有文档解析器的抽象基类。"""

    @staticmethod
    def _check_file(file_path: str) -> str:
        """校验文件存在，返回文件名；不存在则抛出 ParserError。"""
        if not os.path.isfile(file_path):
            raise ParserError(f"文件不存在: {file_path}")
        return os.path.basename(file_path)

    @abstractmethod
    def parse(self, file_path: str) -> ParsedDocument:
        """解析文档，返回统一的 ParsedDocument。"""
        ...


def get_parser(file_path: str) -> BaseParser:
    """工厂函数：按文件扩展名返回对应的解析器实例。

    支持扩展名: .pdf .xlsx .xls .csv .docx .doc
    """
    ext = os.path.splitext(file_path)[1].lower().lstrip(".")
    # 懒加载各解析器，避免与 base 产生循环导入
    if ext == "pdf":
        from .pdf_parser import PdfParser

        return PdfParser()
    if ext in ("xlsx", "xls"):
        from .excel_parser import ExcelParser

        return ExcelParser()
    if ext == "csv":
        from .csv_parser import CsvParser

        return CsvParser()
    if ext in ("docx", "doc"):
        from .docx_parser import DocxParser

        return DocxParser()
    raise ParserError(f"不支持的文件格式: .{ext}")
