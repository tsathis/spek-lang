"""End-to-end verification pipeline."""

from spek.parser import Parser
from spek.lint import Linter


class Verifier:
    def verify(self, spec_text, impl_path):
        parser = Parser(spec_text)
        module = parser.parse()

        linter = Linter()
        diagnostics = linter.lint_module(module)

        if diagnostics.has_errors():
            return diagnostics

        # TODO: effects check
        # TODO: codegen + run pytest
        return diagnostics
