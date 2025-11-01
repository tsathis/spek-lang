import pytest
from spek.parser import Parser


def test_parse_simple_signature():
    text = "login(user, pw) -> ok | fail\n"
    module = Parser(text).parse()
    spec = module.specs[0]
    assert spec.sig.name == "login"
    assert spec.sig.params == ["user", "pw"]
    assert spec.sig.outcomes == ["ok", "fail"]


def test_parse_with_effects():
    text = "login(user, pw) -> ok | fail\n!db\n!hash\n"
    module = Parser(text).parse()
    spec = module.specs[0]
    assert [e.name for e in spec.effects] == ["db", "hash"]
