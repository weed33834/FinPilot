"""通用响应、分页等数据结构。"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class DataResponse(BaseModel):
    """统一响应包装."""

    code: int = Field(default=0, description="业务状态码，0 表示成功")
    message: str = Field(default="ok", description="提示信息")


class GenericDataResponse(BaseModel, Generic[T]):
    """带数据的统一响应包装（泛型版）."""

    code: int = Field(default=0)
    message: str = Field(default="ok")
    data: T


class PaginationMeta(BaseModel):
    """分页元数据."""

    total: int = Field(description="总记录数")
    page: int = Field(description="当前页码，从 1 开始")
    page_size: int = Field(description="每页条数")
    total_pages: int = Field(description="总页数")


class PaginatedData(BaseModel, Generic[T]):
    """分页数据."""

    items: list[T]
    total: int
    page: int
    page_size: int


class ErrorResponse(BaseModel):
    """错误响应."""

    code: int = Field(description="HTTP 状态码或业务错误码")
    message: str = Field(description="错误描述")
    detail: Any | None = Field(default=None, description="错误详情")
    request_id: str | None = Field(default=None, description="请求追踪 ID")


class HealthResponse(BaseModel):
    """健康检查响应."""

    status: str = Field(default="ok")
    version: str = Field(default="0.1.0")
    services: dict[str, str] = Field(default_factory=dict)
