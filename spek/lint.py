"""Lint checks for spek specs."""

from spek.diagnostics import DiagnosticSet, Diagnostic, Severity


class Linter:
    def __init__(self):
        self.diagnostics = DiagnosticSet()

    def lint_module(self, module):
        for spec in module.specs:
            self.lint_spec(spec)
        return self.diagnostics

    def lint_spec(self, spec):
        if not spec.sig.outcomes:
            self.diagnostics.add(Diagnostic(
                "E002", "at least one outcome required", spec.sig.line, Severity.ERROR
            ))
        if not spec.examples:
            self.diagnostics.add(Diagnostic(
                "W001", "no examples", spec.sig.line, Severity.WARNING, spec.sig.name
            ))

        seen = set()
        for ex in spec.examples:
            key = (tuple(ex.inputs), ex.outcome)
            if key in seen:
                self.diagnostics.add(Diagnostic(
                    "W002", "duplicate example", ex.line, Severity.WARNING, spec.sig.name
                ))
            seen.add(key)

        exercised = {ex.outcome for ex in spec.examples}
        for o in spec.sig.outcomes:
            if o not in exercised:
                self.diagnostics.add(Diagnostic(
                    "W003", f"outcome '{o}' never exercised by an example", spec.sig.line,
                    Severity.WARNING, spec.sig.name
                ))
