"""Structured diagnostics."""

from dataclasses import dataclass, field
from enum import Enum


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass
class Diagnostic:
    code: str
    message: str
    line: int
    severity: Severity
    symbol: str = None


@dataclass
class DiagnosticSet:
    items: list = field(default_factory=list)

    def add(self, d):
        self.items.append(d)

    def errors(self):
        return [d for d in self.items if d.severity == Severity.ERROR]

    def warnings(self):
        return [d for d in self.items if d.severity == Severity.WARNING]

    def has_errors(self):
        return len(self.errors()) > 0
