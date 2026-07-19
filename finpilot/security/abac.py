"""ABAC (attribute-based access control) policy engine -- ORM-free edition.

Migrated from legacy core/abac.py. Coexists with RBAC: RBAC does coarse
role checks, ABAC does fine-grained attribute-policy checks.

Change from legacy: legacy queried AccessPolicy from SQLAlchemy and consumed
ORM User objects directly. Here it is **storage-agnostic** -- policies arrive
as a ``Policy`` dataclass list and the subject as a ``Subject``; the engine is
pure in-memory evaluation only. The policy source (memory / SQLite / JSON
config) is decided by the caller, so it runs fine on a single machine. The
comparison logic (operators, type coercion, nested lookup) is identical to
legacy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Subject:
    """Access subject (user) attributes."""

    id: str | int = ""
    role: str = ""
    tenant_id: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class Policy:
    """A single access policy."""

    resource_type: str
    action: str
    effect: str = "allow"  # allow / deny
    conditions: dict[str, Any] | None = None
    priority: int = 100
    tenant_id: str = ""
    is_active: bool = True


class ABACEngine:
    """ABAC policy-evaluation engine (pure in-memory)."""

    OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte", "in", "nin", "contains"}

    def evaluate(
        self,
        subject: Subject,
        resource_type: str,
        action: str,
        policies: list[Policy],
        resource_attributes: dict[str, Any] | None = None,
    ) -> bool:
        """Evaluate whether the subject may perform the action on the resource.

        Rules (same as legacy):
        1. Only evaluate policies matching tenant + resource type + action + active.
        2. Stable sort by priority asc, then original order.
        3. role == "admin" is allowed by default; a deny hit rejects immediately
           (highest priority).
        4. Default deny when no allow matches.
        """
        candidates = [
            p for p in policies
            if p.is_active
            and p.tenant_id == subject.tenant_id
            and p.resource_type == resource_type
            and p.action == action
        ]
        candidates.sort(key=lambda p: p.priority)

        allowed = subject.role == "admin"
        for policy in candidates:
            if self._match_conditions(subject, resource_attributes or {}, policy.conditions):
                if policy.effect == "deny":
                    return False
                if policy.effect == "allow":
                    allowed = True
        return allowed

    def _match_conditions(
        self,
        subject: Subject,
        resource_attributes: dict[str, Any],
        conditions: dict[str, Any] | None,
    ) -> bool:
        if not conditions:
            return True
        context = self._build_context(subject, resource_attributes)
        for key, expected in conditions.items():
            actual = self._get_nested_value(context, key)
            if not self._compare(actual, expected):
                return False
        return True

    @staticmethod
    def _build_context(subject: Subject, resource_attributes: dict[str, Any]) -> dict[str, Any]:
        return {
            "user": {
                "id": subject.id,
                "role": subject.role,
                "attributes": subject.attributes or {},
            },
            "resource": resource_attributes,
        }

    @staticmethod
    def _get_nested_value(context: dict[str, Any], key: str) -> Any:
        """Get a nested value by dot-path, e.g. ``user.attributes.dept``."""
        value: Any = context
        for part in key.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return None
        return value

    def _compare(self, actual: Any, expected: Any) -> bool:
        """Compare actual vs expected; supports ``op:value`` syntax (default eq)."""
        if isinstance(expected, str) and ":" in expected:
            op, _, raw_value = expected.partition(":")
            if op in self.OPERATORS:
                return self._apply_operator(actual, op, raw_value)
        return bool(actual == expected)

    def _apply_operator(self, actual: Any, op: str, raw_value: str) -> bool:
        if op == "eq":
            return bool(actual == self._coerce(actual, raw_value))
        if op == "ne":
            return bool(actual != self._coerce(actual, raw_value))

        coerced = self._coerce_numeric(raw_value)
        actual_numeric = self._coerce_numeric(actual)
        if op == "gt":
            return bool(actual_numeric is not None and coerced is not None and actual_numeric > coerced)
        if op == "gte":
            return bool(actual_numeric is not None and coerced is not None and actual_numeric >= coerced)
        if op == "lt":
            return bool(actual_numeric is not None and coerced is not None and actual_numeric < coerced)
        if op == "lte":
            return bool(actual_numeric is not None and coerced is not None and actual_numeric <= coerced)

        values = [self._coerce(actual, v) for v in raw_value.split(",")]
        if op == "in":
            return bool(actual in values)
        if op == "nin":
            return bool(actual not in values)
        if op == "contains":
            return isinstance(actual, list) and any(v in actual for v in values)
        return False

    @staticmethod
    def _coerce(actual: Any, raw_value: str) -> Any:
        """Coerce raw_value to actual's type (bool/int/float/str)."""
        if isinstance(actual, bool):
            return raw_value.lower() in ("true", "1", "yes")
        if isinstance(actual, int):
            try:
                return int(raw_value)
            except ValueError:
                return raw_value
        if isinstance(actual, float):
            try:
                return float(raw_value)
            except ValueError:
                return raw_value
        return raw_value

    @staticmethod
    def _coerce_numeric(value: Any) -> float | int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            try:
                return float(value) if "." in value else int(value)
            except ValueError:
                return None
        return None


__all__ = ["ABACEngine", "Subject", "Policy"]
