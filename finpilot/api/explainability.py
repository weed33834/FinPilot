# -*- coding: utf-8 -*-
"""可解释 AI 路由 — 决策归因与审计 API 入口。

POST /api/v1/explainability/explain  对 Agent 决策做归因 + 证据追溯 + LLM 自解释
GET  /api/v1/explainability/methods  返回支持的归因方法
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from finpilot.api.deps import get_current_user, get_db_session

router = APIRouter(prefix="/explainability", tags=["Explainability"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ExplainRequest(BaseModel):
    """解释请求。"""

    question: str = Field(..., description="用户原始问题")
    answer: str = Field(..., description="Agent 最终答案")
    steps: list[dict[str, Any]] | None = Field(
        default=None, description="ReAct 草稿本（含 thought/action/observation）"
    )
    features: dict[str, float] | None = Field(
        default=None,
        description="因子值字典（如 {revenue_growth: 0.15, gross_margin: 0.35}），用于 SHAP-lite 归因",
    )
    feature_weights: dict[str, float] | None = Field(
        default=None, description="因子权重字典（用于 SHAP-lite 归因）"
    )
    confidence: float = Field(default=0.0, description="模型置信度（0-1）")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/explain")
def explain_endpoint(
    body: ExplainRequest,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db_session),
) -> dict[str, Any]:
    """对 Agent 决策做可解释性归因，返回 ExplainabilityReport。"""
    from finpilot.agent.explainability import explain_decision

    try:
        report = explain_decision(
            body.question,
            body.answer,
            body.steps or [],
            features=body.features,
            feature_weights=body.feature_weights,
            confidence=body.confidence,
            db=db,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "code": 1,
            "message": f"解释失败({type(exc).__name__}): {exc}",
            "data": None,
        }
    return {"code": 0, "message": "ok", "data": report.to_dict()}


@router.get("/methods")
def list_methods(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """返回支持的归因方法。"""
    methods = [
        {
            "id": "shap_lite",
            "name": "SHAP-lite 因子归因",
            "description": (
                "基于线性权重的 Shapley 值加权近似：contribution = w_i * (x_i - mean)。"
                "适用于线性模型 / 因子加权打分场景，无需训练 shap 库。"
            ),
            "inputs": ["features", "feature_weights (可选)"],
        },
        {
            "id": "decision_trace",
            "name": "决策追溯",
            "description": (
                "从草稿本 Observation 中抽取数字，匹配 final_answer 中的数字，"
                "标记 cited_in_final。用于审计答案是否可追溯到工具结果。"
            ),
            "inputs": ["steps (草稿本)"],
        },
        {
            "id": "llm_self",
            "name": "LLM 自解释",
            "description": (
                "调用 LLM 让其用自己的话解释为什么给出这个答案，作为兜底/补充。"
                "不需要工具结果也可生成。"
            ),
            "inputs": ["question", "answer"],
        },
    ]
    return {"code": 0, "message": "ok", "data": methods}
