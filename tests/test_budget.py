import pytest
from spek.parser import Parser


def test_spec_body_is_short():
    """specs should stay small enough to paste in a prompt"""
    text = "login(u, p) -> ok | fail\n!db\n(a, b) ok\n"
    module = Parser(text).parse()
    spec = module.specs[0]
    body_lines = len(spec.effects) + len(spec.examples) + len(spec.hatches) + len(spec.notes)
    assert body_lines <= 6
