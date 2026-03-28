"""The parsed form of a .spek file.

Four node kinds, matching the four rules of the language: a signature, and
body lines that are effects, examples, or hatches. Nothing else is ever added
here -- every extra node type is a step toward a general-purpose language.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Example outcome alias that always resolves to the first declared outcome.
SUCCESS_ALIAS = "ok"


@dataclass(frozen=True)
class Span:
    line: int
    col: int

    def as_dict(self) -> dict[str, int]:
        return {"line": self.line, "col": self.col}


# --- literals ---------------------------------------------------------------


@dataclass(frozen=True)
class Literal:
    """Base for the values an example can carry."""


@dataclass(frozen=True)
class Str(Literal):
    value: str


@dataclass(frozen=True)
class Num(Literal):
    value: int | float


@dataclass(frozen=True)
class Bool(Literal):
    value: bool


@dataclass(frozen=True)
class Null(Literal):
    pass


@dataclass(frozen=True)
class Sym(Literal):
    """A bare word standing for a fixture the author binds elsewhere.

    `known`, `timeout`, `after_expire` -- the language deliberately has no way
    to describe what they are. That belongs in the fixtures file, where it is
    ordinary Python.
    """

    name: str


@dataclass(frozen=True)
class Named(Literal):
    """`name=value`. Binds a parameter by name, or supplies setup state."""

    name: str
    value: Literal


def literal_repr(lit: Literal) -> str:
    """Render a literal back into spec syntax (used in diagnostics)."""
    if isinstance(lit, Str):
        return f'"{lit.value}"'
    if isinstance(lit, Num):
        return str(lit.value)
    if isinstance(lit, Bool):
        return "true" if lit.value else "false"
    if isinstance(lit, Null):
        return "null"
    if isinstance(lit, Sym):
        return lit.name
    if isinstance(lit, Named):
        return f"{lit.name}={literal_repr(lit.value)}"
    raise TypeError(f"unknown literal {lit!r}")


# --- body lines -------------------------------------------------------------


@dataclass(frozen=True)
class Effect:
    tag: str
    span: Span


@dataclass(frozen=True)
class Example:
    """One input/outcome pair.

    `outcome` is always resolved to a declared outcome name (`ok` expanded).
    `expect` is set when the example pinned an exact return value rather than
    just naming the outcome.
    """

    inputs: tuple[Literal, ...]
    outcome: str
    expect: Literal | None
    span: Span

    @property
    def positional(self) -> tuple[Literal, ...]:
        return tuple(i for i in self.inputs if not isinstance(i, Named))

    @property
    def named(self) -> tuple[Named, ...]:
        return tuple(i for i in self.inputs if isinstance(i, Named))


@dataclass(frozen=True)
class Hatch:
    """An unverified property. The count of these is the triage signal."""

    text: str
    span: Span


@dataclass(frozen=True)
class Note:
    """Optional guidance, chiefly for whoever writes the implementation.

    A note is advisory and nothing ever checks it -- that is the whole
    difference from a hatch, which states a requirement that merely happens to
    be unverifiable. A note can never fail a build.
    """

    text: str
    span: Span


# --- spec -------------------------------------------------------------------


@dataclass(frozen=True)
class Signature:
    name: str
    params: tuple[str, ...]
    outcomes: tuple[str, ...]
    span: Span

    @property
    def success(self) -> str:
        return self.outcomes[0]

    @property
    def failures(self) -> tuple[str, ...]:
        return self.outcomes[1:]


@dataclass(frozen=True)
class Spec:
    signature: Signature
    effects: tuple[Effect, ...] = ()
    examples: tuple[Example, ...] = ()
    hatches: tuple[Hatch, ...] = ()
    notes: tuple[Note, ...] = ()
    file: str | None = None

    @property
    def name(self) -> str:
        return self.signature.name

    @property
    def effect_tags(self) -> tuple[str, ...]:
        return tuple(e.tag for e in self.effects)

    @property
    def symbols(self) -> tuple[str, ...]:
        """Every fixture name the examples refer to, in first-seen order."""
        seen: dict[str, None] = {}
        for example in self.examples:
            for lit in example.inputs:
                inner = lit.value if isinstance(lit, Named) else lit
                if isinstance(inner, Sym):
                    seen.setdefault(inner.name, None)
            if isinstance(example.expect, Sym):
                seen.setdefault(example.expect.name, None)
        return tuple(seen)

    @property
    def body_lines(self) -> int:
        """Physical lines that carry verification.

        Counted by source line, not by item: `!db !hash` is two effects but one
        line, and the budget exists to measure what a reviewer's eye actually
        traverses. Notes are guidance, so they sit outside this budget and are
        counted separately.
        """
        lines = {effect.span.line for effect in self.effects}
        lines.update(example.span.line for example in self.examples)
        lines.update(hatch.span.line for hatch in self.hatches)
        return len(lines)

    @property
    def note_lines(self) -> int:
        return len({note.span.line for note in self.notes})

    def python_name(self) -> str:
        """Last segment of a possibly dotted name: `cache.get` -> `get`."""
        return self.signature.name.rsplit(".", 1)[-1]

    def python_owner(self) -> str | None:
        """Owning class for a dotted name: `cache.get` -> `cache`."""
        if "." not in self.signature.name:
            return None
        return self.signature.name.rsplit(".", 1)[0]


@dataclass(frozen=True)
class SpecFile:
    """One `.spek` file: an ordered list of specs."""

    specs: tuple[Spec, ...]
    path: str | None = None
    source: str = field(default="", repr=False)

    def __iter__(self):
        return iter(self.specs)

    def __len__(self) -> int:
        return len(self.specs)

    def get(self, name: str) -> Spec | None:
        for spec in self.specs:
            if spec.name == name:
                return spec
        return None
