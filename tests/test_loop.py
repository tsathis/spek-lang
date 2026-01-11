import pytest
from spek.loop import Loop
from spek.spec_ast import Spec, Signature


def test_loop_max_rounds():
    sig = Signature("add", ["a", "b"], ["ok"], line=1)
    spec = Spec(sig=sig)
    loop = Loop(spec, "impl.py", "echo hi", max_rounds=2)
    assert loop.max_rounds == 2
