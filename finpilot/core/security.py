"""安全模块 — argon2 密码哈希与验证。

替换原有的 hashlib.sha256（无盐、无迭代），使用 argon2id：
- time_cost=3  (迭代次数)
- memory_cost=65536 (64 MiB 内存)
- parallelism=4 (并行度)
"""
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)


def hash_password(password: str) -> str:
    """对明文密码进行 argon2id 哈希，返回编码后的哈希字符串。"""
    return ph.hash(password)


def verify_password(password: str, password_hash: str) -> tuple[bool, str | None]:
    """验证明文密码与 argon2 哈希是否匹配。

    Returns:
        (True, new_hash) — 验证通过但哈希参数需更新，调用方应持久化 new_hash
        (True, None)    — 验证通过且哈希参数无需更新
        (False, None)   — 密码不匹配
    """
    try:
        ph.verify(password_hash, password)
        if ph.check_needs_rehash(password_hash):
            return True, hash_password(password)
        return True, None
    except VerifyMismatchError:
        return False, None
