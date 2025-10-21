"""End-to-end verification pipeline."""

import inspect
from spek.parser import Parser
from spek.lint import Linter
from spek.diagnostics import Diagnostic, Severity


class Verifier:
    def verify(self, spec_text, impl_path):
        parser = Parser(spec_text)
        module = parser.parse()

        linter = Linter()
        diagnostics = linter.lint_module(module)

        if diagnostics.has_errors():
            return diagnostics

        for spec in module.specs:
            self._check_effects(spec, impl_path, diagnostics)

        return diagnostics

    def _check_effects(self, spec, impl_path, diagnostics):
        from spek.effects.python import EffectChecker
        code = open(impl_path).read()
        found = EffectChecker().check(code, spec.sig.name)
        declared = {e.name for e in spec.effects}
        for eff in found - declared:
            diagnostics.add(Diagnostic(
                "E101", f"undeclared effect: {eff}", spec.sig.line, Severity.ERROR, spec.sig.name
            ))
