"""The effect vocabulary, shared by every target language.

Tags are free-form in the grammar -- `!whatever` parses. This table is the set
spek can actually *check*, and an unknown tag is warned about precisely
because it documents without verifying.

`CERTAIN` effects are read off imports and calls, so an undeclared one is an
error. `HEURISTIC` effects are inferred from shape rather than from a name, so
an undeclared one is only a warning: the analysis is allowed to be wrong.
"""

from __future__ import annotations

from enum import Enum


class EffectKind(str, Enum):
    CERTAIN = "certain"
    HEURISTIC = "heuristic"


#: tag -> (kind, one-line meaning)
EFFECTS: dict[str, tuple[EffectKind, str]] = {
    "net": (EffectKind.CERTAIN, "talks to the network"),
    "fs": (EffectKind.CERTAIN, "reads or writes the filesystem"),
    "db": (EffectKind.CERTAIN, "reads or writes a database"),
    "proc": (EffectKind.CERTAIN, "starts processes or signals them"),
    "env": (EffectKind.CERTAIN, "reads or writes process environment"),
    "clock": (EffectKind.CERTAIN, "reads wall-clock time or sleeps"),
    "rand": (EffectKind.CERTAIN, "consumes randomness"),
    "hash": (EffectKind.CERTAIN, "hashes or encrypts"),
    "io": (EffectKind.CERTAIN, "reads or writes the console"),
    "ai": (EffectKind.CERTAIN, "calls a model"),
    "mem": (EffectKind.HEURISTIC, "keeps state between calls"),
}

KNOWN_EFFECTS: frozenset[str] = frozenset(EFFECTS)

CERTAIN_EFFECTS: frozenset[str] = frozenset(
    tag for tag, (kind, _) in EFFECTS.items() if kind is EffectKind.CERTAIN
)


def kind_of(tag: str) -> EffectKind | None:
    entry = EFFECTS.get(tag)
    return entry[0] if entry else None


def describe(tag: str) -> str:
    entry = EFFECTS.get(tag)
    return entry[1] if entry else "unrecognised effect"
