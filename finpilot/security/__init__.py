"""finpilot security package.

- pii:       PII masking (regex, zero-dependency)
- injection: prompt-injection protection (rule edition, optional promptshield upgrade)
- audit:     audit logging (best-effort SQLite writes)
- guard:     unified facade mounted around LLMClient calls
- totp:      TOTP/MFA helpers (pyotp)
- abac:      attribute-based access control engine
"""

from .pii import mask_pii, has_pii, detect_pii
from .injection import injection_guard, InjectionGuard, InjectionResult
from .audit import record_event
from .guard import guard_llm_call, InjectionBlockedError
from .totp import (
    generate_secret, provisioning_uri, verify_totp,
    generate_backup_codes, hash_backup_code, verify_backup_code, build_qr_svg,
)
from .abac import ABACEngine, Subject, Policy

__all__ = [
    "mask_pii",
    "has_pii",
    "detect_pii",
    "injection_guard",
    "InjectionGuard",
    "InjectionResult",
    "record_event",
    "guard_llm_call",
    "InjectionBlockedError",
    # TOTP/MFA
    "generate_secret",
    "provisioning_uri",
    "verify_totp",
    "generate_backup_codes",
    "hash_backup_code",
    "verify_backup_code",
    "build_qr_svg",
    # ABAC
    "ABACEngine",
    "Subject",
    "Policy",
]
