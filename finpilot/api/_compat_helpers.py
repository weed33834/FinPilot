# -*- coding: utf-8 -*-
"""前端契约兼容路由共享的辅助函数。

把 ``_ok`` / ``_tenant_of`` / ``_parse_int_id`` / ``_coerce_model_id``
集中放在这里，让从 compat.py 拆分出来的各模块共用同一份实现，
避免重复定义或互相循环导入。
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException, status


def ok(data: Any, message: str = "success") -> dict:
    """统一 ``{code, message, data}`` 包装，与前端 ``DataResponse<T>`` 对齐。"""
    return {"code": 0, "message": message, "data": data}


def tenant_of(user: dict) -> str:
    """从当前用户解析 tenant_id：优先 ``tenant_id``，其次 ``user_id``，兜底 ``default``。"""
    return str(user.get("tenant_id") or user.get("user_id") or "default")


def parse_int_id(_id: str, label: str = "记录") -> int:
    """把路径参数 ``_id`` 解析为 int；非法格式按 404 处理。"""
    try:
        return int(_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=404, detail=f"{label} {_id} 不存在")


def coerce_model_id(value: Any) -> Optional[int]:
    """把前端传来的 ``model_id``（字符串/整数/空）转为 int 或 None。"""
    if value in (None, "", 0):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"model_id 必须是整数：{value!r}",
        )
