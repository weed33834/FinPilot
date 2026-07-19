"""
模型路由 - 按问题复杂度将请求路由到不同性能层级的模型
规则优先级：意图 > 关键词 > 问题长度
层级降级链：high -> medium -> low
"""
from dataclasses import dataclass, field
from typing import Optional

# 各层级的降级顺序
_TIER_FALLBACK = {
    "high": ["medium", "low"],
    "medium": ["low"],
    "low": [],
}


@dataclass
class RouteDecision:
    """路由决策结果"""
    tier: str                                     # 目标层级 low/medium/high
    model_name: Optional[str] = None              # 具体模型名（路由阶段可不指定）
    fallback_tiers: list[str] = field(default_factory=list)  # 降级层级列表


class ModelRouter:
    """规则路由器：依据意图、关键词与问题长度判定目标模型层级"""

    # 高复杂度关键词 -> high
    HIGH_KEYWORDS = ("分析", "对比", "预测", "估值", "报告")
    # 低复杂度关键词 -> low
    LOW_KEYWORDS = ("查", "查一下", "是多少", "多少", "是什么")

    def route(
        self,
        question: str,
        intent: Optional[str] = None,
        context: Optional[str] = None,
    ) -> RouteDecision:
        """
        路由主入口
        优先级：意图(create_report) > 关键词 > 问题长度
        """
        # 1. 意图直接决定高层级需求
        if intent == "create_report":
            return self._decision("high")

        # 2. 关键词检测（语义信号强于长度，优先判定）
        for kw in self.HIGH_KEYWORDS:
            if kw in question:
                return self._decision("high")
        for kw in self.LOW_KEYWORDS:
            if kw in question:
                return self._decision("low")

        # 3. 按问题长度分级兜底
        length = len(question)
        if length < 200:
            return self._decision("low")
        elif length <= 800:
            return self._decision("medium")
        else:
            return self._decision("high")

    @staticmethod
    def _decision(tier: str) -> RouteDecision:
        """构造路由决策，附带降级链"""
        return RouteDecision(
            tier=tier,
            fallback_tiers=list(_TIER_FALLBACK.get(tier, [])),
        )


# ---------- 单例管理 ----------
_router_instance: Optional[ModelRouter] = None


def get_router() -> ModelRouter:
    """获取路由器单例"""
    global _router_instance
    if _router_instance is None:
        _router_instance = ModelRouter()
    return _router_instance


def reset_router() -> None:
    """重置路由器单例（测试或配置变更时使用）"""
    global _router_instance
    _router_instance = None
