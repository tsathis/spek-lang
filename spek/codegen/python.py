"""Generates a pytest module from a Spec."""


class PythonCodegen:
    def __init__(self, spec, impl_module, impl_func):
        self.spec = spec
        self.impl_module = impl_module
        self.impl_func = impl_func

    def generate(self):
        lines = [
            "import pytest",
            f"from {self.impl_module} import {self.impl_func}",
            "",
        ]
        for i, ex in enumerate(self.spec.examples):
            args = ", ".join(ex.inputs)
            lines.append(f"def test_case_{i}():")
            lines.append(f"    result = {self.impl_func}({args})")
            lines.append(f"    assert result == \"{ex.outcome}\"")
            lines.append("")
        return "\n".join(lines)
