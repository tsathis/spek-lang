import pytest
from spek.verify import Verifier


def test_verify_lint_only_for_now():
    spec = "login(user, pw) -> ok | fail\n!hash\n(a, b) ok\n(a, c) fail\n"
    diags = Verifier().verify(spec, "examples/demo/auth.py")
    assert not diags.has_errors()
