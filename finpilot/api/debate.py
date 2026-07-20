# -*- coding: utf-8 -*-
"""多智能体对抗辩论路由 — 投研决策 API 入口。

POST /api/v1/debate/run  运行 N 轮 Bull/Bear 对抗辩论，返回结构化决策
GET  /api/v1/debate/info 返回辩论引擎说明
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from finpilot.api.deps import get_current_user, get_db_session

router = APIRouter(prefix="/debate", tags=["Debate"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class DebateRequest(BaseModel):
    """辩论请求。"""

    question: str = Field(..., description="投研问题（如：分析贵州茅台 2024 年投资价值）")
    max_rounds: int | None = Field(
        default=None,
        description="辩论轮数，默认取环境变量 FINPILOT_DEBATE_MAX_ROUNDS（3）",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/run")
def run_debate_endpoint(
    body: DebateRequest,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db_session),
) -> dict[str, Any]:
    """运行多智能体对抗辩论（4 角色 N 轮），返回 DebateResult。"""
    from finpilot.agent.debate import run_debate

    try:
        result = run_debate(
            body.question, db=db, max_rounds=body.max_rounds
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "code": 1,
            "message": f"辩论执行失败({type(exc).__name__}): {exc}",
            "data": None,
        }
    return {"code": 0, "message": "ok", "data": result.to_dict()}


@router.get("/info")
def debate_info(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """返回辩论引擎说明（角色 + 流程 + 默认轮数）。"""
    import os

    info = {
        "name": "FinPilot Adversarial Debate Engine",
        "architecture": "START → research → bull ⇄ bear × N → risk → pm → END",
        "roles": [
            {"name": "Research Analyst", "duty": "抽取公司基本面/财务指标/估值/行业/事件"},
            {"name": "Bull", "duty": "提出看多论点，反驳 Bear"},
            {"name": "Bear", "duty": "提出看空论点，反驳 Bull"},
            {"name": "Risk", "duty": "5 维风险评估（财务/估值/经营/治理/宏观）"},
            {"name": "PM", "duty": "综合决策（买/持/卖 + 仓位 + 止损）+ 置信度 + 证据链"},
        ],
        "default_rounds": int(os.getenv("FINPILOT_DEBATE_MAX_ROUNDS", "3")),
        "inspiration": "TradingAgents (AAAI 2025) — 多空对抗辩论 + Reflector 记忆",
    }
    return {"code": 0, "message": "ok", "data": info}
