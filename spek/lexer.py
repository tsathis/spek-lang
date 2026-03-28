"""Token scanner for a single line of spec.

Hatch lines never reach here -- their text is taken raw -- so the scanner only
has to cover signatures and examples.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .diagnostics import E_UNEXPECTED_CHAR, E_UNTERMINATED_STRING, Diagnostic, error


class T(str, Enum):
    IDENT = "ident"
    STRING = "string"
    NUMBER = "number"
    TRUE = "true"
    FALSE = "false"
    NULL = "null"
    LPAREN = "("
    RPAREN = ")"
    COMMA = ","
    PIPE = "|"
    ARROW = "->"
    BANG = "!"
    EQ = "="


@dataclass(frozen=True)
class Token:
    kind: T
    text: str
    line: int
    col: int
    value: object = None


_PUNCT = {"(": T.LPAREN, ")": T.RPAREN, ",": T.COMMA, "|": T.PIPE, "!": T.BANG, "=": T.EQ}
_WORDS = {"true": T.TRUE, "false": T.FALSE, "null": T.NULL, "none": T.NULL}

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "0": "\0"}


def _ident_char(ch: str, first: bool = False) -> bool:
    if ch == "_" or ch.isalpha():
        return True
    return not first and (ch.isdigit() or ch == ".")


def scan(text: str, line: int, file: str | None = None) -> tuple[list[Token], list[Diagnostic]]:
    """Tokenize one line. Returns tokens plus any lexical diagnostics."""
    tokens: list[Token] = []
    diags: list[Diagnostic] = []
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]
        col = i + 1

        if ch in " \t":
            i += 1
            continue

        if ch == "#":  # comment to end of line
            break

        if text.startswith("->", i):
            tokens.append(Token(T.ARROW, "->", line, col))
            i += 2
            continue

        if ch in _PUNCT:
            tokens.append(Token(_PUNCT[ch], ch, line, col))
            i += 1
            continue

        if ch == '"':
            i += 1
            buf: list[str] = []
            closed = False
            while i < n:
                c = text[i]
                if c == "\\" and i + 1 < n:
                    buf.append(_ESCAPES.get(text[i + 1], text[i + 1]))
                    i += 2
                    continue
                if c == '"':
                    i += 1
                    closed = True
                    break
                buf.append(c)
                i += 1
            value = "".join(buf)
            if not closed:
                diags.append(
                    error(
                        E_UNTERMINATED_STRING,
                        "unterminated string literal",
                        file=file,
                        line=line,
                        col=col,
                        fix='close the string with a double quote',
                    )
                )
            tokens.append(Token(T.STRING, text[col - 1 : i], line, col, value))
            continue

        if ch.isdigit() or (ch == "-" and i + 1 < n and text[i + 1].isdigit()):
            start = i
            i += 1
            seen_dot = False
            while i < n and (text[i].isdigit() or (text[i] == "." and not seen_dot)):
                if text[i] == ".":
                    # A trailing dot is not part of the number.
                    if i + 1 >= n or not text[i + 1].isdigit():
                        break
                    seen_dot = True
                i += 1
            raw = text[start:i]
            tokens.append(Token(T.NUMBER, raw, line, col, float(raw) if seen_dot else int(raw)))
            continue

        if _ident_char(ch, first=True):
            start = i
            while i < n and _ident_char(text[i]):
                i += 1
            raw = text[start:i]
            kind = _WORDS.get(raw.lower(), T.IDENT)
            tokens.append(Token(kind, raw, line, col))
            continue

        diags.append(
            error(
                E_UNEXPECTED_CHAR,
                f"unexpected character {ch!r}",
                file=file,
                line=line,
                col=col,
                symbol=ch,
            )
        )
        i += 1

    return tokens, diags
