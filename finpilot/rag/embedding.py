"""向量生成模块 - RAG 检索的向量化层。

优先级（逐级降级）：
1. Ollama 原生 /api/embeddings 接口（本地部署，零成本）。
2. OpenAI 兼容 embeddings API（云端，需 api_key）。
3. hash-based 伪向量（384 维，确定性，仅调试兜底）。

任何一级失败都自动降级，保证检索链路不中断。
"""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

import httpx
import numpy as np
import openai
from openai import OpenAI

from finpilot.llm.config import LLMConfig, get_default_config

logger = logging.getLogger(__name__)

# 伪向量维度（与 sentence-transformers mini 模型一致，便于调试替换）
_PSEUDO_DIM = 384
# 请求超时（秒）
_TIMEOUT = 30.0


def _ollama_root(base_url: Optional[str]) -> str:
    """从 LLMConfig.base_url（形如 http://localhost:11434/v1）还原 Ollama 根地址"""
    base = (base_url or "http://localhost:11434/v1").rstrip("/")
    # 去掉 OpenAI 兼容层 /v1 后缀，得到原生 API 根
    if base.endswith("/v1"):
        base = base[:-3]
    return base.rstrip("/")


def _ollama_embed(config: LLMConfig, text: str) -> list[float]:
    """调用 Ollama 原生 /api/embeddings 接口生成向量"""
    url = f"{_ollama_root(config.base_url)}/api/embeddings"
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.post(url, json={"model": config.model_name, "prompt": text})
        resp.raise_for_status()
        return list(resp.json()["embedding"])


def _openai_embed(config: LLMConfig, text: str) -> list[float]:
    """调用 OpenAI 兼容 embeddings 接口生成向量"""
    client = OpenAI(
        base_url=config.base_url,
        api_key=config.api_key or "not-required",
        timeout=_TIMEOUT,
    )
    # 配置中的 model_name 多为聊天模型，对 openai 供应商回退到默认 embedding 模型
    model = config.model_name
    if config.provider_type == "openai" and "embed" not in model.lower():
        model = "text-embedding-3-small"
    resp = client.embeddings.create(model=model, input=text)
    return list(resp.data[0].embedding)


def _pseudo_embed(text: str, dim: int = _PSEUDO_DIM) -> list[float]:
    """基于 hash 的伪向量（调试降级用）：确定性，相同文本得到相同向量。

    用 (字符, 位置) 的 md5 投影到固定维度并 L2 归一化，
    保留一定文本区分度以便验证检索链路。
    """
    vec = np.zeros(dim, dtype=np.float32)
    for i, ch in enumerate(text):
        h = int(hashlib.md5(f"{ch}:{i}".encode("utf-8")).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.tolist()


def _load_config(db) -> Optional[LLMConfig]:
    """安全加载默认 LLM 配置；DB 缺失或异常时返回 None"""
    if db is None:
        return None
    try:
        return get_default_config(db)
    except Exception as exc:  # 配置加载不应阻断向量化
        logger.warning("加载 LLM 配置失败，将降级伪向量: %s", exc)
        return None


def embed(text: str, db=None) -> list[float]:
    """生成单条文本向量：Ollama 优先 -> OpenAI 回退 -> 伪向量兜底"""
    config = _load_config(db)

    # 1. Ollama 优先（本地零成本）
    if config and config.provider_type == "ollama":
        try:
            return _ollama_embed(config, text)
        except Exception as exc:
            logger.warning("Ollama embedding 失败，尝试 OpenAI: %s", exc)

    # 2. OpenAI 回退（需 api_key）
    if config and config.api_key:
        try:
            return _openai_embed(config, text)
        except openai.OpenAIError as exc:
            logger.warning("OpenAI embedding 失败，降级伪向量: %s", exc)
        except Exception as exc:
            logger.warning("OpenAI embedding 异常，降级伪向量: %s", exc)

    # 3. 伪向量兜底
    return _pseudo_embed(text)


def embed_batch(texts: list[str], db=None) -> list[list[float]]:
    """批量生成向量：逐条调用 embed，保证降级策略与单条一致"""
    return [embed(t, db) for t in texts]
