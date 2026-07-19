# TODO: requires external package `graphrag-lite` (知识图谱 RAG 引擎，pip install graphrag-lite)
# TODO: requires finpilot.llm.client.LLMClient —— 当前以环境变量配置 LLM；如需统一接入 FinPilot 的 LLMClient 可后续替换
"""知识图谱增强检索服务 — 基于 graphrag-lite.

在传统 RAG 之上增加实体-关系网络层，支持：
- 实体提取与关系构建
- 本地/全局/混合三种检索模式
- 与现有 RAG 服务协同工作（mix_search + naive_search）

配置说明（替代原 app.config.get_settings，FinPilot 无独立 config 模块，改用环境变量）:
- OLLAMA_HOST: Ollama 服务地址（优先使用）
- OPENAI_BASE_URL: OpenAI 兼容服务地址（OLLAMA_HOST 缺省时回退）
- AGENT_LLM_MODEL: 使用的模型名（默认 gpt-3.5-turbo）
- GRAPHRAG_STORAGE_PATH: 图谱存储路径（默认 ./graph_data）
"""

from __future__ import annotations

import logging
import os
from typing import Any

from graphrag_lite import GraphRAGLite

logger = logging.getLogger(__name__)

_graph_instance: GraphRAGLite | None = None


def _get_graph() -> GraphRAGLite:
    """获取 GraphRAG 单例."""
    global _graph_instance
    if _graph_instance is None:
        base_url = os.environ.get("OLLAMA_HOST") or os.environ.get("OPENAI_BASE_URL")
        model = os.environ.get("AGENT_LLM_MODEL", "gpt-3.5-turbo")
        storage_path = os.environ.get("GRAPHRAG_STORAGE_PATH", "./graph_data")
        _graph_instance = GraphRAGLite(
            storage_path=storage_path,
            base_url=base_url,
            model=model,
            enable_cache=True,
        )
    return _graph_instance


def insert_document(text: str, doc_id: str | None = None) -> None:
    """将文档插入知识图谱（提取实体 + 构建关系）."""
    graph = _get_graph()
    graph.insert(text, doc_id=doc_id)


def graph_search(query: str, mode: str = "mix", top_k: int = 10) -> dict[str, Any]:
    """知识图谱增强检索.

    Args:
        query: 查询问题
        mode: 检索模式 — local(实体→关系), global(关系→实体), mix(混合), naive(纯文本)
        top_k: 返回结果数

    Returns:
        检索结果字典，包含 answer 和 citations。
    """
    graph = _get_graph()
    if not graph.has_data():
        return {"answer": "", "citations": [], "warning": "知识图谱为空"}

    result = graph.query(query, mode=mode, top_k=top_k)
    return {"answer": str(result), "citations": [], "mode": mode}
