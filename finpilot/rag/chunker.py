"""文档分块模块 - RAG 检索的前置切分层。

策略：
- 中文友好：按换行符分段（不按英文句号），契合财务文档/中文语料结构。
- 段落聚合：短段落累积到接近 chunk_size 再成块，保留语义完整性。
- 超长段落硬切：按 chunk_size 滑窗切分，带 overlap 保证上下文连续。
"""
from __future__ import annotations


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """将长文本切分为 chunk 列表。

    Args:
        text: 原始文本。
        chunk_size: 单块最大字符数（按字符计，中文友好）。
        overlap: 硬切时的重叠字符数，用于保留上下文。

    Returns:
        切分后的文本块列表（去除空块）。
    """
    if not text or not text.strip():
        return []

    # 防御：overlap 大于等于 chunk_size 会死循环，强制收敛
    if overlap >= chunk_size:
        overlap = max(0, chunk_size // 5)

    # 按换行符分段（中文文本友好，不按英文句号切分）
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    chunks: list[str] = []
    current = ""  # 当前正在聚合的块

    for para in paragraphs:
        # 超长段落单独硬切，不参与聚合
        if len(para) > chunk_size:
            # 先把已聚合内容落盘，避免与硬切块混淆
            if current:
                chunks.append(current)
                current = ""
            # 滑窗硬切，带 overlap
            start = 0
            while start < len(para):
                end = min(start + chunk_size, len(para))
                chunks.append(para[start:end])
                if end >= len(para):
                    break
                start = end - overlap
            continue

        # 段落聚合：若加入该段后超长，则先落盘当前块再起新块
        if current and len(current) + 1 + len(para) > chunk_size:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n{para}" if current else para

    # 收尾：剩余聚合内容落盘
    if current:
        chunks.append(current)

    return chunks
