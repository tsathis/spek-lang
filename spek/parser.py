"""Recursive-descent parser for .spek files.

Line shape decides the rule, which keeps the whole grammar LL(1) at the line
level and preserves the option of per-state logit masks for constrained
decoding:

    column 0   signature      name(params) -> a | b | c
    indented   `!`  effect    !db !hash
               `?`  hatch     ? retries 3x with backoff
               `:`  note      : reuse the retry helper in utils.py
               else example   (known, right) ok

Parsing never raises on bad input: it records a diagnostic, skips the line and
carries on, so one typo does not hide the rest of the file.
"""

from __future__ import annotations

from .diagnostics import (
    E_EMPTY_HATCH,
    E_EMPTY_NOTE,
    E_EXPECTED_TOKEN,
    E_NO_SIGNATURE,
    E_UNKNOWN_OUTCOME,
    Diagnostic,
    error,
)
from .lexer import T, Token, scan
from .spec_ast import (
    SUCCESS_ALIAS,
    Bool,
    Effect,
    Example,
    Hatch,
    Literal,
    Named,
    Note,
    Null,
    Num,
    Signature,
    Span,
    Spec,
    SpecFile,
    Str,
    Sym,
)


class _Builder:
    """Accumulates the body lines of one spec."""

    def __init__(self, signature: Signature, file: str | None):
        self.signature = signature
        self.file = file
        self.effects: list[Effect] = []
        self.examples: list[Example] = []
        self.hatches: list[Hatch] = []
        self.notes: list[Note] = []

    def build(self) -> Spec:
        return Spec(
            signature=self.signature,
            effects=tuple(self.effects),
            examples=tuple(self.examples),
            hatches=tuple(self.hatches),
            notes=tuple(self.notes),
            file=self.file,
        )


