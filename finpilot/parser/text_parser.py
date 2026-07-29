"""纯文本文档解析器：支持 .txt / .md / .text / .log 等无结构文本文件。

整个文件作为一页纯文本，不抽取表格。多编码自动探测以兼容
Windows（gbk/gb18030）与 Unix（utf-8）导出场景。
"""
from __future__ import annotations

from .base import BaseParser, ParsedDocument, ParsedPage, ParserError

# 常见中文文本编码，按优先级尝试
_CANDIDATE_ENCODINGS = ("utf-8", "utf-8-sig", "gbk", "gb18030", "latin-1")


class TextParser(BaseParser):
    """解析纯文本文件，整篇作为一个 ParsedPage。"""

    def parse(self, file_path: str) -> ParsedDocument:
        filename = self._check_file(file_path)

        last_err: Exception | None = None
        text: str | None = None
        for enc in _CANDIDATE_ENCODINGS:
            try:
                with open(file_path, "r", encoding=enc) as fp:
                    text = fp.read()
                break
            except (OSError, UnicodeDecodeError) as e:
                last_err = e
                continue
        if text is None:
            raise ParserError(f"文本解析失败 [{filename}]: {last_err}") from last_err

        page = ParsedPage(page_number=1, text=text, tables=[])

        return ParsedDocument(
            filename=filename,
            file_type="txt",
            pages=[page],
            tables=[],
            metadata={"char_count": len(text), "line_count": text.count("\n") + 1},
        )
