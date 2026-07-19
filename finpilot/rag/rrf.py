"""RRF（Reciprocal Rank Fusion）融合算法。

将多路检索的排序结果融合为单一排序，无需归一化分数即可合并
向量检索（稠密）与 BM25 检索（稀疏）的异质打分。

公式：score(d) = Σ 1 / (k + rank_i(d))，rank 从 1 开始。
k 为平滑常数（默认 60），削弱头部排名的过大权重。
"""
from __future__ import annotations

from collections import defaultdict


def rrf_fuse(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """对多路排序结果做 RRF 融合。

    Args:
        rankings: 多路检索的 doc_id 排序列表（每路按相关性从高到低）。
        k: 平滑常数，rank 越靠后贡献越小，k 越大融合越平滑。

    Returns:
        融合后的 (doc_id, score) 列表，按融合分数降序。
    """
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        # rank 从 1 开始计，符合 RRF 原始论文定义
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] += 1.0 / (k + rank)
    # 按融合分数降序输出
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
