"""Excel 文档解析器：基于 pandas（openpyxl/xlrd 引擎）解析 .xlsx/.xls。

每个 sheet 视为一页（ParsedPage），提取表格数据为 list[list[str]]。
"""
from __future__ import annotations

import os
import zipfile

import pandas as pd
from openpyxl.utils.exceptions import InvalidFileException
from xlrd.biffh import XLRDError

from .base import BaseParser, ParsedDocument, ParsedPage, ParserError


class ExcelParser(BaseParser):
    """解析 Excel 文件，每个 sheet 作为一个 ParsedPage。"""

    def parse(self, file_path: str) -> ParsedDocument:
        filename = self._check_file(file_path)
        ext = os.path.splitext(file_path)[1].lower().lstrip(".")
        file_type = "xlsx" if ext == "xlsx" else "xls"

        try:
            # sheet_name=None 一次性读取全部 sheet，返回 {sheet名: DataFrame}
            # dtype=str 保持原始文本，避免数字/日期被自动转换
            sheets = pd.read_excel(file_path, sheet_name=None, dtype=str)
        except (
            OSError,
            InvalidFileException,
            XLRDError,
            zipfile.BadZipFile,
            ValueError,
        ) as e:
            # InvalidFileException/BadZipFile: 非 Excel 或文件损坏；
            # XLRDError: 旧版 .xls 解析失败；ValueError: 其他格式/解码问题
            raise ParserError(f"Excel 解析失败 [{filename}]: {e}") from e

        pages: list[ParsedPage] = []
        all_tables: list[list[list[str]]] = []
        sheet_names: list[str] = []

        for idx, (sheet_name, df) in enumerate(sheets.items(), start=1):
            sheet_names.append(sheet_name)
            # 空单元格统一替换为空字符串，避免出现 "nan"
            df = df.fillna("")
            table = self._df_to_table(df)
            pages.append(
                ParsedPage(
                    page_number=idx,
                    text=df.to_string(index=False),
                    tables=[table] if table else [],
                )
            )
            if table:
                all_tables.append(table)

        return ParsedDocument(
            filename=filename,
            file_type=file_type,
            pages=pages,
            tables=all_tables,
            metadata={
                "sheet_names": sheet_names,
                "sheet_count": len(sheet_names),
            },
        )

    @staticmethod
    def _df_to_table(df: pd.DataFrame) -> list[list[str]]:
        """DataFrame 转二维字符串列表，首行为列名。"""
        # 无数据行时视为空表
        if df.shape[0] == 0:
            return []
        rows: list[list[str]] = [df.columns.astype(str).tolist()]
        for row in df.itertuples(index=False, name=None):
            rows.append([str(v) for v in row])
        return rows
