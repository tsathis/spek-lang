"""AST nodes for spek."""

from dataclasses import dataclass, field


@dataclass
class Signature:
    name: str
    params: list
    outcomes: list
    line: int


@dataclass
class Example:
    inputs: list
    outcome: str
    line: int


@dataclass
class Effect:
    name: str
    line: int


@dataclass
class Hatch:
    text: str
    line: int


@dataclass
class Note:
    text: str
    line: int


@dataclass
class Spec:
    sig: Signature
    examples: list = field(default_factory=list)
    effects: list = field(default_factory=list)
    hatches: list = field(default_factory=list)
    notes: list = field(default_factory=list)


@dataclass
class Module:
    specs: list = field(default_factory=list)
