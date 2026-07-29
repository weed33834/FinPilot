# -*- coding: utf-8 -*-
"""前端契约兼容路由共享的辅助函数。

把 ``_ok`` / ``_tenant_of`` / ``_parse_int_id`` / ``_coerce_model_id``
集中放在这里，让从 compat.py 拆分出来的各模块共用同一份实现，
避免重复定义或互相循环导入。
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException, status

# 统一 tenant_id 计算：从 deps 导入并 re-export，保持向后兼容。
# 此前本函数用 ``str(user.get("tenant_id") or user.get("user_id") or "default")``
# 产生 ``"1"``，与 agent.py 的 ``"user_1"`` 不一致，导致多租户隔离失效。
from finpilot.api.deps import tenant_of  # noqa: F401


def ok(data: Any, message: str = "success") -> dict:
    """统一 ``{code, message, data}`` 包装，与前端 ``DataResponse<T>`` 对齐。"""
    return {"code": 0, "message": message, "data": data}


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
