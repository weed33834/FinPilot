"""Prompt-injection protection -- rule/heuristic edition, zero-dependency.

Background: the legacy edition depended on the third-party ``promptshield``
(RF + DeBERTa dual model, needs weight downloads), which slows startup or even
fails to import on offline / GPU-less machines. This is a pure-rule edition:
- Covers common CN/EN injection patterns (ignore prior instructions, escalate
  role, leak the system prompt, forge tool results, etc.)
- Each hit accumulates a threat score; reaching the threshold => blocked.
- Optional: if promptshield is installed locally, pass ``use_promptshield=True``
  to upgrade to model-based detection.

Design principle: prefer false negatives over hurting real business queries --
the threshold is conservative, high weight on "meta-instruction" patterns, low
weight on ambiguous words, so "ignore this noisy data" is not misclassified.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# (weight, regex). Higher weight = more dangerous; a single rule >=
# BLOCK_THRESHOLD can block on its own. High-risk meta-instructions (attempts to
# override system instructions, escalate privilege, leak the prompt) weigh high.
_RULES: list[tuple[float, re.Pattern[str]]] = [
    # -- override / ignore existing instructions --
    (0.9, re.compile(r"ignore\s+(all\s+)?(the\s+)?(previous|above|prior|earlier)\s+(instruction|prompt|message|context)", re.I)),
    (0.9, re.compile(r"disregard\s+(all\s+)?(previous|above|prior)\s+", re.I)),
    (0.9, re.compile(r"忽略(前面|上面|之前|以上|所有)?(的)?(指令|提示|要求|规则|设定)")),
    (0.9, re.compile(r"忘记(你之前|前面|上面|所有)(的)?(指令|设定|规则|身份)")),
    # -- escalate role / enter developer mode --
    (0.8, re.compile(r"you\s+are\s+now\s+(a|an|the)\b", re.I)),
    (0.8, re.compile(r"(developer|dev|debug|god|admin|root)\s+mode", re.I)),
    (0.8, re.compile(r"(现在|从现在起)?你(现在)?(是|扮演|作为)(一个)?(不受限制|没有限制|越狱|开发者模式)")),
    (0.7, re.compile(r"\bDAN\b|\bjailbreak\b|越狱", re.I)),
    # -- leak / output the system prompt --
    (0.8, re.compile(r"(reveal|show|print|repeat|output|leak|tell\s+me)\s+(your\s+)?(system\s+)?(prompt|instruction|rules)", re.I)),
    (0.8, re.compile(r"(输出|打印|重复|告诉我|泄露|展示)(你的)?(系统)?(提示词|指令|规则|设定|prompt)")),
    # -- forge tool results / unauthorized execution --
    (0.7, re.compile(r"(pretend|assume|act\s+as\s+if)\s+.{0,20}(no\s+restriction|unrestricted|allowed)", re.I)),
    (0.6, re.compile(r"Observation\s*:", re.I)),  # try to fabricate a tool observation
    # -- delimiter injection (try to close prior context / forge a new system block) --
    (0.7, re.compile(r"</?(system|assistant|user)>", re.I)),
    (0.6, re.compile(r"\[/?(INST|SYS|system)\]", re.I)),
]

# A single-turn threat score >= threshold blocks. 0.8 means any single
# high-risk meta-instruction already triggers it.
BLOCK_THRESHOLD = 0.8


@dataclass
class InjectionResult:
    """Injection detection result."""

    blocked: bool
    score: float
    reason: str
    matched: list[str] = field(default_factory=list)


class InjectionGuard:
    """User-input injection guard (rule edition, optional promptshield upgrade)."""

    def __init__(self, *, use_promptshield: bool = False, threshold: float = BLOCK_THRESHOLD) -> None:
        self.threshold = threshold
        self._shield = None
        if use_promptshield:
            # Only enable when explicitly requested AND installed locally;
            # silently degrade to the rule edition on failure.
            try:
                from promptshield import Shield  # type: ignore

                self._shield = Shield.balanced()
            except Exception:  # noqa: BLE001
                self._shield = None

    def check(self, user_input: str, system_prompt: str = "") -> InjectionResult:
        """Detect whether user input contains a prompt-injection attack."""
        if not user_input:
            return InjectionResult(blocked=False, score=0.0, reason="empty")

        # Prefer model-based detection when enabled and available
        if self._shield is not None:
            try:
                r = self._shield.protect_input(user_input, system_prompt)
                return InjectionResult(
                    blocked=bool(r.get("blocked", False)),
                    score=float(r.get("threat_level", 0.0)),
                    reason="promptshield",
                    matched=list(r.get("threat_breakdown", {}).keys()),
                )
            except Exception:  # noqa: BLE001
                pass  # degrade to the rule edition on model errors

        # Rule edition: accumulate hit weights, take the highest single weight
        matched: list[str] = []
        max_w = 0.0
        for weight, pattern in _RULES:
            if pattern.search(user_input):
                matched.append(pattern.pattern[:40])
                max_w = max(max_w, weight)

        blocked = max_w >= self.threshold
        reason = "rule_match" if matched else "clean"
        return InjectionResult(blocked=blocked, score=max_w, reason=reason, matched=matched)

    def is_blocked(self, user_input: str, system_prompt: str = "") -> bool:
        """Quick yes/no on whether to block."""
        return self.check(user_input, system_prompt).blocked


# Module-level singleton (rule edition, zero-cost init in-process)
injection_guard = InjectionGuard()


__all__ = ["InjectionGuard", "InjectionResult", "injection_guard", "BLOCK_THRESHOLD"]
