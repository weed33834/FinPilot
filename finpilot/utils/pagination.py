"""SQLAlchemy 查询分页工具."""

from typing import Any

from sqlalchemy.orm import Query


def apply_page(query: Query[Any], page: int, page_size: int) -> Query[Any]:
    """对 query 应用 offset+limit（不执行、不计数）。"""
    return query.offset((page - 1) * page_size).limit(page_size)


def paginate(query: Query[Any], page: int, page_size: int) -> tuple[list[Any], int]:
    """分页查询：返回 (items, total)。total 在 offset/limit 前计数。"""
    total = query.count()
    items = apply_page(query, page, page_size).all()
    return items, total
