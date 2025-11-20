import pytest
from spek.spec_ast import Spec, Signature, Example
from spek.codegen.python import PythonCodegen


def test_generate_basic_case():
    sig = Signature("add", ["a", "b"], ["ok"], line=1)
    spec = Spec(sig=sig)
    spec.examples.append(Example(["a", "b"], "ok", line=2))
    code = PythonCodegen(spec, "impl", "add").generate()
    assert "from impl import add" in code
    assert "def test_case_0" in code
