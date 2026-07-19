# -*- coding: utf-8 -*-
"""文档管理路由 - 上传、解析、索引到 RAG。

- GET    /            列出文档（分页）
- POST   /upload      上传文档，自动解析并索引到 RAG
- GET    /{id}        获取文档详情
- DELETE /{id}        删除文档

文件保存到 ~/.finpilot/uploads/，上传限制 50MB。
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from finpilot.database import crud
from finpilot.parser import ParserError, get_parser
from finpilot.rag import RagService

from .deps import get_current_user, get_db_session
from .schemas import DocumentResponse

router = APIRouter(prefix="/documents", tags=["documents"])

# 上传文件保存目录
UPLOAD_DIR = Path.home() / ".finpilot" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 文件大小上限 50MB
MAX_FILE_SIZE = 50 * 1024 * 1024


def _tenant_of(user: dict) -> str:
    """按用户生成租户 ID，用于文档隔离"""
    return f"user_{user['user_id']}"


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """列出当前用户的文档（分页）"""
    docs = crud.list_documents(
        db, tenant_id=_tenant_of(current_user), skip=skip, limit=limit
    )
    return docs


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """上传文档：保存 -> 解析 -> 索引到 RAG"""
    import time as _time

    started_at = _time.time()
    parse_success = True
    parse_error = ""
    pages_count = 0
    tables_count = 0

    # 读取文件内容并校验大小
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="文件超过 50MB 限制",
        )

    # 保存到上传目录，用 uuid 避免重名
    ext = os.path.splitext(file.filename or "")[1]
    saved_name = f"{uuid.uuid4().hex}{ext}"
    saved_path = UPLOAD_DIR / saved_name
    saved_path.write_bytes(content)

    tenant_id = _tenant_of(current_user)
    # 创建文档记录（状态 pending）
    doc = crud.create_document(
        db,
        filename=file.filename or saved_name,
        file_path=str(saved_path),
        file_type=ext.lstrip(".").lower(),
        file_size=len(content),
        tenant_id=tenant_id,
        uploaded_by=current_user["user_id"],
    )

    # 解析文档
    try:
        parser = get_parser(str(saved_path))
        parsed = parser.parse(str(saved_path))
        pages_count = len(getattr(parsed, "pages", []) or [])
        # 某些 parser 在 page 上挂 tables 字段
        for p in getattr(parsed, "pages", []) or []:
            tbls = getattr(p, "tables", None)
            if tbls:
                tables_count += len(tbls)
    except ParserError as exc:
        parse_success = False
        parse_error = str(exc)
        crud.update_document_status(db, doc.id, "failed")
        # best-effort 埋点：解析失败也要记录
        try:
            from finpilot.services.runtime_log_service import log_runtime

            log_runtime(
                db,
                category="document_parse",
                event="parse_failed",
                message=f"解析失败: {file.filename or saved_name}",
                source="documents.upload",
                payload={
                    "filename": file.filename or saved_name,
                    "file_type": ext.lstrip(".").lower(),
                    "file_size": len(content),
                    "pages": 0,
                    "tables": 0,
                    "error": parse_error,
                    "document_id": str(doc.id),
                },
                duration_ms=int((_time.time() - started_at) * 1000),
                tenant_id=tenant_id,
                user_id=str(current_user["user_id"]),
                success=False,
                level="error",
            )
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"解析失败: {exc}",
        )

    # 拼接全文并索引到 RAG
    full_text = "\n\n".join(p.text for p in parsed.pages if p.text)
    rag = RagService(db)
    rag.index_document(doc.id, full_text, tenant_id=tenant_id)
    crud.update_document_status(db, doc.id, "indexed")
    db.refresh(doc)

    # best-effort 埋点：解析成功
    try:
        from finpilot.services.runtime_log_service import log_runtime

        log_runtime(
            db,
            category="document_parse",
            event="parse_complete",
            message=f"文档解析完成: {file.filename or saved_name}",
            source="documents.upload",
            payload={
                "filename": file.filename or saved_name,
                "file_type": ext.lstrip(".").lower(),
                "file_size": len(content),
                "pages": pages_count,
                "tables": tables_count,
                "document_id": str(doc.id),
            },
            duration_ms=int((_time.time() - started_at) * 1000),
            tenant_id=tenant_id,
            user_id=str(current_user["user_id"]),
            success=parse_success,
            level="info",
        )
    except Exception:  # noqa: BLE001
        pass
    return doc


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """获取文档详情"""
    doc = crud.get_document(db, document_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")
    return doc


@router.delete("/{document_id}")
def delete_document(
    document_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """删除文档（同时删除物理文件）"""
    doc = crud.get_document(db, document_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")
    # 删除物理文件，不存在则忽略
    try:
        if doc.file_path and os.path.isfile(doc.file_path):
            os.remove(doc.file_path)
    except OSError:
        pass
    db.delete(doc)
    db.commit()
    return {"message": "已删除"}
