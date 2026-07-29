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

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from finpilot.database import crud
from finpilot.database.models import Document, FinancialAccount, FinancialReport
from finpilot.parser import ParserError, get_parser
from finpilot.rag import RagService

from .deps import get_current_user, get_db_session, tenant_of

router = APIRouter(prefix="/documents", tags=["documents"])


def _ok(data, message: str = "success") -> dict:
    """统一 {code, message, data} 包装，与前端 ApiResponse<T> 对齐。"""
    return {"code": 0, "message": message, "data": data}


def _doc_to_dict(doc) -> dict:
    """Document ORM → 前端 Document 字段（与 DocumentResponse 对齐）。"""
    return {
        "id": str(doc.id),
        "filename": doc.filename,
        "file_type": doc.file_type,
        "file_size": doc.file_size,
        "status": doc.status,
        "uploaded_by": str(doc.uploaded_by) if doc.uploaded_by is not None else None,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        "tenant_id": doc.tenant_id,
    }

# 上传文件保存目录
UPLOAD_DIR = Path.home() / ".finpilot" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 文件大小上限 50MB
MAX_FILE_SIZE = 50 * 1024 * 1024


def _parse_number(value: str) -> float | None:
    """尽力把表格单元格解析为数字；失败返回 None。"""
    if value is None:
        return None
    s = str(value).strip().replace(",", "").replace("，", "")
    if not s or s in {"-", "—", "nan", "None"}:
        return None
    # 去掉百分号、括号负数等常见格式
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    if s.endswith("%"):
        s = s[:-1]
    try:
        num = float(s)
        return -num if neg else num
    except (TypeError, ValueError):
        return None


def _persist_tables(
    db: Session,
    *,
    document_id: int,
    tenant_id: str,
    filename: str,
    tables: list[list[list[str]]],
) -> int:
    """把解析出的表格结构化入库为 FinancialReport + FinancialAccount.

    每张表（首行视为表头）落一条 FinancialReport（关联 document_id 溯源），
    其每一数据行落一条 FinancialAccount：account_name=首列文本，
    account_category=其他文本列，balance=首个可解析数值列。

    返回成功入库的科目数（0 表示无可用结构化数据）。
    """
    if not tables:
        return 0

    base_name = os.path.splitext(filename)[0]
    accounts_count = 0

    for idx, table in enumerate(tables, start=1):
        # 至少需要表头 + 1 行数据
        if not table or len(table) < 2:
            continue
        header = [str(c or "").strip() for c in table[0]]
        if not any(header):
            continue

        report = FinancialReport(
            tenant_id=tenant_id,
            report_name=f"{base_name} - 表{idx}",
            report_type="auto_extracted",
            period=None,
            data_json=None,
            document_id=document_id,
        )
        db.add(report)
        db.flush()  # 拿到 report.id

        for row in table[1:]:
            cells = [str(c or "").strip() for c in row]
            if not any(cells):
                continue
            account_name = cells[0] if cells[0] else (header[0] or f"行{idx}")
            # 首个可解析数值列作为 balance
            balance: float | None = None
            for cell in cells[1:]:
                balance = _parse_number(cell)
                if balance is not None:
                    break
            # 其余文本列拼为 account_category
            text_cols = [
                cells[i]
                for i in range(1, len(cells))
                if i < len(header) and cells[i] and _parse_number(cells[i]) is None
            ]
            account_category = " / ".join(text_cols[:2]) if text_cols else None

            db.add(
                FinancialAccount(
                    report_id=report.id,
                    account_name=account_name,
                    account_category=account_category,
                    balance=balance if balance is not None else 0.0,
                    debit_amount=0.0,
                    credit_amount=0.0,
                )
            )
            accounts_count += 1

    if accounts_count:
        db.commit()
    else:
        db.rollback()
    return accounts_count


