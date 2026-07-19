"""沙箱配置加载器 — 从 DB 加载沙箱配置并应用到运行时.

配置层级:
1. 系统默认 (is_system=True) — 全局基线
2. 租户覆盖 (tenant_id=X) — 租户级别自定义
合并策略: 租户配置覆盖系统默认, 未定义的键继承系统默认
"""

# TODO: requires finpilot.database.models.SandboxConfig

from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Iterator

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 默认配置常量（代码沙箱 / SQL / 文件上传的硬编码基线）
# 这些常量既是 dataclass 的回退默认值, 也是 code_sandbox.py 的单一事实来源。
# ---------------------------------------------------------------------------

DEFAULT_ALLOWED_MODULES: frozenset[str] = frozenset({
    # 标准库 — 数学
    "math", "cmath",
    # 标准库 — 数据处理
    "json", "csv",
    # 标准库 — 日期时间
    "datetime", "calendar", "time",
    # 标准库 — 数据结构
    "collections", "heapq", "bisect", "array",
    # 标准库 — 迭代工具
    "itertools", "functools", "operator",
    # 标准库 — 类型与工具
    "typing", "dataclasses", "enum",
    # 标准库 — 数值
    "decimal", "fractions", "statistics", "random",
    # 标准库 — 文本
    "string", "re", "textwrap", "unicodedata", "difflib",
    # 标准库 — 日志（只读用途）
    "logging",
    # 标准库 — 哈希与校验
    "hashlib",
    # 标准库 — 拷贝
    "copy",
    # 常用第三方 — 数值计算
    "numpy",
    # 常用第三方 — 数据分析
    "pandas",
})

DEFAULT_BLOCKED_MODULES: frozenset[str] = frozenset({
    "os", "subprocess", "socket", "ctypes", "sys",
    "signal", "shutil", "importlib", "builtins",
    "code", "codeop", "compileall", "concurrent.futures",
    "multiprocessing", "threading",
    "pathlib", "io", "tempfile", "pickle", "shelve",
    "webbrowser", "http", "urllib", "ftplib", "smtplib",
    "xmlrpc", "socketserver",
    "pdb", "traceback", "inspect", "trace",
    "gc", "atexit",
    "tkinter", "curses",
})

DEFAULT_TIMEOUT_SECONDS: int = 30
DEFAULT_MEMORY_MB: int = 256
DEFAULT_CPU_LIMIT: int = 1
DEFAULT_MAX_OUTPUT_LENGTH: int = 10000
DEFAULT_NETWORK_DISABLED: bool = True
# 沙箱执行模式: lightweight (subprocess) / docker (容器隔离)
DEFAULT_SANDBOX_MODE: str = "lightweight"
# Docker 模式默认镜像
DEFAULT_DOCKER_IMAGE: str = "python:3.12-slim"

DEFAULT_MAX_SIZE_MB: int = 50
DEFAULT_ALLOWED_TYPES: frozenset[str] = frozenset({
    ".pdf", ".docx", ".xlsx", ".xls", ".csv", ".txt", ".md",
})
DEFAULT_SCAN_FOR_MALWARE: bool = False
DEFAULT_MAX_FILES_PER_UPLOAD: int = 10


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CodeSandboxConfig:
    """代码沙箱运行时配置."""

    allowed_modules: frozenset[str] = field(
        default_factory=lambda: DEFAULT_ALLOWED_MODULES
    )
    blocked_modules: frozenset[str] = field(
        default_factory=lambda: DEFAULT_BLOCKED_MODULES
    )
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    memory_mb: int = DEFAULT_MEMORY_MB
    cpu_limit: int = DEFAULT_CPU_LIMIT
    max_output_length: int = DEFAULT_MAX_OUTPUT_LENGTH
    network_disabled: bool = DEFAULT_NETWORK_DISABLED
    # 执行模式: lightweight / docker（可由前端配置覆盖环境变量 SANDBOX_MODE）
    mode: str = DEFAULT_SANDBOX_MODE
    # Docker 模式使用的镜像（仅 docker 模式生效）
    docker_image: str = DEFAULT_DOCKER_IMAGE


