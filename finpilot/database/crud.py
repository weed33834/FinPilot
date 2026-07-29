"""
基础 CRUD 操作 - 文档、用户、会话、LLM配置
API key 使用 Fernet (AES) 对称加密存储（见 finpilot.core.crypto），
旧 base64 数据可平滑迁移：decode_api_key 自动回退解码。
"""
from typing import Optional

from sqlalchemy.orm import Session

from finpilot.core.crypto import decrypt as _crypto_decrypt, encrypt as _crypto_encrypt

from .models import (
    User,
    Document,
    Conversation,
    Message,
    LlmProvider,
    LlmModel,
)


# ---------- API Key 加密工具（Fernet AES，向后兼容 base64）----------
def encode_api_key(raw_key: str) -> str:
    """加密明文 API key 后存储（Fernet AES-128-CBC + HMAC）。"""
    return _crypto_encrypt(raw_key)


def decode_api_key(encoded_key: str) -> str:
    """解密 API key；旧 base64 数据自动回退解码（平滑迁移）。"""
    return _crypto_decrypt(encoded_key)


# ---------- 文档 CRUD ----------
def create_document(db: Session, filename: str, file_path: str, **kwargs) -> Document:
    """创建文档记录，kwargs 可传入 file_type/file_size/tenant_id/uploaded_by 等"""
    doc = Document(filename=filename, file_path=file_path, **kwargs)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def get_document(db: Session, document_id: int) -> Optional[Document]:
    """按 ID 获取文档"""
    return db.get(Document, document_id)


def list_documents(
    db: Session,
    tenant_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> list[Document]:
    """获取文档列表，支持按租户过滤，按创建时间倒序"""
    query = db.query(Document)
    if tenant_id:
        query = query.filter(Document.tenant_id == tenant_id)
    return query.order_by(Document.created_at.desc()).offset(skip).limit(limit).all()


def update_document_status(db: Session, document_id: int, status: str) -> Optional[Document]:
    """更新文档处理状态（pending/indexed/failed）"""
    doc = db.get(Document, document_id)
    if doc:
        doc.status = status
        db.commit()
        db.refresh(doc)
    return doc


# ---------- 用户 CRUD ----------
def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """按邮箱获取用户"""
    return db.query(User).filter(User.email == email).first()


def create_user(
    db: Session,
    email: str,
    password_hash: str,
    name: Optional[str] = None,
    role: str = "analyst",
) -> User:
    """创建用户"""
    user = User(email=email, password_hash=password_hash, name=name, role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------- 会话 CRUD ----------
def create_conversation(
    db: Session,
    user_id: int,
    title: str,
    tenant_id: Optional[str] = None,
) -> Conversation:
    """创建会话"""
    conv = Conversation(user_id=user_id, title=title, tenant_id=tenant_id)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def get_conversations(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 50,
) -> list[Conversation]:
    """获取指定用户的会话列表，按创建时间倒序"""
    return (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id)
        .order_by(Conversation.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def add_message(
    db: Session,
    conversation_id: int,
    role: str,
    content: str,
    model_name: Optional[str] = None,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    latency_ms: Optional[int] = None,
    tool_calls: Optional[str] = None,
) -> Message:
    """向会话中添加一条消息（role: user/assistant/system）.

    LLM 运行时元数据（model_name/tokens_in/tokens_out/latency_ms/tool_calls）
    仅在 assistant 消息上填充；user/system 消息保留默认 None。
    tool_calls 应为 JSON 字符串（调用方负责序列化）。
    """
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        model_name=model_name,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
        tool_calls=tool_calls,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


# ---------- LLM 配置 CRUD ----------
def get_default_provider(db: Session) -> Optional[LlmProvider]:
    """获取默认 LLM 供应商（is_default=True 且 is_active=True）"""
    return (
        db.query(LlmProvider)
        .filter(LlmProvider.is_default.is_(True), LlmProvider.is_active.is_(True))
        .first()
    )


def get_models_by_tier(
    db: Session,
    tier: str,
    provider_id: Optional[int] = None,
) -> list[LlmModel]:
    """按性能层级获取可用模型列表（tier: low/medium/high）"""
    query = db.query(LlmModel).filter(LlmModel.tier == tier, LlmModel.is_active.is_(True))
    if provider_id:
        query = query.filter(LlmModel.provider_id == provider_id)
    return query.all()
