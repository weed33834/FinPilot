# -*- coding: utf-8 -*-
"""数据连接器 CRUD — 外部数据源连接配置管理（CSV 批量上传 + DB 直连 + API Key / SFTP / S3）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from finpilot.api.deps import get_current_user, get_db_session
from finpilot.core.permissions import Permission, require_permission
from finpilot.database.models import DataConnection, User

router = APIRouter(prefix="/data-connections", tags=["data-connections"])

_SENSITIVE_KEYS = {
    "client_secret", "api_key", "password", "secret_key",
    "access_key", "secret_access_key", "token", "private_key",
}


def _redact(config: dict | None) -> dict:
    """替换 config 中的敏感字段为占位符。"""
    if not config:
        return {}
    return {k: ("***REDACTED***" if k in _SENSITIVE_KEYS else v) for k, v in config.items()}


def _conn_dict(c: DataConnection) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "connection_type": c.connection_type,
        "config": _redact(c.config),
        "created_by": c.created_by,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


# ── Schema ───────────────────────────────────────────

class DataConnectionCreate(BaseModel):
    name: str = Field(..., max_length=200, description="连接名称")
    connection_type: str = Field(
        ..., max_length=32, pattern=r"^(api_key|database|sftp|s3|custom)$",
        description="连接类型：api_key / database / sftp / s3 / custom",
    )
    config: dict = Field(default_factory=dict, description="连接参数 JSON")


class DataConnectionUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    config: dict | None = None


# ── CRUD Endpoints ────────────────────────────────────

@router.get("")
async def list_connections(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    connection_type: str | None = Query(None, description="按类型过滤"),
):
    """列出当前租户下所有数据连接。"""
    require_permission(current_user, Permission.FINANCE_VIEW)
    stmt = select(DataConnection)
    if connection_type:
        stmt = stmt.where(DataConnection.connection_type == connection_type)
    connections = db.execute(stmt.order_by(DataConnection.name)).scalars().all()
    return {"code": 0, "data": [_conn_dict(c) for c in connections]}


@router.get("/{connection_id}")
async def get_connection(
    connection_id: int,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """获取单个数据连接详情。"""
    require_permission(current_user, Permission.FINANCE_VIEW)
    conn = db.get(DataConnection, connection_id)
    if not conn:
        raise HTTPException(404, "数据连接不存在")
    return {"code": 0, "data": _conn_dict(conn)}


@router.post("", status_code=201)
async def create_connection(
    body: DataConnectionCreate,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """创建新的数据连接。"""
    require_permission(current_user, Permission.FINANCE_MANAGE)
    conn = DataConnection(
        name=body.name,
        connection_type=body.connection_type,
        config=body.config,
        created_by=current_user.id,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return {"code": 0, "data": _conn_dict(conn), "message": "数据连接已创建"}


@router.put("/{connection_id}")
async def update_connection(
    connection_id: int,
    body: DataConnectionUpdate,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """更新数据连接名称或配置。"""
    require_permission(current_user, Permission.FINANCE_MANAGE)
    conn = db.get(DataConnection, connection_id)
    if not conn:
        raise HTTPException(404, "数据连接不存在")
    if body.name is not None:
        conn.name = body.name
    if body.config is not None:
        conn.config = body.config
    db.commit()
    db.refresh(conn)
    return {"code": 0, "data": _conn_dict(conn), "message": "数据连接已更新"}


@router.delete("/{connection_id}")
async def delete_connection(
    connection_id: int,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """删除数据连接。"""
    require_permission(current_user, Permission.FINANCE_MANAGE)
    conn = db.get(DataConnection, connection_id)
    if not conn:
        raise HTTPException(404, "数据连接不存在")
    db.delete(conn)
    db.commit()
    return {"code": 0, "message": "数据连接已删除"}


@router.post("/test/{connection_id}")
async def test_connection(
    connection_id: int,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """测试数据连接是否可用（尝试验证而非实际连接以保安全）。"""
    require_permission(current_user, Permission.FINANCE_MANAGE)
    conn = db.get(DataConnection, connection_id)
    if not conn:
        raise HTTPException(404, "数据连接不存在")
    if not conn.config:
        return {"code": 0, "data": {"status": "unconfigured", "message": "连接配置为空"}}

    host = conn.config.get("host") or conn.config.get("endpoint")
    if not host:
        return {"code": 0, "data": {"status": "incomplete", "message": "缺少 host/endpoint 参数"}}

    return {"code": 0, "data": {
        "status": "configured",
        "message": f"连接配置完整（target: {host}），实际可用性需在运行时验证",
    }}


@router.post("/csv/preview")
async def preview_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """上传 CSV 文件预览前 10 行（含列名），用于导入前确认结构。"""
    require_permission(current_user, Permission.FINANCE_MANAGE)
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "仅支持 CSV 文件")

    import csv
    import io
    content = (await file.read()).decode("utf-8-sig")
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    if len(rows) < 1:
        raise HTTPException(400, "CSV 文件为空")

    headers = rows[0]
    preview = rows[1:11]
    return {
        "code": 0,
        "data": {
            "filename": file.filename,
            "columns": headers,
            "total_rows": len(rows) - 1,
            "preview": preview,
        },
    }
