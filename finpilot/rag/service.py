"""RAG 主服务 - 文档索引 + 混合检索 + LLM 生成。

检索流程：
    embed(question) → 查询改写多路扩展 → [向量召回 ‖ BM25召回] → RRF融合(k=60) → top_k → LLM生成(带[n]引用)

降级策略：
- LLM 不可用时，query 仅返回检索到的 chunks，answer 为空串。
- embedding 失败自动降级伪向量（见 embedding.py），检索链路不中断。
- 查询改写失败时仅用原问题检索。
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from finpilot.database.models import DocumentChunk
from finpilot.llm.client import LLMClient, LLMUnavailableError
from finpilot.llm.config import get_default_config

from .bm25_index import BM25Index
from .chunker import chunk_text
from .embedding import embed, embed_batch
from .rrf import rrf_fuse
from .vector_store import VectorStore

logger = logging.getLogger(__name__)

# 最终返回的片段数
TOP_K = 5
# RRF 融合平滑常数
RRF_K = 60
# 单路召回放大倍数：为 tenant/document 过滤预留余量
_RECALL_FACTOR = 4
# 短/长查询分界（字符数）：<= 阈值走 MultiQuery，否则走 HyDE
_SHORT_QUERY_THRESHOLD = 12


class RagService:
    """RAG 主服务：索引 + 混合检索 + 生成"""

    def __init__(self, db: Optional[Session] = None) -> None:
        self.db = db
        self.vector_store = VectorStore()
        self.bm25_index = BM25Index()
        # chunk_key -> {document_id, chunk_index, text, tenant_id}
        self.registry: dict[str, dict] = {}

    # ---------------- 索引 ----------------

    def index_document(
        self, document_id: int, text: str, tenant_id: str = "default"
    ) -> int:
        """切分 + embed + 写入 DB 与内存索引，返回分块数"""
        chunks = chunk_text(text)
        if not chunks:
            return 0
        # 批量向量化（内部统一降级策略）
        embeddings = embed_batch(chunks, self.db)

        for idx, (chunk, emb_vec) in enumerate(zip(chunks, embeddings)):
            chunk_key = f"{document_id}:{idx}"
            # 写内存索引：向量库 + BM25 + 元信息登记
            self.vector_store.add(chunk_key, chunk, emb_vec, document_id=document_id)
            self.bm25_index.add(chunk_key, chunk)
            self.registry[chunk_key] = {
                "document_id": document_id,
                "chunk_index": idx,
                "text": chunk,
                "tenant_id": tenant_id,
            }
            # 写 DB：embedding 序列化为 JSON 字符串（与 DocumentChunk.embedding 字段约定一致）
            if self.db is not None:
                self.db.add(
                    DocumentChunk(
                        document_id=document_id,
                        chunk_index=idx,
                        content=chunk,
                        embedding=json.dumps(emb_vec, ensure_ascii=False),
                        tenant_id=tenant_id,
                    )
                )
        if self.db is not None:
            self.db.commit()
        return len(chunks)

    # ---------------- 检索 + 生成 ----------------

    def query(
        self,
        question: str,
        tenant_id: str = "default",
        document_id: Optional[int] = None,
    ) -> dict:
        """混合检索 + LLM 生成。

        Returns:
            {"answer": str, "chunks": list[dict], "document_id": int|None}
            chunks 每项含 {"text", "score", "document_id", "chunk_index"}
        """
        # 1. 查询改写（多查询扩展），失败则只用原问题
        expanded = self.rewrite_query(question)
        all_queries = [question] + expanded

        # 2. 多路召回：每条查询都做 向量 ‖ BM25
        #    召回数放大，为后续 tenant/document 过滤预留余量
        recall_n = TOP_K * _RECALL_FACTOR
        vector_rankings: list[list[str]] = []
        bm25_rankings: list[list[str]] = []
        for q in all_queries:
            q_emb = embed(q, self.db)
            v_hits = self.vector_store.search(
                q_emb, top_k=recall_n, document_id=document_id
            )
            b_hits = self.bm25_index.search(q, top_k=recall_n)
            vector_rankings.append([doc_id for doc_id, _ in v_hits])
            bm25_rankings.append([doc_id for doc_id, _ in b_hits])

        # 3. RRF 融合：向量多路先融合，BM25 多路先融合，再两路最终融合
        fused_vector = rrf_fuse(vector_rankings, k=RRF_K)
        fused_bm25 = rrf_fuse(bm25_rankings, k=RRF_K)
        final_fused = rrf_fuse(
            [
                [doc_id for doc_id, _ in fused_vector],
                [doc_id for doc_id, _ in fused_bm25],
            ],
            k=RRF_K,
        )

        # 4. 取 top_k：按 tenant 与 document 过滤后构造片段
        score_map = dict(final_fused)
        chunks: list[dict] = []
        for chunk_key, _ in final_fused:
            meta = self.registry.get(chunk_key)
            if meta is None:
                continue
            if meta["tenant_id"] != tenant_id:
                continue
            # BM25 未做 document 过滤，此处统一对齐（向量路已过滤，重复判断无副作用）
            if document_id is not None and meta["document_id"] != document_id:
                continue
            chunks.append(
                {
                    "text": meta["text"],
                    "score": score_map.get(chunk_key, 0.0),
                    "document_id": meta["document_id"],
                    "chunk_index": meta["chunk_index"],
                }
            )
            if len(chunks) >= TOP_K:
                break

        # 5. LLM 生成答案（带 [n] 引用）；不可用时返回空串
        answer = self._generate_answer(question, chunks)

        return {
            "answer": answer,
            "chunks": chunks,
            "document_id": document_id,
        }

    def _generate_answer(self, question: str, chunks: list[dict]) -> str:
        """基于检索片段生成带 [n] 引用的答案；LLM 不可用时返回空串"""
        if not chunks:
            return ""
        config = get_default_config(self.db) if self.db is not None else None
        if config is None:
            return ""
        # 构造带编号的上下文，编号与 chunks 顺序对应，供答案 [n] 引用
        context = "\n\n".join(f"[{i + 1}] {c['text']}" for i, c in enumerate(chunks))
        system_prompt = (
            "你是企业财务分析助手。根据以下检索到的资料片段回答用户问题。"
            "回答时在引用处标注 [n]（n 为片段编号）。若资料不足以回答，请说明。"
        )
        user_prompt = f"检索资料：\n{context}\n\n用户问题：{question}"
        try:
            client = LLMClient(config)
            return client.chat(system_prompt, user_prompt)
        except LLMUnavailableError as exc:
            logger.warning("LLM 生成答案失败，仅返回检索结果: %s", exc)
            return ""

    # ---------------- 查询改写 ----------------

    def rewrite_query(self, question: str) -> list[str]:
        """查询改写：短查询 MultiQuery 扩展，长查询 HyDE 假设文档。

        - 短查询（<= 阈值字符）：扩展为 3 个语义相近的查询，提升召回。
        - 长查询：生成假设性答案文档作为查询，使向量更贴近目标文档。
        LLM 不可用时返回空列表（仅用原问题检索）。
        """
        config = get_default_config(self.db) if self.db is not None else None
        if config is None:
            return []
        try:
            client = LLMClient(config)
            if len(question) <= _SHORT_QUERY_THRESHOLD:
                # MultiQuery 扩展：改写为 3 个等价查询
                prompt = (
                    "请将下面的查询改写为 3 个语义相近但表述不同的查询，"
                    "用于提升检索召回率。每行一个，不要编号，不要解释。\n"
                    f"查询：{question}"
                )
                resp = client.chat("你是查询改写助手。", prompt)
                return [
                    line.strip()
                    for line in resp.strip().splitlines()
                    if line.strip()
                ][:3]
            # HyDE 假设文档：生成可能含答案的段落作为查询
            prompt = (
                "请针对下面的查询，撰写一段可能包含答案的假设性文档段落"
                "（中文，100字以内），用于辅助检索。直接输出段落，不要解释。\n"
                f"查询：{question}"
            )
            resp = client.chat("你是假设文档生成助手。", prompt)
            return [resp.strip()] if resp.strip() else []
        except LLMUnavailableError as exc:
            logger.warning("查询改写失败，跳过扩展: %s", exc)
            return []

    # ---------------- 维护 ----------------

    def clear(self) -> None:
        """清空内存索引（不影响已写入 DB 的数据）"""
        self.vector_store.clear()
        self.bm25_index.clear()
        self.registry.clear()
