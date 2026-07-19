"""LangGraph session persistence (checkpointer) -- migrated from legacy
agent_runtime/checkpoint.py.

The legacy edition targeted PostgreSQL (PostgresSaver + connection pool).
finpilot is a single-machine SQLite architecture, so this is reworked into a
**Memory / SQLite dual backend**:

- default ``memory``: in-process MemorySaver, same behavior as current finpilot
  (lost on restart).
- ``sqlite``: SqliteSaver persisted to ~/.finpilot/checkpoints.db, so multi-turn
  dialogs survive a process restart.
- Switched via env var ``FINPILOT_CHECKPOINT_BACKEND``; defaults to memory (no
  change to existing behavior).

thread_id design follows legacy: ``"{tenant_id}:{conversation_id}"``, with the
tenant prefix as the isolation boundary; a temp UUID is generated when
conversation_id is missing (valid for the current turn only).
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import MemorySaver

# Persistence backend singleton: avoid rebuilding connections repeatedly
_saver_singleton: Any = None
_saver_backend: str | None = None

# SQLite checkpoint path (separate from the business DB, no interference)
CHECKPOINT_DB_PATH = Path.home() / ".finpilot" / "checkpoints.db"


def make_thread_id(tenant_id: str, conversation_id: str | None) -> str:
    """Build thread_id: tenant prefix + conversation ID; UUID when missing."""
    cid = conversation_id or uuid.uuid4().hex
    return f"{tenant_id}:{cid}"


def get_checkpointer() -> Any:
    """Get the checkpointer singleton (backend chosen by env, degrade to memory on failure).

    Returns:
        A langgraph BaseCheckpointSaver instance (MemorySaver or SqliteSaver).
    """
    global _saver_singleton, _saver_backend  # noqa: PLW0603

    backend = (os.getenv("FINPILOT_CHECKPOINT_BACKEND") or "memory").strip().lower()

    # Reuse if backend unchanged and already built
    if _saver_singleton is not None and _saver_backend == backend:
        return _saver_singleton

    if backend == "sqlite":
        saver = _try_sqlite()
        if saver is not None:
            _saver_singleton, _saver_backend = saver, "sqlite"
            return saver
        # degrade to memory on failure
    _saver_singleton, _saver_backend = MemorySaver(), "memory"
    return _saver_singleton


def _try_sqlite() -> Any:
    """Try building a SqliteSaver; return None on failure (caller degrades).

    Note: SqliteSaver needs a sqlite3.Connection; check_same_thread=False adapts
    to uvicorn's multithreading, and the autocommit semantics are handled by
    langgraph's setup.
    """
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
    except ImportError:
        return None
    try:
        CHECKPOINT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(CHECKPOINT_DB_PATH), check_same_thread=False)
        saver = SqliteSaver(conn)
        saver.setup()  # idempotent table creation
        return saver
    except Exception:  # noqa: BLE001
        return None


def build_run_config(tenant_id: str, conversation_id: str | None) -> dict[str, Any]:
    """Build the LangGraph invoke config (thread_id drives persistence)."""
    return {"configurable": {"thread_id": make_thread_id(tenant_id, conversation_id)}}


__all__ = ["get_checkpointer", "make_thread_id", "build_run_config", "CHECKPOINT_DB_PATH"]
