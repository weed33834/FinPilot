"""FinPilot RAG 知识库服务模块 - 检索增强生成层。

第一版采用内存向量库（不依赖 PGVector），支持向量 + BM25 混合检索，
通过 RRF 融合两路排序结果，并由 LLM 生成带引用的答案。

用法:
    from finpilot.rag import RagService, chunk_text

    svc = RagService()
    svc.index_document(1, "文档全文...")
    result = svc.query("营业收入是多少？")
"""
from .chunker import chunk_text
from .service import RagService

__all__ = [
    "RagService",
    "chunk_text",
]
