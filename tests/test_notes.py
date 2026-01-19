import pytest
from spek.parser import Parser


def test_notes_dont_affect_lint():
    text = "login(u, p) -> ok\n: use bcrypt\n(a, b) ok\n"
    module = Parser(text).parse()
    spec = module.specs[0]
    assert spec.notes[0].text == "use bcrypt"
