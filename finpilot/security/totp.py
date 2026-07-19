"""TOTP two-factor auth helpers (migrated from legacy core/totp.py, config-free).

Pure functions: secret generation, otpauth URI building, code verification,
backup-code generation/verification, QR-code SVG rendering. No DB/ORM; params
carry sane defaults (legacy read them from app.config; here they are function
args + module constants, so it runs with zero config on a single machine).

Deps: pyotp, qrcode.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

import pyotp
import qrcode
import qrcode.image.svg

# -- Default params (legacy read these from settings; inlined as overridable
#    defaults here) --
DEFAULT_ISSUER = "FinPilot"
DEFAULT_DIGITS = 6
DEFAULT_STEP_SECONDS = 30
DEFAULT_WINDOW = 1  # tolerate +/-1 time window to absorb client clock drift
DEFAULT_BACKUP_CODE_COUNT = 10


def generate_secret() -> str:
    """Generate a base32-encoded TOTP secret."""
    return pyotp.random_base32()


def provisioning_uri(
    secret: str,
    username: str,
    *,
    issuer: str = DEFAULT_ISSUER,
    digits: int = DEFAULT_DIGITS,
    step_seconds: int = DEFAULT_STEP_SECONDS,
) -> str:
    """Build an otpauth:// URI for an Authenticator app to scan."""
    totp = pyotp.TOTP(secret, digits=digits, interval=step_seconds)
    return totp.provisioning_uri(name=username, issuer_name=issuer)


def verify_totp(
    secret: str,
    code: str,
    *,
    window: int = DEFAULT_WINDOW,
    digits: int = DEFAULT_DIGITS,
    step_seconds: int = DEFAULT_STEP_SECONDS,
) -> bool:
    """Verify a TOTP code; empty code fails immediately."""
    if not code:
        return False
    totp = pyotp.TOTP(secret, digits=digits, interval=step_seconds)
    return bool(totp.verify(code, valid_window=window))


def generate_backup_codes(count: int = DEFAULT_BACKUP_CODE_COUNT) -> list[str]:
    """Generate `count` one-time backup codes, formatted XXXX-XXXX (uppercase hex)."""
    codes: list[str] = []
    for _ in range(count):
        raw = secrets.token_hex(4).upper()
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


def hash_backup_code(code: str) -> str:
    """sha256 a backup code; verification ignores case and hyphens."""
    normalized = code.strip().upper().replace("-", "")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def verify_backup_code(code: str, hashed_codes: list[str]) -> bool:
    """Check whether a backup code hits the stored hash list.

    Scans all entries (no short-circuit); each compare uses
    ``hmac.compare_digest`` to resist timing side-channels.
    """
    if not code:
        return False
    candidate = hash_backup_code(code)
    matched = False
    for stored in hashed_codes:
        if hmac.compare_digest(candidate, stored):
            matched = True
    return matched


def build_qr_svg(uri: str) -> str:
    """Render an otpauth URI to an SVG string (embeddable in the frontend)."""
    factory = qrcode.image.svg.SvgPathImage
    img = qrcode.make(uri, image_factory=factory)
    return img.to_string().decode("utf-8")  # type: ignore[no-any-return]


__all__ = [
    "generate_secret",
    "provisioning_uri",
    "verify_totp",
    "generate_backup_codes",
    "hash_backup_code",
    "verify_backup_code",
    "build_qr_svg",
]
