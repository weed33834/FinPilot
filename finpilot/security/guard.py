"""Security facade mounted around LLMClient calls (before/after).

Composes prompt-injection detection (injection) + audit logging (audit) +
PII masking (pii). Controlled by env switches, enabled by default but
"soft-failing" so it never breaks the existing call chain:

- FINPILOT_SECURITY_ENABLED=0  -> disable all security hooks (legacy behavior)
- FINPILOT_INJECTION_BLOCK=0   -> audit/alert only, do not actually block (observe mode)
- FINPILOT_AUDIT_ENABLED=0     -> disable audit persistence

Design: guard_llm_call is the single entry point. It raises
InjectionBlockedError when a high-risk injection is detected AND blocking is
on; otherwise it returns and the main flow continues. Auditing is always
best-effort.
"""

from __future__ import annotations

import os

from .audit import record_event
from .injection import injection_guard


class InjectionBlockedError(Exception):
    """Raised when a prompt injection is detected while in blocking mode."""

    def __init__(self, reason: str, score: float, matched: list[str]) -> None:
        self.reason = reason
        self.score = score
        self.matched = matched
        super().__init__(f"Prompt injection attack detected (threat score {score:.2f}); request blocked")


def _flag(name: str, default: bool = True) -> bool:
    """Read a boolean env var; fall back to `default`. '0'/'false'/'no'/'off'/'' -> False."""
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() not in ("0", "false", "no", "off", "")


def guard_llm_call(
    system_prompt: str,
    user_prompt: str,
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
    model_name: str | None = None,
) -> None:
    """Run security checks before an LLM call: injection detection + audit.

    Raises InjectionBlockedError on a blocked high-risk injection; otherwise
    returns normally. Audit writes are best-effort and never raise.
    """
    if not _flag("FINPILOT_SECURITY_ENABLED"):
        return

    result = injection_guard.check(user_prompt, system_prompt)

    if result.blocked:
        block_enabled = _flag("FINPILOT_INJECTION_BLOCK")
        if _flag("FINPILOT_AUDIT_ENABLED"):
            record_event(
                "injection_blocked" if block_enabled else "injection_detected",
                detail=user_prompt,
                status="blocked" if block_enabled else "ok",
                tenant_id=tenant_id,
                user_id=user_id,
                meta={"score": result.score, "matched": result.matched, "model": model_name},
            )
        if block_enabled:
            raise InjectionBlockedError(result.reason, result.score, result.matched)
        return

    # Normal calls are also logged (useful for call-volume stats & compliance tracing)
    if _flag("FINPILOT_AUDIT_ENABLED"):
        record_event(
            "llm_call",
            detail=user_prompt,
            status="ok",
            tenant_id=tenant_id,
            user_id=user_id,
            meta={"model": model_name},
        )


__all__ = ["guard_llm_call", "InjectionBlockedError"]
