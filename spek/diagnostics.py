"""Structured diagnostics with stable codes.

Every problem spek reports is a `Diagnostic`. Codes are stable across releases
so that an agent's retry loop can branch on them without parsing prose.

Code ranges:
    E0xx  lexical / syntax
    E1xx  effects
    E2xx  examples and the spec/implementation interface
    W3xx  spec lint (advisory; never fails `verify` on its own)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


# --- lexical / syntax -------------------------------------------------------
E_UNTERMINATED_STRING = "E001"
E_UNEXPECTED_CHAR = "E002"
E_EXPECTED_TOKEN = "E003"
E_NO_SIGNATURE = "E004"
E_BODY_NOT_INDENTED = "E005"
E_EMPTY_HATCH = "E006"
E_EMPTY_NOTE = "E007"

# --- effects ----------------------------------------------------------------
E_UNDECLARED_EFFECT = "E101"
E_DUPLICATE_EFFECT = "E102"
E_EFFECT_NOT_IMPLEMENTED = "E103"
W_UNUSED_EFFECT = "W301"
W_UNKNOWN_EFFECT = "W302"
W_UNDECLARED_HEURISTIC = "W308"

# --- examples / interface ---------------------------------------------------
E_DUPLICATE_OUTCOME = "E201"
E_UNKNOWN_OUTCOME = "E202"
E_ARITY_MISMATCH = "E203"
E_TARGET_NOT_FOUND = "E204"
E_UNBOUND_SYMBOL = "E205"
E_EXAMPLE_FAILED = "E206"
E_IMPL_SYNTAX = "E207"
E_PARAM_BOUND_TWICE = "E208"

# --- lint -------------------------------------------------------------------
W_NO_EXAMPLES = "W303"
W_OUTCOME_UNEXERCISED = "W304"
W_HATCH_HEAVY = "W305"
W_OVER_BUDGET = "W306"
W_DUPLICATE_EXAMPLE = "W307"
W_TOO_MANY_NOTES = "W309"


@dataclass(frozen=True)
class Diagnostic:
    """One machine-readable finding.

    `symbol` names the thing at fault (an effect tag, an outcome, a callee)
    so a repair loop can act without re-deriving it from `message`.
    """

    code: str
    severity: Severity
    message: str
    file: str | None = None
    line: int | None = None
    col: int | None = None
    symbol: str | None = None
    fix: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_error(self) -> bool:
        return self.severity is Severity.ERROR

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
        }
        for key in ("file", "line", "col", "symbol", "fix"):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        if self.extra:
            out["extra"] = dict(self.extra)
        return out

    def render(self) -> str:
        where = self.file or "<spec>"
        if self.line is not None:
            where += f":{self.line}"
            if self.col is not None:
                where += f":{self.col}"
        text = f"{where}: {self.severity.value} {self.code}: {self.message}"
        if self.fix:
            text += f"\n    fix: {self.fix}"
        return text


def error(code: str, message: str, **kwargs: Any) -> Diagnostic:
    return Diagnostic(code=code, severity=Severity.ERROR, message=message, **kwargs)


def warning(code: str, message: str, **kwargs: Any) -> Diagnostic:
    return Diagnostic(code=code, severity=Severity.WARNING, message=message, **kwargs)


def to_json(diagnostics: list[Diagnostic], **payload: Any) -> str:
    body = {"diagnostics": [d.to_dict() for d in diagnostics], **payload}
    return json.dumps(body, indent=2, sort_keys=False)


def has_errors(diagnostics: list[Diagnostic]) -> bool:
    return any(d.is_error for d in diagnostics)


class SpekError(Exception):
    """Raised when spek cannot continue; carries the diagnostics explaining why."""

    def __init__(self, diagnostics: list[Diagnostic]):
        self.diagnostics = diagnostics
        super().__init__("; ".join(d.message for d in diagnostics) or "spek error")
