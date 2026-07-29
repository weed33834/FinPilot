# -*- coding: utf-8 -*-
"""对称加密模块 — 使用 Fernet (AES-128-CBC + HMAC-SHA256) 保护静态密钥。

用于加密落库的敏感凭据：LLM/MCP 的 ``api_key``、用户 ``totp_secret`` 等。
此前这些凭据仅用 base64 编码（可逆、无密钥），等于明文存储，存在泄露风险。

主密钥 (KEK) 来源（按优先级）：
1. 环境变量 ``FINPILOT_ENCRYPTION_KEY``（urlsafe_base64 编码的 32 字节，生产必配）
2. 文件 ``~/.finpilot/secret.key``（首次启动自动生成，开发环境零配置可用）

向后兼容：``decrypt`` 会先尝试 Fernet 解密，失败再回退 base64 解码旧数据，
确保存量库平滑迁移；旧数据一经 ``encrypt`` 重写即升级为密文。
"""
from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_KEY_FILE = Path.home() / ".finpilot" / "secret.key"


def _load_or_create_key() -> bytes:
    """加载 KEK：优先环境变量，其次本地密钥文件（不存在则生成并持久化）。"""
    env_key = os.getenv("FINPILOT_ENCRYPTION_KEY")
    if env_key:
        return env_key.encode("utf-8")
    _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if _KEY_FILE.exists():
        return _KEY_FILE.read_bytes()
    key = Fernet.generate_key()
    _KEY_FILE.write_bytes(key)
    _KEY_FILE.chmod(0o600)
    logger.warning(
        "FINPILOT_ENCRYPTION_KEY 未设置，已生成开发用密钥文件 %s。"
        "生产环境请显式设置环境变量，并将该文件纳入备份。",
        _KEY_FILE,
    )
    return key


_fernet: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_or_create_key())
    return _fernet


def encrypt(plaintext: str) -> str:
    """加密明文，返回 Fernet token 字符串（urlsafe_base64）。"""
    if not plaintext:
        return plaintext
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    """解密 Fernet token；若为旧 base64 数据则回退解码（平滑迁移）。"""
    if not token:
        return token
    try:
        return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        # 旧 base64 编码数据（迁移期兼容）
        try:
            return base64.b64decode(token.encode("utf-8")).decode("utf-8")
        except Exception:  # noqa: BLE001
            return token


def is_encrypted(value: Optional[str]) -> bool:
    """粗略判断值是否已为 Fernet 密文（以 'gAAAAA' 开头）。"""
    return bool(value) and value.startswith("gAAAAA")