def parse(source: str, file: str | None = None) -> tuple[SpecFile, list[Diagnostic]]:
    """Parse a whole `.spek` file."""
    diags: list[Diagnostic] = []
    specs: list[Spec] = []
    current: _Builder | None = None

    for lineno, raw in enumerate(source.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indented = raw[0] in " \t"

        if not indented:
            if current is not None:
                specs.append(current.build())
                current = None
            signature, sig_diags = _parse_signature(raw, lineno, file)
            diags.extend(sig_diags)
            if signature is not None:
                current = _Builder(signature, file)
            continue

        if current is None:
            diags.append(
                error(
                    E_NO_SIGNATURE,
                    "body line before any signature",
                    file=file,
                    line=lineno,
                    col=1,
                    fix="start the spec with `name(params) -> outcome | ...` at column 0",
                )
            )
            continue

        diags.extend(_parse_body_line(raw, lineno, file, current))

    if current is not None:
        specs.append(current.build())

    if not specs and not diags:
        diags.append(
            error(
                E_NO_SIGNATURE,
                "no spec found",
                file=file,
                fix="a spec starts with `name(params) -> outcome | ...`",
            )
        )

    return SpecFile(specs=tuple(specs), path=file, source=source), diags


# --- signature --------------------------------------------------------------


def _parse_signature(
    raw: str, lineno: int, file: str | None
) -> tuple[Signature | None, list[Diagnostic]]:
    tokens, diags = scan(raw, lineno, file)
    if not tokens:
        return None, diags

    cursor = _Cursor(tokens, file)
    name_tok = cursor.expect(T.IDENT, "function name")
    if name_tok is None:
        return None, diags + cursor.diags
    if cursor.expect(T.LPAREN, "'(' after the name") is None:
        return None, diags + cursor.diags

    params: list[str] = []
    if not cursor.at(T.RPAREN):
        while True:
            param = cursor.expect(T.IDENT, "parameter name")
            if param is None:
                return None, diags + cursor.diags
            params.append(param.text)
            if not cursor.take(T.COMMA):
                break
    if cursor.expect(T.RPAREN, "')' to close the parameter list") is None:
        return None, diags + cursor.diags
    if cursor.expect(T.ARROW, "'->' before the outcomes") is None:
        return None, diags + cursor.diags

    outcomes: list[str] = []
    while True:
        outcome = cursor.expect(T.IDENT, "outcome name")
        if outcome is None:
            return None, diags + cursor.diags
        outcomes.append(outcome.text)
        if not cursor.take(T.PIPE):
            break

    cursor.expect_end("end of the signature")

    signature = Signature(
        name=name_tok.text,
        params=tuple(params),
        outcomes=tuple(outcomes),
        span=Span(lineno, name_tok.col),
    )
    return signature, diags + cursor.diags


# --- body lines -------------------------------------------------------------


def _parse_body_line(
    raw: str, lineno: int, file: str | None, builder: _Builder
) -> list[Diagnostic]:
    stripped = raw.strip()
    col = len(raw) - len(raw.lstrip()) + 1

    if stripped.startswith("?"):
        text = stripped[1:].strip()
        if not text:
            return [
                error(
                    E_EMPTY_HATCH,
                    "empty hatch",
                    file=file,
                    line=lineno,
                    col=col,
                    fix="write the property the tests cannot check, e.g. `? atomic`",
                )
            ]
        builder.hatches.append(Hatch(text=text, span=Span(lineno, col)))
        return []

    if stripped.startswith(":"):
        text = stripped[1:].strip()
        if not text:
            return [
                error(
                    E_EMPTY_NOTE,
                    "empty note",
                    file=file,
                    line=lineno,
                    col=col,
                    fix="write the guidance, e.g. `: reuse the retry helper in utils.py`",
                )
            ]
        builder.notes.append(Note(text=text, span=Span(lineno, col)))
        return []

    if stripped.startswith("!"):
        return _parse_effect_line(raw, lineno, file, builder)

    return _parse_example_line(raw, lineno, file, builder)


def _parse_effect_line(
    raw: str, lineno: int, file: str | None, builder: _Builder
) -> list[Diagnostic]:
    tokens, diags = scan(raw, lineno, file)
    cursor = _Cursor(tokens, file)
    while cursor.take(T.BANG):
        tag = cursor.expect(T.IDENT, "effect tag after '!'")
        if tag is None:
            break
        builder.effects.append(Effect(tag=tag.text, span=Span(lineno, tag.col - 1)))
    cursor.expect_end("end of the effect line")
    return diags + cursor.diags


def _parse_example_line(
    raw: str, lineno: int, file: str | None, builder: _Builder
) -> list[Diagnostic]:
    tokens, diags = scan(raw, lineno, file)
    if not tokens:
        return diags

    signature = builder.signature
    cursor = _Cursor(tokens, file)
    span = Span(lineno, tokens[0].col)

    # A lone trailer is the zero-argument form: `ok`.
    if len(tokens) == 1:
        inputs: list[Literal] = []
        trailer = tokens[0]
    else:
        inputs, input_diags = _parse_inputs(cursor)
        diags.extend(input_diags)
        remaining = cursor.rest()
        if len(remaining) != 1:
            hint = (
                "wrap multiple inputs in parentheses: `(a, b) outcome`"
                if len(remaining) > 1
                else "an example is `input outcome`"
            )
            diags.append(
                error(
                    E_EXPECTED_TOKEN,
                    "an example needs exactly one outcome after its input",
                    file=file,
                    line=lineno,
                    col=(remaining[0].col if remaining else tokens[-1].col),
                    fix=hint,
                )
            )
            return diags
        trailer = remaining[0]

    outcome, expect, trailer_diags = _resolve_trailer(trailer, signature, file)
    diags.extend(trailer_diags)
    if outcome is None:
        return diags

    builder.examples.append(
        Example(inputs=tuple(inputs), outcome=outcome, expect=expect, span=span)
    )
    return diags


def _parse_inputs(cursor: _Cursor) -> tuple[list[Literal], list[Diagnostic]]:
    """`(a, b, c)` or a single bare literal."""
    if not cursor.take(T.LPAREN):
        lit = cursor.literal()
        return ([] if lit is None else [lit]), []

    inputs: list[Literal] = []
    if not cursor.at(T.RPAREN):
        while True:
            lit = cursor.literal()
            if lit is None:
                break
            inputs.append(lit)
            if not cursor.take(T.COMMA):
                break
    cursor.expect(T.RPAREN, "')' to close the input list")
    return inputs, []


def _resolve_trailer(
    trailer: Token, signature: Signature, file: str | None
) -> tuple[str | None, Literal | None, list[Diagnostic]]:
    """Decide whether the last token names an outcome or pins a value.

    A bare word is an outcome when it matches a declared one (or the `ok`
    alias). Otherwise it is a symbolic expected value -- but only for a
    single-outcome spec, where there is nothing to confuse it with. In a
    multi-outcome spec an unrecognised bare word is a typo, not a value.
    """
    outcomes = signature.outcomes

    if trailer.kind is T.IDENT:
        if trailer.text == SUCCESS_ALIAS or trailer.text == signature.success:
            return signature.success, None, []
        if trailer.text in outcomes:
            return trailer.text, None, []
        if len(outcomes) > 1:
            choices = ", ".join((*outcomes, SUCCESS_ALIAS))
            return (
                None,
                None,
                [
                    error(
                        E_UNKNOWN_OUTCOME,
                        f"{trailer.text!r} is not an outcome of {signature.name}",
                        file=file,
                        line=trailer.line,
                        col=trailer.col,
                        symbol=trailer.text,
                        fix=f"use one of: {choices}",
                    )
                ],
            )
        return signature.success, Sym(trailer.text), []

    lit = _token_literal(trailer)
    if lit is None:
        return (
            None,
            None,
            [
                error(
                    E_EXPECTED_TOKEN,
                    "expected an outcome name or an expected value",
                    file=file,
                    line=trailer.line,
                    col=trailer.col,
                )
            ],
        )
    return signature.success, lit, []


def _token_literal(token: Token) -> Literal | None:
    if token.kind is T.STRING:
        return Str(str(token.value))
    if token.kind is T.NUMBER:
        return Num(token.value)  # type: ignore[arg-type]
    if token.kind is T.TRUE:
        return Bool(True)
    if token.kind is T.FALSE:
        return Bool(False)
    if token.kind is T.NULL:
        return Null()
    if token.kind is T.IDENT:
        return Sym(token.text)
    return None


# --- cursor -----------------------------------------------------------------


class _Cursor:
    def __init__(self, tokens: list[Token], file: str | None):
        self.tokens = tokens
        self.file = file
        self.pos = 0
        self.diags: list[Diagnostic] = []

    def peek(self) -> Token | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def at(self, kind: T) -> bool:
        token = self.peek()
        return token is not None and token.kind is kind

    def take(self, kind: T) -> Token | None:
        if self.at(kind):
            token = self.tokens[self.pos]
            self.pos += 1
            return token
        return None

    def rest(self) -> list[Token]:
        return self.tokens[self.pos :]

    def expect(self, kind: T, what: str) -> Token | None:
        token = self.take(kind)
        if token is not None:
            return token
        found = self.peek()
        self.diags.append(
            error(
                E_EXPECTED_TOKEN,
                f"expected {what}"
                + (f", found {found.text!r}" if found else ", found end of line"),
                file=self.file,
                line=found.line if found else self.tokens[-1].line,
                col=found.col if found else self.tokens[-1].col + len(self.tokens[-1].text),
            )
        )
        return None

    def expect_end(self, what: str) -> None:
        extra = self.peek()
        if extra is not None:
            self.diags.append(
                error(
                    E_EXPECTED_TOKEN,
                    f"unexpected {extra.text!r} after {what}",
                    file=self.file,
                    line=extra.line,
                    col=extra.col,
                )
            )
            self.pos = len(self.tokens)

    def literal(self) -> Literal | None:
        token = self.peek()
        if token is None:
            return None
        if token.kind is T.IDENT and self.pos + 1 < len(self.tokens):
            if self.tokens[self.pos + 1].kind is T.EQ:
                name = token.text
                self.pos += 2
                inner = self.literal()
                if inner is None:
                    return None
                return Named(name=name, value=inner)
        lit = _token_literal(token)
        if lit is None:
            self.expect(T.IDENT, "a value")
            return None
        self.pos += 1
        return lit


def parse_file(path: str) -> tuple[SpecFile, list[Diagnostic]]:
    with open(path, encoding="utf-8") as handle:
        return parse(handle.read(), file=path)
