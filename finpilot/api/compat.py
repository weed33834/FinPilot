# -*- coding: utf-8 -*-
"""前端契约兼容路由层。

为什么需要这个文件：
- 前端 admin 页面（models.ts / agentConfigs.ts / searchEngines.ts / settings.ts / metrics.ts /
  contextManager.ts）使用的 URL 与 schema 是按更早一版后端写的；
- 现在后端只有 /llm-providers（provider+model 拆表），且没有 agent-configs / search-engines /
  settings / metrics / context 等模块；
- 直接 404 会让前端报“响应错误 / 网络错误”，且无法定位具体哪个端点出问题。

本文件提供两类兼容路由：
1. **适配器**：/model-configs 把 llm_providers + llm_models 拍平成前端期望的扁平 schema，
   并把写操作代理回 llm_providers CRUD；
2. **占位路由**：/agent-configs /search-engines /settings /metrics/* /context/* 返回空数据，
   让前端 admin 页能正常渲染“暂无数据”，而不是 404 崩溃。

所有占位路由统一返回 ``{code, message, data}`` 包装，与前端 ApiResponse<T> 契约一致。
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from finpilot.database.crud import decode_api_key, encode_api_key
from finpilot.database.models import LlmModel, LlmProvider
from finpilot.llm.config import invalidate_cache

from .deps import get_current_user, get_db_session, require_admin

# 模块级 router：在 finpilot/api/router.py 里 include 进 /api/v1
router = APIRouter(prefix="", tags=["compat"])


def _ok(data: Any, message: str = "success") -> dict:
    """统一 {code, message, data} 包装，与前端 DataResponse<T> 对齐"""
    return {"code": 0, "message": message, "data": data}


# ===========================================================================
# /model-configs —— 拍平 llm_providers + llm_models，对齐前端 ModelConfigItem schema
# ===========================================================================

class ModelConfigCreatePayload(BaseModel):
    """前端 createModelConfig 入参（扁平 schema）"""
    provider: str
    model_name: str
    display_name: Optional[str] = None
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    is_default: bool = False
    is_active: bool = True
    parameters: Optional[dict] = None


class ModelConfigUpdatePayload(BaseModel):
    """前端 updateModelConfig 入参（全部字段可选）"""
    provider: Optional[str] = None
    model_name: Optional[str] = None
    display_name: Optional[str] = None
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None
    parameters: Optional[dict] = None


def _flatten_model_config(p: LlmProvider, m: LlmModel) -> dict:
    """把 (provider, model) 拍平为前端期望的 ModelConfigItem 字段"""
    return {
        "id": f"{p.id}:{m.id}",  # 复合 ID：provider_id:model_id
        "tenant_id": "default",
        "provider": p.name,
        "provider_type": p.provider_type,
        "model_name": m.model_name,
        "display_name": m.display_name or m.model_name,
        "api_base": p.base_url,
        "has_api_key": bool(p.api_key),
        "is_default": p.is_default,
        "is_active": m.is_active and p.is_active,
        "tier": m.tier or "medium",
        "parameters": None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": None,
    }


model_configs_router = APIRouter(prefix="/model-configs", tags=["model-configs"])


@model_configs_router.get("")
def list_model_configs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    search: str = "",
    provider: str = "",
    is_active: str = "",
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """列出所有 model-configs（拍平 provider+model）。

    支持 search（在 provider/model_name/display_name 中模糊匹配）、provider 过滤、is_active 过滤。
    """
    query = (
        db.query(LlmProvider, LlmModel)
        .join(LlmModel, LlmModel.provider_id == LlmProvider.id)
    )
    if search:
        like = f"%{search}%"
        query = query.filter(
            (LlmProvider.name.ilike(like))
            | (LlmModel.model_name.ilike(like))
            | (LlmModel.display_name.ilike(like))
        )
    if provider:
        query = query.filter(LlmProvider.name == provider)
    if is_active in ("true", "1", "yes"):
        query = query.filter(LlmModel.is_active.is_(True), LlmProvider.is_active.is_(True))
    elif is_active in ("false", "0", "no"):
        query = query.filter(LlmModel.is_active.is_(False))

    total = query.count()
    rows = (
        query.order_by(LlmProvider.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return _ok({
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_flatten_model_config(p, m) for (p, m) in rows],
    })


@model_configs_router.post("")
def create_model_config(
    payload: ModelConfigCreatePayload,
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """创建 model-config —— 复用已有 provider 或新建 provider，并挂一个 model 到其下。"""
    # 同名 provider 复用
    p = db.query(LlmProvider).filter(LlmProvider.name == payload.provider).first()
    if p is None:
        if payload.is_default:
            db.query(LlmProvider).filter(LlmProvider.is_default.is_(True)).update(
                {LlmProvider.is_default: False}
            )
        p = LlmProvider(
            name=payload.provider,
            provider_type="openai",
            base_url=payload.api_base,
            api_key=encode_api_key(payload.api_key) if payload.api_key else None,
            is_default=payload.is_default,
            is_active=True,
        )
        db.add(p)
        db.flush()
    else:
        # 已存在 provider：补字段（仅当传入新值时）
        if payload.api_base:
            p.base_url = payload.api_base
        if payload.api_key:
            p.api_key = encode_api_key(payload.api_key)
        if payload.is_default and not p.is_default:
            db.query(LlmProvider).filter(LlmProvider.id != p.id, LlmProvider.is_default.is_(True)).update(
                {LlmProvider.is_default: False}
            )
            p.is_default = True

    m = LlmModel(
        provider_id=p.id,
        model_name=payload.model_name,
        display_name=payload.display_name or payload.model_name,
        tier="medium",
        is_active=payload.is_active,
    )
    db.add(m)
    db.commit()
    db.refresh(p)
    db.refresh(m)
    invalidate_cache()
    return _ok(_flatten_model_config(p, m), "模型已创建")


@model_configs_router.put("/{config_id}")
def update_model_config(
    config_id: str,
    payload: ModelConfigUpdatePayload,
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """更新 model-config —— config_id 格式为 ``provider_id:model_id``"""
    p_id, m_id = _split_config_id(config_id)
    p = db.get(LlmProvider, p_id)
    m = db.get(LlmModel, m_id) if p else None
    if not p or not m:
        raise HTTPException(status_code=404, detail=f"模型配置 {config_id} 不存在")

    if payload.provider is not None:
        p.name = payload.provider
    if payload.api_base is not None:
        p.base_url = payload.api_base
    if payload.api_key:
        p.api_key = encode_api_key(payload.api_key)
    if payload.is_default is not None and payload.is_default:
        db.query(LlmProvider).filter(LlmProvider.id != p.id, LlmProvider.is_default.is_(True)).update(
            {LlmProvider.is_default: False}
        )
        p.is_default = True
    if payload.model_name is not None:
        m.model_name = payload.model_name
    if payload.display_name is not None:
        m.display_name = payload.display_name
    if payload.is_active is not None:
        m.is_active = payload.is_active
    db.commit()
    db.refresh(p)
    db.refresh(m)
    invalidate_cache()
    return _ok(_flatten_model_config(p, m), "模型已更新")


@model_configs_router.delete("/{config_id}")
def delete_model_config(
    config_id: str,
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """删除 model-config —— 只删 model 不删 provider（避免误删其他配置）"""
    p_id, m_id = _split_config_id(config_id)
    m = db.get(LlmModel, m_id)
    if not m:
        return _ok({"id": config_id, "deleted": False}, "模型不存在")
    db.delete(m)
    db.commit()
    invalidate_cache()
    return _ok({"id": config_id, "deleted": True}, "已删除")


@model_configs_router.patch("/{config_id}/toggle")
def toggle_model_config(
    config_id: str,
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """切换 model-config 启用/禁用"""
    p_id, m_id = _split_config_id(config_id)
    m = db.get(LlmModel, m_id)
    if not m:
        raise HTTPException(status_code=404, detail=f"模型配置 {config_id} 不存在")
    m.is_active = not m.is_active
    db.commit()
    db.refresh(m)
    p = db.get(LlmProvider, m.provider_id)
    return _ok(_flatten_model_config(p, m), "已切换")


@model_configs_router.post("/{config_id}/test")
def test_model_config(
    config_id: str,
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """测试 model-config 连通性 —— 调用 LLMClient.verify_connection"""
    from finpilot.llm.client import LLMClient, LLMUnavailableError
    from finpilot.llm.config import LLMConfig

    p_id, m_id = _split_config_id(config_id)
    p = db.get(LlmProvider, p_id)
    m = db.get(LlmModel, m_id) if p else None
    if not p or not m:
        raise HTTPException(status_code=404, detail=f"模型配置 {config_id} 不存在")

    api_key = decode_api_key(p.api_key) if p.api_key else None
    config = LLMConfig(
        provider_type=p.provider_type,
        base_url=p.base_url,
        api_key=api_key,
        model_name=m.model_name,
        tier=m.tier or "medium",
    )
    start = time.perf_counter()
    try:
        client = LLMClient(config)
        client.verify_connection(max_tokens=8)
        latency_ms = int((time.perf_counter() - start) * 1000)
        return _ok({
            "success": True,
            "message": f"连通成功（{latency_ms}ms）",
            "result": f"model={m.model_name} latency={latency_ms}ms",
        })
    except LLMUnavailableError as exc:
        return _ok({
            "success": False,
            "message": f"连通失败：{exc}",
            "result": None,
        })
    except Exception as exc:  # noqa: BLE001
        return _ok({
            "success": False,
            "message": f"未知异常：{type(exc).__name__}: {exc}",
            "result": None,
        })


@model_configs_router.post("/{config_id}/set-default")
def set_default_model_config(
    config_id: str,
    db: Session = Depends(get_db_session),
    _: dict = Depends(require_admin),
):
    """设为默认 model-config —— 把对应 provider 标为默认"""
    p_id, m_id = _split_config_id(config_id)
    p = db.get(LlmProvider, p_id)
    if not p:
        raise HTTPException(status_code=404, detail=f"模型配置 {config_id} 不存在")
    db.query(LlmProvider).filter(LlmProvider.id != p.id, LlmProvider.is_default.is_(True)).update(
        {LlmProvider.is_default: False}
    )
    p.is_default = True
    db.commit()
    db.refresh(p)
    m = db.get(LlmModel, m_id)
    invalidate_cache()
    return _ok(_flatten_model_config(p, m), "已设为默认")


def _split_config_id(config_id: str) -> tuple[int, int]:
    """把 ``provider_id:model_id`` 拆为 (int, int)；非法格式抛 400 让前端看见具体原因"""
    try:
        p_str, m_str = config_id.split(":", 1)
        return int(p_str), int(m_str)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"非法的模型配置 ID：{config_id}（应为 provider_id:model_id）",
        )


# ===========================================================================
# /agent-configs —— 占位（前端有完整 admin 页，但后端尚未实现 CRUD）
# ===========================================================================

agent_configs_router = APIRouter(prefix="/agent-configs", tags=["agent-configs"])


@agent_configs_router.get("")
def list_agent_configs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    search: str = "",
    agent_type: str = "",
    is_active: str = "",
    _: dict = Depends(require_admin),
):
    return _ok({"total": 0, "page": page, "page_size": page_size, "items": []})


@agent_configs_router.get("/types")
def list_agent_types(_: dict = Depends(require_admin)):
    return _ok([
        {"value": "react", "label": "ReAct 智能体", "description": "推理-行动循环，多步工具调用"},
        {"value": "plan_execute", "label": "Plan-Execute", "description": "先规划再执行，适合复杂任务"},
        {"value": "debate", "label": "辩论体", "description": "多 agent 辩论，估值/分析场景"},
    ])


@agent_configs_router.post("")
def create_agent_config_stub(_: dict = Depends(require_admin)):
    raise HTTPException(status_code=501, detail="Agent 配置 CRUD 尚未实现，请通过 LLM 供应商页管理模型")


@agent_configs_router.put("/{_id}")
def update_agent_config_stub(_id: str, _: dict = Depends(require_admin)):
    raise HTTPException(status_code=501, detail="Agent 配置 CRUD 尚未实现")


@agent_configs_router.delete("/{_id}")
def delete_agent_config_stub(_id: str, _: dict = Depends(require_admin)):
    raise HTTPException(status_code=501, detail="Agent 配置 CRUD 尚未实现")


@agent_configs_router.patch("/{_id}/toggle")
def toggle_agent_config_stub(_id: str, _: dict = Depends(require_admin)):
    raise HTTPException(status_code=501, detail="Agent 配置 CRUD 尚未实现")


@agent_configs_router.post("/{_id}/test")
def test_agent_config_stub(_id: str, _: dict = Depends(require_admin)):
    raise HTTPException(status_code=501, detail="Agent 配置 CRUD 尚未实现")


@agent_configs_router.post("/{_id}/duplicate")
def duplicate_agent_config_stub(_id: str, _: dict = Depends(require_admin)):
    raise HTTPException(status_code=501, detail="Agent 配置 CRUD 尚未实现")


# ===========================================================================
# /search-engines —— 占位
# ===========================================================================

search_engines_router = APIRouter(prefix="/search-engines", tags=["search-engines"])


@search_engines_router.get("")
def list_search_engines(_: dict = Depends(require_admin)):
    return _ok([])


@search_engines_router.get("/types")
def list_search_engine_types(_: dict = Depends(require_admin)):
    return _ok([
        {"value": "bing", "label": "Bing"},
        {"value": "google", "label": "Google"},
        {"value": "duckduckgo", "label": "DuckDuckGo"},
        {"value": "serpapi", "label": "SerpAPI"},
    ])


@search_engines_router.post("")
def create_search_engine_stub(_: dict = Depends(require_admin)):
    raise HTTPException(status_code=501, detail="搜索引擎 CRUD 尚未实现")


@search_engines_router.put("/{_id}")
def update_search_engine_stub(_id: str, _: dict = Depends(require_admin)):
    raise HTTPException(status_code=501, detail="搜索引擎 CRUD 尚未实现")


@search_engines_router.delete("/{_id}")
def delete_search_engine_stub(_id: str, _: dict = Depends(require_admin)):
    raise HTTPException(status_code=501, detail="搜索引擎 CRUD 尚未实现")


@search_engines_router.patch("/{_id}/toggle")
def toggle_search_engine_stub(_id: str, _: dict = Depends(require_admin)):
    raise HTTPException(status_code=501, detail="搜索引擎 CRUD 尚未实现")


@search_engines_router.put("/{_id}/set-default")
def set_default_search_engine_stub(_id: str, _: dict = Depends(require_admin)):
    raise HTTPException(status_code=501, detail="搜索引擎 CRUD 尚未实现")


@search_engines_router.post("/{_id}/test")
def test_search_engine_stub(_id: str, _: dict = Depends(require_admin)):
    raise HTTPException(status_code=501, detail="搜索引擎 CRUD 尚未实现")


# ===========================================================================
# /settings —— 占位（系统设置页）
# ===========================================================================

settings_router = APIRouter(prefix="/settings", tags=["settings"])


@settings_router.get("")
def get_settings(_: dict = Depends(require_admin)):
    return _ok({
        "general": {
            "site_name": "FinPilot",
            "timezone": "Asia/Shanghai",
            "language": "zh-CN",
        },
        "security": {
            "session_timeout_minutes": 10080,
            "max_login_attempts": 5,
            "require_2fa": False,
        },
        "limits": {
            "max_upload_size_mb": 50,
            "max_concurrent_queries": 10,
            "query_timeout_seconds": 30,
        },
    })


@settings_router.put("")
def update_settings(_: dict = Depends(require_admin)):
    return _ok(None, "设置已保存（占位响应）")


@settings_router.get("/health")
def get_health(_: dict = Depends(get_current_user)):
    """健康检查 —— 任意登录用户可访问"""
    return _ok({
        "status": "healthy",
        "version": "1.0.0",
        "checked_at": datetime.now().isoformat(),
    }, "ok")


# ===========================================================================
# /metrics —— 指标分析页
#
# 前端 KpiDashboardPage.tsx 期望 schema（见 frontend/src/types/metric.ts）：
#   overview  -> { year, period, cards: KpiCardData[], generated_at }
#   trend     -> { metric, label, unit, series: TrendPoint[] }
#   comparison-> { year, periods: str[], metrics: MetricComparisonItem[] }
#   drill     -> { metric, label, year, total, items: DrillDownItem[] }
#
# 这里基于 year+period 用确定性公式生成稳定的模拟财务数据，让前端 KPI 看板
# 能真正渲染出来（同比/环比/趋势/对比/钻取），而不是 404 或 undefined 崩溃。
# ===========================================================================

metrics_router = APIRouter(prefix="/metrics", tags=["metrics"])

# 指标元数据：metric key -> (label, unit)
_METRIC_META: dict[str, tuple[str, str]] = {
    "revenue": ("营业收入", "元"),
    "net_profit": ("净利润", "元"),
    "gross_profit": ("毛利润", "元"),
    "total_assets": ("资产总额", "元"),
    "total_liabilities": ("负债总额", "元"),
    "net_assets": ("净资产", "元"),
    "operating_cash_flow": ("经营活动现金流", "元"),
    "ar_balance": ("应收账款", "元"),
    "ap_balance": ("应付账款", "元"),
    "inventory": ("存货", "元"),
}

# 每个指标的基准值（2020 年 Q1 的"起点"），后续按 year/period 增长
_BASE_VALUES: dict[str, float] = {
    "revenue": 1_000_000_000.0,
    "net_profit": 150_000_000.0,
    "gross_profit": 400_000_000.0,
    "total_assets": 3_000_000_000.0,
    "total_liabilities": 1_600_000_000.0,
    "net_assets": 1_400_000_000.0,
    "operating_cash_flow": 200_000_000.0,
    "ar_balance": 300_000_000.0,
    "ap_balance": 250_000_000.0,
    "inventory": 180_000_000.0,
}


def _period_index(period: str) -> int:
    """把期间字符串映射成 0-7 的索引：Q1=0, Q2=1, Q3=2, Q4=3, H1=4, H2=5, annual=6, 其他=7"""
    mapping = {"Q1": 0, "Q2": 1, "Q3": 2, "Q4": 3, "H1": 4, "H2": 5, "annual": 6}
    return mapping.get(period, 7)


def _metric_value(metric: str, year: int, period: str) -> float:
    """确定性生成 (metric, year, period) 的模拟值：基准 × 年增长 × 季节因子"""
    base = _BASE_VALUES.get(metric, 100_000_000.0)
    # 年增长：每年 +18%（线性增长），2020 为基年
    year_factor = (1.18 ** max(year - 2020, 0))
    # 季节因子：Q1=0.85, Q2=0.95, Q3=1.10, Q4=1.40, H1=1.80, H2=2.50, annual=4.30
    period_factor = {
        "Q1": 0.85, "Q2": 0.95, "Q3": 1.10, "Q4": 1.40,
        "H1": 1.80, "H2": 2.50, "annual": 4.30,
    }.get(period, 1.0)
    # 指标特有调整：负债/应收/应付/存货增长慢一些；净利润波动大
    metric_adj = {
        "net_profit": 0.92,           # 利润略低于平均
        "total_liabilities": 1.05,    # 负债略高
        "ar_balance": 1.08,           # 应收增长快
        "ap_balance": 1.03,
        "inventory": 0.98,
    }.get(metric, 1.0)
    return round(base * year_factor * period_factor * metric_adj, 2)


def _change_tuple(metric: str, year: int, period: str, lag_periods: int) -> dict | None:
    """构造同比 (lag=4) / 环比 (lag=1) 变化值，去年/上季数据不存在则返回 None"""
    periods_order = ["Q1", "Q2", "Q3", "Q4"]
    if period not in periods_order:
        return None
    idx = periods_order.index(period)
    target_idx = idx - lag_periods
    target_year = year
    if target_idx < 0:
        target_idx += 4
        target_year = year - 1
    if target_year < 2020:
        return None
    target_period = periods_order[target_idx]
    cur = _metric_value(metric, year, period)
    prev = _metric_value(metric, target_year, target_period)
    if prev == 0:
        return None
    change = round(cur - prev, 2)
    change_pct = round((cur - prev) / prev, 4)
    return {"value": cur, "change": change, "change_pct": change_pct}


@metrics_router.get("/overview")
def metrics_overview(year: int = 0, period: str = "", _: dict = Depends(get_current_user)):
    """KPI 概览：返回核心指标卡片，含同比/环比变化"""
    year = year or datetime.utcnow().year
    period = period or "Q3"
    cards = []
    for metric, (label, unit) in _METRIC_META.items():
        value = _metric_value(metric, year, period)
        cards.append({
            "metric": metric,
            "label": label,
            "value": value,
            "unit": unit,
            "yoy": _change_tuple(metric, year, period, 4),
            "qoq": _change_tuple(metric, year, period, 1),
        })
    return _ok({
        "year": year,
        "period": period,
        "cards": cards,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    })


@metrics_router.get("/comparison")
def metrics_comparison(
    year: int = 0,
    periods: str = "Q1,Q2,Q3,Q4",
    _: dict = Depends(get_current_user),
):
    """季度对比：返回每个指标在指定 periods 上的取值"""
    year = year or datetime.utcnow().year
    period_list = [p.strip() for p in periods.split(",") if p.strip()]
    items = []
    for metric, (label, unit) in _METRIC_META.items():
        values = {p: _metric_value(metric, year, p) for p in period_list}
        items.append({
            "metric": metric,
            "label": label,
            "unit": unit,
            "values": values,
        })
    return _ok({
        "year": year,
        "periods": period_list,
        "metrics": items,
    })


@metrics_router.get("/{metric}/trend")
def metrics_trend(
    metric: str,
    years: str = "",
    _: dict = Depends(get_current_user),
):
    """年度趋势：返回指标在指定年份的年度值序列"""
    label, unit = _METRIC_META.get(metric, (metric, "元"))
    year_list = []
    if years:
        for y in years.split(","):
            y = y.strip()
            if y.isdigit():
                year_list.append(int(y))
    if not year_list:
        cur = datetime.utcnow().year
        year_list = [cur - 2, cur - 1, cur]
    series = [
        {"year": y, "value": _metric_value(metric, y, "annual")}
        for y in year_list
    ]
    return _ok({
        "metric": metric,
        "label": label,
        "unit": unit,
        "series": series,
    })


@metrics_router.get("/{metric}/drill-down")
def metrics_drill_down(
    metric: str,
    year: int = 0,
    period: str = "",
    _: dict = Depends(get_current_user),
):
    """明细钻取：返回指标在该年四个季度的占比明细"""
    label, unit = _METRIC_META.get(metric, (metric, "元"))
    year = year or datetime.utcnow().year
    quarters = ["Q1", "Q2", "Q3", "Q4"]
    values = [_metric_value(metric, year, q) for q in quarters]
    total = round(sum(values), 2)
    items = []
    for q, v in zip(quarters, values):
        ratio = round(v / total, 4) if total else None
        items.append({"period": q, "value": v, "ratio": ratio})
    return _ok({
        "metric": metric,
        "label": label,
        "year": year,
        "total": total,
        "items": items,
    })


# ===========================================================================
# /context —— 占位（上下文管理页）
# ===========================================================================

context_router = APIRouter(prefix="/context", tags=["context"])


@context_router.post("/count-tokens")
def count_tokens(payload: dict, _: dict = Depends(get_current_user)):
    text = payload.get("text", "") or ""
    # 粗略估算：1 中文字符≈2 token，1 英文单词≈1.3 token
    chars = len(text)
    return _ok({"tokens": int(chars * 1.5), "chars": chars})


@context_router.post("/optimize")
def optimize_context(payload: dict, _: dict = Depends(get_current_user)):
    return _ok({
        "optimized_messages": payload.get("messages", []),
        "removed_count": 0,
        "saved_tokens": 0,
        "message": "上下文已原样保留（占位响应）",
    })


@context_router.get("/memories")
def list_memories(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: dict = Depends(get_current_user),
):
    return _ok({"total": 0, "page": page, "page_size": page_size, "items": []})


@context_router.post("/memories/search")
def search_memories(payload: dict, _: dict = Depends(get_current_user)):
    return _ok({"query": payload.get("query", ""), "results": []})


@context_router.delete("/memories/{memory_id}")
def delete_memory(memory_id: str, _: dict = Depends(get_current_user)):
    return _ok({"id": memory_id, "deleted": False, "message": "记忆系统尚未实现"})


@context_router.get("/stats")
def context_stats(_: dict = Depends(get_current_user)):
    return _ok({
        "total_memories": 0,
        "total_tokens_used": 0,
        "token_limit": 8000,
        "usage_ratio": 0.0,
    })


# ===========================================================================
# 别名路由 —— 把前端调用错路径的请求重定向到正确端点
# ===========================================================================

aliases_router = APIRouter(prefix="", tags=["aliases"])


@aliases_router.get("/dashboard/kpi")
def dashboard_kpi_alias(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """前端 dashboard 页调用 /dashboard/kpi，实际后端是 /dashboard/admin/stats"""
    from .dashboard import dashboard_stats
    return dashboard_stats(current_user=current_user, db=db)


@aliases_router.get("/queries/recent")
def queries_recent_alias(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """前端调用 /queries/recent，后端是 /queries/history"""
    from .queries import query_history
    return query_history(skip=0, limit=limit, db=db, current_user=current_user)


@aliases_router.get("/factor-mining/strategies")
def factor_mining_strategies_alias(current_user: dict = Depends(get_current_user)):
    """前端调用 /factor-mining/strategies，后端是 /factor-mining/factor-categories"""
    from .factor_mining import list_factor_categories
    return list_factor_categories(current_user=current_user)


@aliases_router.get("/valuation/models")
def valuation_models_alias(_: dict = Depends(get_current_user)):
    """前端调用 /valuation/models，后端没有该端点 —— 返回内置估值模型列表"""
    return _ok([
        {"value": "dcf", "label": "DCF 现金流折现", "description": "自由现金流折现估值"},
        {"value": "ddm", "label": "DDM 股利折现", "description": "稳定股利股票估值"},
        {"value": "comps", "label": "可比公司", "description": "相对估值法"},
        {"value": "monte_carlo", "label": "蒙特卡洛", "description": "概率分布模拟"},
        {"value": "scenario", "label": "情景分析", "description": "多情景估值"},
    ])


@aliases_router.get("/reports/templates")
def reports_templates_alias(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """前端调用 /reports/templates，后端是 /report-templates"""
    from .report_templates import list_templates_api
    return list_templates_api(db=db, current_user=current_user, page=page, page_size=page_size)


# ===========================================================================
# 注册到主 router
# ===========================================================================

def register_compat_routes(api: APIRouter) -> None:
    """把所有兼容路由挂载到主 API router 上"""
    api.include_router(model_configs_router)
    api.include_router(agent_configs_router)
    api.include_router(search_engines_router)
    api.include_router(settings_router)
    api.include_router(metrics_router)
    api.include_router(context_router)
    api.include_router(aliases_router)
