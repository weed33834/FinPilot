# -*- coding: utf-8 -*-
"""数据异常校验路由 — 财务规则引擎 API 入口。

POST /api/v1/validation/validate  一站式校验（自动按入参调度 9 类 checker）
GET  /api/v1/validation/rules      列出全部校验规则与说明
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from finpilot.api.deps import get_current_user

router = APIRouter(prefix="/validation", tags=["Validation"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ValidateRequest(BaseModel):
    """校验请求：所有字段可选，只对提供的字段跑对应 checker。"""

    journal_lines: list[dict[str, Any]] | None = Field(
        default=None,
        description="试算平衡校验：借/贷分录列表，每条含 debit/credit/account 等",
    )
    division: dict[str, Any] | None = Field(
        default=None,
        description="除零校验：含 numerator/denominator/metric_name",
    )
    transactions: list[dict[str, Any]] | None = Field(
        default=None,
        description="时间穿越校验：交易列表，含 transaction_date 字段",
    )
    closing_date: str | None = Field(default=None, description="结账日（ISO 日期）")
    opening_date: str | None = Field(default=None, description="开账日（ISO 日期）")
    assets: list[dict[str, Any]] | None = Field(
        default=None, description="负数资产校验：含 cost/accumulated_depreciation"
    )
    receivables: list[dict[str, Any]] | None = Field(
        default=None, description="账龄校验：含 age_days/customer"
    )
    vouchers: list[dict[str, Any]] | None = Field(
        default=None, description="凭证号格式校验：含 voucher_no"
    )
    exchange_rates: dict[str, Any] | None = Field(
        default=None, description="汇率校验：{currency: rate}"
    )
    related_party_transactions: list[dict[str, Any]] | None = Field(
        default=None, description="关联交易披露校验：含 amount/counterparty"
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/validate")
def validate_endpoint(
    body: ValidateRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """对企业财务数据做 9 类异常校验，返回 ValidationReport。"""
    from datetime import date as _date

    from finpilot.validation import validate_financial_data

    # 解析 ISO 日期字符串为 date 对象
    kwargs: dict[str, Any] = body.model_dump(exclude_none=True)
    for k in ("closing_date", "opening_date"):
        v = kwargs.get(k)
        if isinstance(v, str):
            try:
                kwargs[k] = _date.fromisoformat(v)
            except ValueError:
                kwargs.pop(k, None)

    report = validate_financial_data(**kwargs)
    return {"code": 0, "message": "ok", "data": report.to_dict()}


@router.get("/rules")
def list_validation_rules(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """返回全部校验规则与说明（供前端规则文档展示）。"""
    rules = [
        {
            "rule_id": "TBE-001",
            "name": "试算平衡",
            "severity": "P0",
            "description": "全部借方分录合计 = 全部贷方分录合计（容差 0.01）",
            "field": "journal_lines",
        },
        {
            "rule_id": "DBZ-001",
            "name": "除零",
            "severity": "P0",
            "description": "财务比率分母为 0 时不得返回 inf，应返回 null 并提示",
            "field": "division",
        },
        {
            "rule_id": "TTL-001",
            "name": "时间穿越",
            "severity": "P0",
            "description": "交易日期不得早于开账日，不得晚于结账日",
            "field": "transactions",
        },
        {
            "rule_id": "NAV-001",
            "name": "负数资产",
            "severity": "P1",
            "description": "固定资产净值 = 原值 - 累计折旧 不得为负",
            "field": "assets",
        },
        {
            "rule_id": "PRC-001",
            "name": "精度损失",
            "severity": "P2",
            "description": "金额字段小数位不得超过 6 位",
            "field": "values",
        },
        {
            "rule_id": "FXR-001",
            "name": "汇率异常",
            "severity": "P1",
            "description": "汇率 <=0 / 偏离市场公允值 10% 以上即异常",
            "field": "exchange_rates",
        },
        {
            "rule_id": "AGE-001",
            "name": "账龄异常",
            "severity": "P1",
            "description": "应收账款账龄 > 365 天提示坏账风险",
            "field": "receivables",
        },
        {
            "rule_id": "VCH-001",
            "name": "凭证号格式",
            "severity": "P2",
            "description": "凭证号须符合 记-年-流水 / JZ-年-流水 等规范",
            "field": "vouchers",
        },
        {
            "rule_id": "RPT-001",
            "name": "关联交易披露",
            "severity": "P0",
            "description": "单笔关联交易 >= 1000 万元须单独披露",
            "field": "related_party_transactions",
        },
    ]
    return {"code": 0, "message": "ok", "data": rules}
