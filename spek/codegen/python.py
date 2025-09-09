"""Generates a pytest module from a Spec."""


class PythonCodegen:
    def __init__(self, spec, impl_module, impl_func, fixtures_module="spek_fixtures"):
        self.spec = spec
        self.impl_module = impl_module
        self.impl_func = impl_func
        self.fixtures_module = fixtures_module

    def generate(self):
        lines = [
            "import pytest",
            f"from {self.impl_module} import {self.impl_func}",
            f"from spek.runtime import classify_outcome",
            "",
        ]
        try:
            lines.append(f"import {self.fixtures_module} as fx")
        except Exception:
            pass
        lines.append("")
        outcomes = self.spec.sig.outcomes
        for i, ex in enumerate(self.spec.examples):
            args = ", ".join(f"fx.{a}" for a in ex.inputs)
            lines.append(f"def test_case_{i}():")
            lines.append(f"    outcome, _ = classify_outcome(lambda: {self.impl_func}({args}), (), {outcomes!r})")
            lines.append(f"    assert outcome == {ex.outcome!r}")
            lines.append("")
        return "\n".join(lines)