@router.get("")
def list_documents(
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(50, ge=1, le=500, description="每页条数"),
    status: str | None = Query(None, description="按状态筛选: pending/parsing/indexed/failed"),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """列出当前用户的文档（分页）.

    前端契约（documents.ts）：``ApiResponse<PaginatedData<Document>>``，
    即 ``{code, message, data: {items, total, page, page_size}}``。
    此前返回裸数组 + skip/limit 参数，导致前端 ``resp.data.data.items`` 为 undefined。
    """
    tenant_id = tenant_of(current_user)
    # crud.list_documents 不支持 status 过滤，这里在查询层补上
    q = db.query(Document).filter(Document.tenant_id == tenant_id)
    if status:
        q = q.filter(Document.status == status)
    total = q.count()
    docs = (
        q.order_by(Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return _ok({
        "items": [_doc_to_dict(d) for d in docs],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.post("/upload", status_code=status.HTTP_201_CREATED)
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

    tenant_id = tenant_of(current_user)
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
        # 顶层汇总表格（更可靠）
        top_tables = getattr(parsed, "tables", []) or []
        if top_tables:
            tables_count = max(tables_count, len(top_tables))
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

    # 结构化入库：把解析出的表格落为 FinancialReport/FinancialAccount，
    # 建立文档→结构化报表→text2sql 查询 的因果链条
    structured_accounts = 0
    structured_error = ""
    try:
        structured_accounts = _persist_tables(
            db,
            document_id=doc.id,
            tenant_id=tenant_id,
            filename=file.filename or saved_name,
            tables=top_tables,
        )
    except Exception as exc:  # noqa: BLE001
        structured_error = str(exc)

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
                "structured_accounts": structured_accounts,
                "structured_error": structured_error or None,
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

    # 审计埋点：文档上传 + 结构化入库结果
    try:
        from finpilot.services.audit_service import log_action

        log_action(
            db,
            action="document_upload",
            resource=f"document:{doc.id}",
            user=current_user,
            reason=f"上传文件 {file.filename or saved_name}",
            commit=False,
            target_object_type="document",
            target_object_id=str(doc.id),
            meta={
                "filename": file.filename or saved_name,
                "file_type": ext.lstrip(".").lower(),
                "pages": pages_count,
                "tables": tables_count,
                "structured_accounts": structured_accounts,
            },
        )
    except Exception:  # noqa: BLE001
        pass

    # 通知上传人：文档解析+索引完成（best-effort，DB 写入 + WebSocket 推送）
    try:
        from .notifications import _user_id_of, notify_user

        notify_user(
            db,
            _user_id_of(current_user),
            channel="document",
            title="文档处理完成",
            content=(
                f"《{file.filename or saved_name}》已解析并索引"
                f"（{pages_count} 页 / {tables_count} 表 / "
                f"{structured_accounts} 科目）"
            ),
            tenant_id=tenant_id,
        )
    except Exception:  # noqa: BLE001
        pass
    return _ok(_doc_to_dict(doc), "上传成功")


@router.get("/{document_id}")
def get_document(
    document_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """获取文档详情."""
    # 带 tenant_id 过滤，防止跨租户读取（db.get 不触发 tenant_filter 事件）
    tenant_id = tenant_of(current_user)
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.tenant_id == tenant_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")
    return _ok(_doc_to_dict(doc))


@router.delete("/{document_id}")
def delete_document(
    document_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """删除文档（同时删除物理文件）."""
    # 带 tenant_id 过滤，防止跨租户删除（db.get 不触发 tenant_filter 事件）
    tenant_id = tenant_of(current_user)
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.tenant_id == tenant_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")
    # 删除物理文件，不存在则忽略
    try:
        if doc.file_path and os.path.isfile(doc.file_path):
            os.remove(doc.file_path)
    except OSError:
        pass
    # 清理 RAG 索引：移除该文档在内存索引与 DocumentChunk 表中的 chunk，
    # 此前仅删 Document 记录，导致内存索引与 DB 状态不一致、检索命中已删文档
    try:
        rag = RagService(db)
        rag.remove_document(document_id, db)
    except Exception:  # noqa: BLE001  索引清理失败不阻断文档删除
        pass
    db.delete(doc)
    db.commit()
    return _ok(None, "已删除")


@router.post("/{document_id}/reindex")
def reindex_document(
    document_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """重建指定文档的 RAG 索引。

    场景：文档内容更新、embedding 模型升级、或索引损坏后需重新切分+向量化。
    先移除旧 chunk（内存+DB），再重新解析物理文件并索引。
    """
    tenant_id = tenant_of(current_user)
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.tenant_id == tenant_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")
    if not doc.file_path or not os.path.isfile(doc.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档物理文件不存在，无法重建索引",
        )

    rag = RagService(db)
    # 1. 移除旧索引
    removed = rag.remove_document(document_id, db)
    # 2. 重新解析物理文件
    try:
        parser = get_parser(doc.file_path)
        parsed = parser.parse(doc.file_path)
    except ParserError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"解析失败: {exc}",
        )
    # 3. 重新索引
    full_text = "\n\n".join(p.text for p in parsed.pages if p.text)
    chunks = rag.index_document(doc.id, full_text, tenant_id=tenant_id)
    crud.update_document_status(db, doc.id, "indexed")
    return _ok(
        {"document_id": str(doc.id), "removed_chunks": removed, "indexed_chunks": chunks},
        "索引重建完成",
    )