@dataclass(frozen=True)
class SqlWhitelistConfig:
    """SQL 白名单运行时配置.

    allowed_tables 为 None 表示不限制表名（保持原 SQLSandbox 默认行为）。
    """

    allowed_tables: set[str] | None = None
    forbidden_keywords: frozenset[str] = field(default_factory=frozenset)
    max_rows: int | None = None
    max_execution_time_ms: int | None = None
    allow_aggregation: bool = True


@dataclass(frozen=True)
class FileUploadConfig:
    """文件上传运行时配置."""

    max_size_mb: int = DEFAULT_MAX_SIZE_MB
    allowed_types: frozenset[str] = field(default_factory=lambda: DEFAULT_ALLOWED_TYPES)
    scan_for_malware: bool = DEFAULT_SCAN_FOR_MALWARE
    max_files_per_upload: int = DEFAULT_MAX_FILES_PER_UPLOAD


# ---------------------------------------------------------------------------
# 内存缓存（TTL 60s + 失效钩子）
# ---------------------------------------------------------------------------

_CACHE_TTL: float = 60.0
_cache: dict[tuple[str, str], tuple[dict[str, Any], float]] = {}
_cache_lock: Lock = Lock()


def invalidate_config_cache(config_type: str | None = None) -> None:
    """清除配置缓存.

    Args:
        config_type: 指定类型时仅清除该类型; None 时清除全部缓存。
    """
    with _cache_lock:
        if config_type is None:
            _cache.clear()
        else:
            stale = [k for k in _cache if k[0] == config_type]
            for key in stale:
                _cache.pop(key, None)


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


@contextmanager
def _ensure_session(db: Session | None) -> Iterator[Session]:
    """确保有一个可用的数据库会话; db 为 None 时临时创建并关闭。"""
    if db is not None:
        yield db
        return
    from finpilot.database import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """深度合并两个配置字典, override 逐键覆盖 base.

    仅对 dict 类型递归合并; list / 标量等类型直接替换（租户的列表整体覆盖系统列表）。
    """
    result: dict[str, Any] = dict(base)
    for key, val in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(val, dict)
        ):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _load_config_row(
    config_type: str,
    tenant_id: str | None,
    is_system: bool,
    db: Session,
) -> dict[str, Any]:
    """从 DB 加载单条激活配置的 config 字典, 失败 / 无记录返回空字典。"""
    try:
        from finpilot.database.models import SandboxConfig

        query = db.query(SandboxConfig).filter(
            SandboxConfig.config_type == config_type,
            SandboxConfig.is_active.is_(True),
        )
        if is_system:
            query = query.filter(SandboxConfig.is_system.is_(True))
        else:
            query = query.filter(
                SandboxConfig.is_system.is_(False),
                SandboxConfig.tenant_id == tenant_id,
            )
        # priority 越大优先级越高
        row = query.order_by(SandboxConfig.priority.desc()).first()
        if row is None:
            return {}
        return dict(row.config or {})
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "load_sandbox_config_failed",
            config_type=config_type,
            is_system=is_system,
            error=str(exc),
        )
        return {}


def _to_frozenset(val: Any, default: frozenset[str]) -> frozenset[str]:
    if val is None:
        return default
    try:
        return frozenset(str(v) for v in val)
    except TypeError:
        return default


def _to_int(val: Any, default: int) -> int:
    try:
        return int(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _to_bool(val: Any, default: bool) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "y", "on")
    return bool(val)


def _normalize_ext(ext: Any) -> str:
    """规范化扩展名为带点的小写形式, 如 'PDF' -> '.pdf'。"""
    text = str(ext).strip().lower()
    if not text:
        return ""
    if not text.startswith("."):
        text = "." + text
    return text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_sandbox_config(
    config_type: str,
    tenant_id: str,
    db: Session | None = None,
) -> dict[str, Any]:
    """加载并合并「系统默认 + 租户覆盖」的沙箱配置.

    Args:
        config_type: 配置类型 (sql_whitelist / code_sandbox / file_upload)
        tenant_id: 租户 ID
        db: 可选数据库会话, 为 None 时内部临时创建

    Returns:
        合并后的配置字典（系统基线被租户配置逐键覆盖）; 无任何配置时返回空字典。
    """
    cache_key = (config_type, str(tenant_id))
    now = time.monotonic()

    with _cache_lock:
        cached = _cache.get(cache_key)
        if cached is not None:
            value, expires_at = cached
            if now < expires_at:
                return value

    with _ensure_session(db) as session:
        system_cfg = _load_config_row(config_type, None, True, session)
        tenant_cfg = _load_config_row(config_type, str(tenant_id), False, session)

    merged = _deep_merge(system_cfg, tenant_cfg)

    with _cache_lock:
        _cache[cache_key] = (merged, now + _CACHE_TTL)
    return merged


