"""Parses tokens into a Module."""

from spek.lexer import Lexer, TokenType
from spek.spec_ast import Module, Spec, Signature, Example


class Parser:
    def __init__(self, text):
        self.tokens = Lexer(text).tokenize()
        self.pos = 0

    def cur(self):
        return self.tokens[self.pos]

    def advance(self):
        self.pos += 1

    def parse(self):
        module = Module()
        while self.cur().type != TokenType.NEWLINE and self.cur().type != TokenType.EOF:
            module.specs.append(self.parse_spec())
        return module

    def parse_spec(self):
        line = self.cur().line
        name = self.cur().value
        self.advance()
        self.advance()  # (
        params = []
        while self.cur().type != TokenType.RPAREN:
            params.append(self.cur().value)
            self.advance()
            if self.cur().type == TokenType.COMMA:
                self.advance()
        self.advance()  # )
        self.advance()  # ->
        outcomes = [self.cur().value]
        self.advance()
        sig = Signature(name, params, outcomes, line)
        return Spec(sig=sig)
