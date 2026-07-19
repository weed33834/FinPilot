"""Audit logging -- best-effort SQLite writes that never break the main flow.

Single-machine SQLite edition.

Core constraints:
- Auditing is a side-channel; write failures MUST be swallowed silently. A
  single LLM call must never fail because auditing errored.
- PII-mask `detail` before persisting (reuses security.pii), never store
  plaintext sensitive info.
- Does not depend on the FastAPI request context, so it can be called directly
  from low-level code like LLMClient.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .pii import mask_pii

logger = logging.getLogger(__name__)


def record_event(
    action: str,
    *,
    detail: str | None = None,
    status: str = "ok",
    tenant_id: str | None = None,
    user_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    """Write one audit event (best-effort).

    Args:
        action: event type, e.g. ``llm_call`` / ``injection_blocked``.
        detail: plaintext description; auto PII-masked before persisting.
        status: ``ok`` / ``blocked`` / ``error``.
        tenant_id / user_id: subject identifiers; None when missing.
        meta: structured metadata (model name, latency, threat score, ...),
            serialized to JSON.
    """
    try:
        # Lazy import avoids a circular dependency with the database package and
        # lets this module import cleanly even without a DB configured.
        from finpilot.database.connection import SessionLocal
        from finpilot.database.models import AuditLog

        masked = mask_pii(detail) if detail else None
        meta_json = json.dumps(meta, ensure_ascii=False) if meta else None

        db = SessionLocal()
        try:
            db.add(
                AuditLog(
                    action=action,
                    status=status,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    detail=masked,
                    meta_json=meta_json,
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        # Audit failure must not block the business; degrade to local logging.
        logger.warning("audit_record_failed action=%s err=%s", action, exc)


__all__ = ["record_event"]