def get_code_sandbox_config(
    tenant_id: str,
    db: Session | None = None,
) -> CodeSandboxConfig:
    """获取代码沙箱配置（合并系统默认 + 租户覆盖, 回退到硬编码默认）。"""
    cfg = get_sandbox_config("code_sandbox", tenant_id, db)
    # 兼容 max_output_chars / max_output_length 两种键名
    max_out = cfg.get("max_output_length", cfg.get("max_output_chars"))
    # 执行模式: 优先级 DB 配置 > 环境变量 SANDBOX_MODE > 默认 lightweight
    env_mode = os.environ.get("SANDBOX_MODE", "").strip()
    cfg_mode = str(cfg.get("mode") or "").strip()
    mode = cfg_mode or env_mode or DEFAULT_SANDBOX_MODE
    if mode not in ("lightweight", "docker"):
        mode = DEFAULT_SANDBOX_MODE
    return CodeSandboxConfig(
        allowed_modules=_to_frozenset(cfg.get("allowed_modules"), DEFAULT_ALLOWED_MODULES),
        blocked_modules=_to_frozenset(cfg.get("blocked_modules"), DEFAULT_BLOCKED_MODULES),
        timeout_seconds=_to_int(cfg.get("timeout_seconds"), DEFAULT_TIMEOUT_SECONDS),
        memory_mb=_to_int(cfg.get("memory_mb"), DEFAULT_MEMORY_MB),
        cpu_limit=_to_int(cfg.get("cpu_limit"), DEFAULT_CPU_LIMIT),
        max_output_length=_to_int(max_out, DEFAULT_MAX_OUTPUT_LENGTH),
        network_disabled=_to_bool(cfg.get("network_disabled"), DEFAULT_NETWORK_DISABLED),
        mode=mode,
        docker_image=str(cfg.get("docker_image") or DEFAULT_DOCKER_IMAGE),
    )


def get_sql_whitelist_config(
    tenant_id: str,
    db: Session | None = None,
) -> SqlWhitelistConfig:
    """获取 SQL 白名单配置（合并系统默认 + 租户覆盖, 回退到运行时默认）。

    无 DB 配置时保持原 SQLSandbox 行为: 不限制表名、不注入 LIMIT、允许聚合。
    """
    cfg = get_sandbox_config("sql_whitelist", tenant_id, db)
    tables_raw = cfg.get("tables", cfg.get("allowed_tables"))
    allowed_tables = set(str(t) for t in tables_raw) if tables_raw else None
    forbidden = cfg.get("forbidden_keywords")
    return SqlWhitelistConfig(
        allowed_tables=allowed_tables,
        forbidden_keywords=(
            frozenset(str(k).upper() for k in forbidden) if forbidden else frozenset()
        ),
        max_rows=_to_int(cfg.get("max_rows"), 0) or None,
        max_execution_time_ms=_to_int(cfg.get("max_execution_time_ms"), 0) or None,
        allow_aggregation=_to_bool(cfg.get("allow_aggregation"), True),
    )


def get_file_upload_config(
    tenant_id: str,
    db: Session | None = None,
) -> FileUploadConfig:
    """获取文件上传配置（合并系统默认 + 租户覆盖, 回退到硬编码默认）。"""
    cfg = get_sandbox_config("file_upload", tenant_id, db)
    types_raw = cfg.get("allowed_types")
    if types_raw:
        allowed = frozenset(
            t for t in (_normalize_ext(x) for x in types_raw) if t
        ) or DEFAULT_ALLOWED_TYPES
    else:
        allowed = DEFAULT_ALLOWED_TYPES
    return FileUploadConfig(
        max_size_mb=_to_int(cfg.get("max_size_mb"), DEFAULT_MAX_SIZE_MB),
        allowed_types=allowed,
        scan_for_malware=_to_bool(cfg.get("scan_for_malware"), DEFAULT_SCAN_FOR_MALWARE),
        max_files_per_upload=_to_int(
            cfg.get("max_files_per_upload"), DEFAULT_MAX_FILES_PER_UPLOAD
        ),
    )
