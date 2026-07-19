"""PII masking -- regex rule patterns (zero-dependency, runs on a single machine).

Purpose: mask PII (email, phone, ID card, bank card, IP) in text before it is
persisted to audit logs or debug logs, so sensitive data never lands in
plaintext.

Design trade-offs:
- Regex only; no spacy / Presidio NLP deps, so startup never blocks on model
  downloads.
- Order matters: mask the longer / more specific entities first (18-digit ID
  card, 16-19 digit bank card), then the shorter patterns that may overlap,
  so the bank-card rule does not steal the leading digits of an ID card.
- The body sent to the LLM is NOT masked (it would lose context needed for the
  answer); masking is for side-channel retention only.
"""

from __future__ import annotations

import re

# Order is priority: earlier entries are replaced first. Long/specific entities
# go first to avoid being truncated by shorter patterns.
# The 18-digit ID card comes before the bank card (16-19 digits), otherwise
# \d{16,19} would consume the first 16-18 digits of the ID card.
_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")),
    # Mainland China ID card: 18 digits (17 + check digit 0-9/X) or legacy 15 digits
    ("ID_CARD", re.compile(r"\b\d{17}[\dXx]\b|\b\d{15}\b")),
    # Bank card: 16-19 consecutive digits (placed after the ID card)
    ("BANK_CARD", re.compile(r"\b\d{16,19}\b")),
    # Mainland China mobile: starts with 1, second digit 3-9, 11 digits total
    ("PHONE", re.compile(r"\b1[3-9]\d{9}\b")),
    ("IP_ADDRESS", re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")),
]


def mask_pii(text: str) -> str:
    """Mask PII in text, replacing entities with ``<ENTITY_TYPE>``.

    Non-strings / empty strings are returned as-is so callers need no pre-check.
    """
    if not text:
        return text
    result = text
    for entity_type, pattern in _PII_PATTERNS:
        result = pattern.sub(f"<{entity_type}>", result)
    return result


def has_pii(text: str) -> bool:
    """Fast check whether text contains any PII category."""
    if not text:
        return False
    return any(pattern.search(text) for _t, pattern in _PII_PATTERNS)


def detect_pii(text: str) -> dict[str, int]:
    """Count PII hits per category, for audit alerts / risk scoring.

    Returns:
        A dict like ``{"EMAIL": 1, "PHONE": 2}``; empty dict when nothing hits.
    """
    if not text:
        return {}
    counts: dict[str, int] = {}
    for entity_type, pattern in _PII_PATTERNS:
        n = len(pattern.findall(text))
        if n:
            counts[entity_type] = n
    return counts


__all__ = ["mask_pii", "has_pii", "detect_pii"]
