"""工作流持久化 API —— /api/v1/workflows

将前端工作流编辑器从 localStorage 升级为服务端持久化存储。
使用轻量级 SQL 表（不依赖 ORM 模型以避免循环导入）。
"""
from __future__ import annotations

import json
from datetime import datetime
try:
    from datetime import UTC
except ImportError:  # Python 3.10 lacks datetime.UTC; use timezone.utc
    from datetime import timezone
    UTC = timezone.utc
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from finpilot.api.deps import get_current_user, get_db_session

router = APIRouter(prefix="/workflows", tags=["workflows"])

# 表自动创建（幂等）
_WORKFLOW_DDL = """
CREATE TABLE IF NOT EXISTS workflows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id VARCHAR(100) NOT NULL DEFAULT '',
    name VARCHAR(255) NOT NULL DEFAULT '未命名工作流',
    description TEXT DEFAULT '',
    nodes TEXT DEFAULT '[]',
    edges TEXT DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_workflows_tenant ON workflows(tenant_id);
CREATE INDEX IF NOT EXISTS idx_workflows_updated ON workflows(tenant_id, updated_at DESC);
"""


# ---- 工具函数 ----
def _ensure_table(db: Session) -> None:
    """幂等创建 workflows 表。"""
    for stmt in _WORKFLOW_DDL.split(";"):
        s = stmt.strip()
        if s:
            db.execute(text(s))
    db.commit()


def _row_to_dict(row) -> dict:
    return {
        "id": row[0],
        "name": row[2],
        "description": row[3] or "",
        "nodes": json.loads(row[4]) if row[4] else [],
        "edges": json.loads(row[5]) if row[5] else [],
        "created_at": row[6] or "",
        "updated_at": row[7] or "",
    }


# ---- Pydantic schemas ----
class WorkflowSaveRequest(BaseModel):
    name: str = "未命名工作流"
    description: str = ""
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


# ---- Routes ----
@router.get("")
def list_workflows(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    _ensure_table(db)
    tid = f"user_{current_user.get('user_id', 'default')}"
    rows = db.execute(
        text("SELECT * FROM workflows WHERE tenant_id=:tid ORDER BY updated_at DESC LIMIT :lim"),
        {"tid": tid, "lim": limit},
    ).fetchall()
    return {"code": 0, "message": "ok", "data": [_row_to_dict(r) for r in rows]}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_workflow(
    req: WorkflowSaveRequest,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    _ensure_table(db)
    tid = f"user_{current_user.get('user_id', 'default')}"
    now = datetime.now(UTC).isoformat()
    result = db.execute(
        text("""INSERT INTO workflows (tenant_id,name,description,nodes,edges,created_at,updated_at)
                VALUES (:tid,:name,:desc,:nodes,:edges,:now,:now)"""),
        {
            "tid": tid, "name": req.name, "desc": req.description,
            "nodes": json.dumps(req.nodes, ensure_ascii=False),
            "edges": json.dumps(req.edges, ensure_ascii=False),
            "now": now,
        },
    )
    db.commit()
    wid = result.lastrowid
    row = db.execute(text("SELECT * FROM workflows WHERE id=:id"), {"id": wid}).fetchone()
    return {"code": 0, "message": "ok", "data": _row_to_dict(row) if row else {}}


@router.put("/{workflow_id}")
def update_workflow(
    workflow_id: int,
    req: WorkflowSaveRequest,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    _ensure_table(db)
    tid = f"user_{current_user.get('user_id', 'default')}"
    now = datetime.now(UTC).isoformat()
    result = db.execute(
        text("""UPDATE workflows SET name=:name,description=:desc,nodes=:nodes,edges=:edges,updated_at=:now
                WHERE id=:id AND tenant_id=:tid"""),
        {
            "id": workflow_id, "tid": tid, "name": req.name, "desc": req.description,
            "nodes": json.dumps(req.nodes, ensure_ascii=False),
            "edges": json.dumps(req.edges, ensure_ascii=False),
            "now": now,
        },
    )
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="工作流不存在")
    row = db.execute(text("SELECT * FROM workflows WHERE id=:id"), {"id": workflow_id}).fetchone()
    return {"code": 0, "message": "ok", "data": _row_to_dict(row) if row else {}}


@router.get("/{workflow_id}")
def get_workflow(
    workflow_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    _ensure_table(db)
    tid = f"user_{current_user.get('user_id', 'default')}"
    row = db.execute(
        text("SELECT * FROM workflows WHERE id=:id AND tenant_id=:tid"),
        {"id": workflow_id, "tid": tid},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return {"code": 0, "message": "ok", "data": _row_to_dict(row)}


@router.delete("/{workflow_id}")
def delete_workflow(
    workflow_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    _ensure_table(db)
    tid = f"user_{current_user.get('user_id', 'default')}"
    result = db.execute(
        text("DELETE FROM workflows WHERE id=:id AND tenant_id=:tid"),
        {"id": workflow_id, "tid": tid},
    )
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return {"code": 0, "message": "已删除"}
