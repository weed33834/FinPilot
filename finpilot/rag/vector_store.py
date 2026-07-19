"""内存向量库 - 基于 numpy 的稠密向量检索。

- 余弦相似度检索，向量化批量计算，避免逐条点积。
- 支持 document_id 过滤：限定单文档范围内检索（精细问答场景）。
- 第一版纯内存，不依赖 PGVector；进程重启后需重新索引。
"""
from __future__ import annotations

from typing import Optional

import numpy as np

# 防零除小量
_EPS = 1e-10


class VectorStore:
    """内存向量库：doc_id -> 文本/向量/元信息"""

    def __init__(self) -> None:
        # doc_id -> {"text", "embedding"(np.ndarray), "document_id"}
        self.docs: dict[str, dict] = {}

    def add(
        self,
        doc_id: str,
        text: str,
        embedding: list[float],
        document_id: Optional[int] = None,
    ) -> None:
        """添加一条向量文档，附带 document_id 元信息用于过滤"""
        self.docs[doc_id] = {
            "text": text,
            "embedding": np.asarray(embedding, dtype=np.float32),
            "document_id": document_id,
        }

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        document_id: Optional[int] = None,
    ) -> list[tuple[str, float]]:
        """余弦相似度检索 top_k；document_id 非空时限定单文档范围"""
        if not self.docs:
            return []

        # 收集通过过滤的候选
        ids: list[str] = []
        mats: list[np.ndarray] = []
        for doc_id, doc in self.docs.items():
            if document_id is not None and doc["document_id"] != document_id:
                continue
            ids.append(doc_id)
            mats.append(doc["embedding"])
        if not ids:
            return []

        # 批量计算余弦相似度：先归一化再点积
        matrix = np.vstack(mats)  # (n, d)
        q = np.asarray(query_embedding, dtype=np.float32)
        q_norm = q / (np.linalg.norm(q) + _EPS)
        m_norm = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + _EPS)
        sims = m_norm @ q_norm  # (n,)

        # 按相似度降序取 top_k
        ranked = sorted(enumerate(sims), key=lambda x: x[1], reverse=True)[:top_k]
        return [(ids[i], float(s)) for i, s in ranked]

    def clear(self) -> None:
        """清空向量库"""
        self.docs.clear()
