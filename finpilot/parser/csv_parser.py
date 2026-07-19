"""CSV 文档解析器：基于 pandas 读取，整个文件作为一页。

支持多编码自动探测（utf-8 / utf-8-sig / gbk / gb18030）以兼容
真实场景下从不同业务系统导出的零散数据；分隔符自动识别。
"""
from __future__ import annotations

import pandas as pd

from .base import BaseParser, ParsedDocument, ParsedPage, ParserError

# 常见中文 CSV 编码，按优先级尝试
_CANDIDATE_ENCODINGS = ("utf-8", "utf-8-sig", "gbk", "gb18030", "latin-1")


class CsvParser(BaseParser):
    """解析 CSV 文件，整篇作为一个 ParsedPage。"""

    def parse(self, file_path: str) -> ParsedDocument:
        filename = self._check_file(file_path)

        last_err: Exception | None = None
        df: pd.DataFrame | None = None
        for enc in _CANDIDATE_ENCODINGS:
            try:
                # dtype=str 保留原始文本；sep=None 让 pandas 自动嗅探分隔符
                # （兼容逗号 / 分号 / 制表符等欧式格式）
                df = pd.read_csv(file_path, dtype=str, encoding=enc, sep=None, engine="python")
                break
            except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError, ValueError) as e:
                last_err = e
                continue
        if df is None:
            raise ParserError(f"CSV 解析失败 [{filename}]: {last_err}") from last_err

        df = df.fillna("")
        table = self._df_to_table(df)

        page = ParsedPage(
            page_number=1,
            text=df.to_string(index=False),
            tables=[table] if table else [],
        )

        return ParsedDocument(
            filename=filename,
            file_type="csv",
            pages=[page],
            tables=[table] if table else [],
            metadata={"row_count": df.shape[0], "column_count": df.shape[1]},
        )

    @staticmethod
    def _df_to_table(df: pd.DataFrame) -> list[list[str]]:
        """DataFrame 转二维字符串列表，首行为列名。"""
        if df.shape[0] == 0:
            return []
        rows: list[list[str]] = [df.columns.astype(str).tolist()]
        for row in df.itertuples(index=False, name=None):
            rows.append([str(v) for v in row])
        return rows
