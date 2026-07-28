"""财务计算通用工具函数.

集中放置跨服务重复实现的辅助函数,消除 _safe_div / _safe_float / 统计函数
在 financial_ratios / valuation_service / backtesting / factor_mining
等模块中的重复定义。
"""
from __future__ import annotations

import math
import statistics
from typing import Optional

import numpy as np


def safe_div(
    numerator: float | None,
    denominator: float | None,
    round_to: int | None = None,
) -> float | None:
    """安全除法：任一参数为 None 或分母为 0 时返回 None.

    Args:
        numerator: 分子
        denominator: 分母
        round_to: 若指定则保留小数位数
    """
    if numerator is None or denominator is None or denominator == 0:
        return None
    result = numerator / denominator
    return round(result, round_to) if round_to is not None else result


def safe_pct(
    numerator: float | None,
    denominator: float | None,
    round_to: int = 2,
) -> float | None:
    """安全百分比：safe_div(a, b) * 100."""
    val = safe_div(numerator, denominator)
    if val is not None:
        return round(val * 100, round_to)
    return None


def safe_float(value, default: float | None = None) -> float | None:
    """安全浮点转换：None / 空字符串 / 非数字返回 default."""
    if value is None:
        return default
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def safe_int(value, default: int | None = None) -> int | None:
    """安全整数转换."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ── 统计函数（统一使用 numpy / statistics 标准库） ──────────────


def median(values: list[float]) -> float | None:
    """中位数 — 使用 numpy 实现,空列表返回 None."""
    if not values:
        return None
    return float(np.median(values))


def mean(values: list[float]) -> float | None:
    """平均值 — 使用 statistics 标准库."""
    if not values:
        return None
    return statistics.mean(values)


def std_dev(values: list[float], ddof: int = 0) -> float | None:
    """标准差 — 使用 numpy 实现.

    Args:
        ddof: 自由度修正,0=总体标准差,1=样本标准差
    """
    if not values:
        return None
    return float(np.std(values, ddof=ddof))


def percentile(values: list[float], pct: float) -> float | None:
    """百分位数 — 使用 numpy 实现.

    Args:
        values: 数值列表(无需预排序)
        pct: 百分位(0-100)
    """
    if not values:
        return None
    return float(np.percentile(values, pct))


def normal_random(
    mean_val: float = 0.0,
    std_val: float = 1.0,
    size: int = 1,
) -> np.ndarray:
    """正态分布随机数 — 使用 numpy 替代 random.gauss,性能更好."""
    return np.random.normal(mean_val, std_val, size)
