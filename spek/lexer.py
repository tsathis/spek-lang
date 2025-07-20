"""Tokenizer for spek spec files."""

from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    IDENT = auto()
    LPAREN = auto()
    RPAREN = auto()
    COMMA = auto()
    ARROW = auto()
    PIPE = auto()
    BANG = auto()
    QUESTION = auto()
    COLON = auto()
    NEWLINE = auto()
    EOF = auto()


@dataclass
class Token:
    type: TokenType
    value: str
    line: int


class Lexer:
    def __init__(self, text):
        self.text = text
        self.pos = 0
        self.line = 1

    def peek(self):
        if self.pos < len(self.text):
            return self.text[self.pos]
        return None

    def tokenize(self):
        tokens = []
        while self.pos < len(self.text):
            c = self.peek()
            if c == " " or c == "\t":
                self.pos += 1
            elif c == "\n":
                tokens.append(Token(TokenType.NEWLINE, "\n", self.line))
                self.line += 1
                self.pos += 1
            elif c == "(":
                tokens.append(Token(TokenType.LPAREN, "(", self.line))
                self.pos += 1
            elif c == ")":
                tokens.append(Token(TokenType.RPAREN, ")", self.line))
                self.pos += 1
            elif c == ",":
                tokens.append(Token(TokenType.COMMA, ",", self.line))
                self.pos += 1
            elif c == "-":
                # assume arrow, not handling minus for now
                tokens.append(Token(TokenType.ARROW, "->", self.line))
                self.pos += 2
            elif c == "|":
                tokens.append(Token(TokenType.PIPE, "|", self.line))
                self.pos += 1
            elif c == "!":
                tokens.append(Token(TokenType.BANG, "!", self.line))
                self.pos += 1
            elif c == "?":
                tokens.append(Token(TokenType.QUESTION, "?", self.line))
                self.pos += 1
            elif c == ":":
                tokens.append(Token(TokenType.COLON, ":", self.line))
                self.pos += 1
            elif c.isalpha() or c == "_":
                start = self.pos
                while self.peek() and (self.peek().isalnum() or self.peek() == "_"):
                    self.pos += 1
                tokens.append(Token(TokenType.IDENT, self.text[start:self.pos], self.line))
            else:
                self.pos += 1
        tokens.append(Token(TokenType.EOF, "", self.line))
        return tokens
