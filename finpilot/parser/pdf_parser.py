"""PDF 文档解析器：基于 pdfplumber 逐页提取文本与表格。"""
from __future__ import annotations

import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfminer.pdfparser import PDFSyntaxError
from pdfplumber.utils.exceptions import PdfminerException

from .base import BaseParser, ParsedDocument, ParsedPage, ParserError


class PdfParser(BaseParser):
    """解析 PDF 文件，保留页码信息，表格转为 list[list[str]]。"""

    def parse(self, file_path: str) -> ParsedDocument:
        filename = self._check_file(file_path)
        pages: list[ParsedPage] = []
        all_tables: list[list[list[str]]] = []

        try:
            # 上下文管理器确保 PDF 文件句柄释放
            with pdfplumber.open(file_path) as pdf:
                for idx, page in enumerate(pdf.pages, start=1):
                    # 提取当前页纯文本（无文本时返回 None，统一转为空串）
                    text = page.extract_text() or ""
                    # 提取当前页全部表格并规范化（None 单元格 -> ""）
                    page_tables = [
                        self._normalize_table(t) for t in page.extract_tables()
                    ]
                    pages.append(
                        ParsedPage(
                            page_number=idx, text=text, tables=page_tables
                        )
                    )
                    all_tables.extend(page_tables)
        except (
            OSError,
            PdfminerException,
            PDFSyntaxError,
            PDFPasswordIncorrect,
            ValueError,
        ) as e:
            # PdfminerException: pdfplumber 包装的解析异常（非法/加密 PDF 等）；
            # PDFSyntaxError/PDFPasswordIncorrect: 页内提取时可能直接抛出；
            # OSError: 读取/IO 失败；ValueError: 其他格式/解码问题
            raise ParserError(f"PDF 解析失败 [{filename}]: {e}") from e

        return ParsedDocument(
            filename=filename,
            file_type="pdf",
            pages=pages,
            tables=all_tables,
            metadata={"page_count": len(pages)},
        )

    @staticmethod
    def _normalize_table(table: list[list]) -> list[list[str]]:
        """将 pdfplumber 表格中的 None 单元格替换为空字符串。"""
        return [[(cell if cell is not None else "") for cell in row] for row in table]
