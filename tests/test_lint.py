import pytest
from spek.spec_ast import Spec, Signature
from spek.lint import Linter


def test_missing_outcomes_is_error():
    sig = Signature("foo", ["x"], [], line=1)
    linter = Linter()
    linter.lint_spec(Spec(sig=sig))
    assert linter.diagnostics.has_errors()


def test_no_examples_is_warning():
    sig = Signature("foo", ["x"], ["ok"], line=1)
    linter = Linter()
    linter.lint_spec(Spec(sig=sig))
    assert len(linter.diagnostics.warnings()) == 1
