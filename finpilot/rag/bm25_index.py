"""BM25 检索模块 - 基于词频的稀疏检索。

- 使用 rank_bm25.BM25Okapi（k1=1.5, b=0.75，经典经验值）。
- CJK 按字切分：中文无需空格分词，逐字作为 token；
  英文/数字按连续单词切分，兼顾中英混排的财务文本。
"""
from __future__ import annotations

import re

from rank_bm25 import BM25Okapi

# 匹配连续英文/数字/下划线单词，或单个 CJK 汉字
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


def cjk_tokenize(text: str) -> list[str]:
    """中英混合分词：CJK 按字切分，英文按词切分，统一小写化"""
    return [tok.lower() for tok in _TOKEN_PATTERN.findall(text)]


class BM25Index:
    """内存 BM25 索引，惰性重建，支持 CJK 按字切分"""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        # doc_id 列表与分词语料按索引对齐
        self.doc_ids: list[str] = []
        self.corpus: list[list[str]] = []
        self.bm25: BM25Okapi | None = None  # 标记是否需重建

    def add(self, doc_id: str, text: str) -> None:
        """添加单篇文档；标记索引为脏，查询前惰性重建"""
        self.doc_ids.append(doc_id)
        self.corpus.append(cjk_tokenize(text))
        self.bm25 = None

    def _ensure_built(self) -> None:
        """惰性重建 BM25 实例，避免每次 add 都重建"""
        if self.bm25 is None and self.corpus:
            self.bm25 = BM25Okapi(self.corpus, k1=self.k1, b=self.b)

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        """检索 top_k 文档，返回 (doc_id, score) 列表，按分数降序"""
        self._ensure_built()
        if self.bm25 is None:
            return []
        scores = self.bm25.get_scores(cjk_tokenize(query))
        # 按分数降序取 top_k，过滤零分（无词项命中）文档
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return [(self.doc_ids[i], float(s)) for i, s in ranked[:top_k] if s > 0]

    def clear(self) -> None:
        """清空索引"""
        self.doc_ids.clear()
        self.corpus.clear()
        self.bm25 = None
