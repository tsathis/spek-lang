"""Parses tokens into a Module."""

from spek.lexer import Lexer, TokenType
from spek.spec_ast import Module, Spec, Signature, Example, Effect, Hatch, Note


class Parser:
    def __init__(self, text):
        self.tokens = Lexer(text).tokenize()
        self.pos = 0

    def cur(self):
        return self.tokens[self.pos]

    def advance(self):
        self.pos += 1

    def skip_newlines(self):
        while self.cur().type == TokenType.NEWLINE:
            self.advance()

    def parse(self):
        module = Module()
        self.skip_newlines()
        while self.cur().type == TokenType.IDENT:
            module.specs.append(self.parse_spec())
            self.skip_newlines()
        return module

    def parse_spec(self):
        sig = self.parse_signature()
        spec = Spec(sig=sig)
        while self.cur().type in (TokenType.BANG, TokenType.QUESTION, TokenType.COLON, TokenType.LPAREN):
            if self.cur().type == TokenType.BANG:
                spec.effects.append(self.parse_effect())
            elif self.cur().type == TokenType.QUESTION:
                spec.hatches.append(self.parse_hatch())
            elif self.cur().type == TokenType.COLON:
                spec.notes.append(self.parse_note())
            else:
                spec.examples.append(self.parse_example())
        return spec

    def parse_signature(self):
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
        outcomes = []
        while self.cur().type != TokenType.NEWLINE:
            outcomes.append(self.cur().value)
            self.advance()
            if self.cur().type == TokenType.PIPE:
                self.advance()
        self.advance()  # newline
        return Signature(name, params, outcomes, line)

    def parse_effect(self):
        line = self.cur().line
        self.advance()  # !
        name = self.cur().value
        self.advance()
        self.advance()  # newline
        return Effect(name, line)

    def parse_hatch(self):
        line = self.cur().line
        self.advance()  # ?
        text = ""
        while self.cur().type != TokenType.NEWLINE:
            text += self.cur().value + " "
            self.advance()
        self.advance()
        return Hatch(text.strip(), line)

    def parse_note(self):
        line = self.cur().line
        self.advance()  # :
        text = ""
        while self.cur().type != TokenType.NEWLINE:
            text += self.cur().value + " "
            self.advance()
        self.advance()
        return Note(text.strip(), line)

    def parse_example(self):
        line = self.cur().line
        self.advance()  # (
        inputs = []
        while self.cur().type != TokenType.RPAREN:
            inputs.append(self.cur().value)
            self.advance()
            if self.cur().type == TokenType.COMMA:
                self.advance()
        self.advance()  # )
        outcome = self.cur().value
        self.advance()
        self.advance()  # newline
        return Example(inputs, outcome, line)
