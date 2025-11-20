import pytest
from spek.runtime import FixtureContext, classify_outcome


def test_fixture_context():
    ctx = FixtureContext({"user": "alice"})
    assert ctx.get("user") == "alice"


def test_classify_success():
    outcome, result = classify_outcome(lambda: 42, (), ["ok"])
    assert outcome == "ok"
    assert result == 42


def test_classify_exception_outcome():
    class Locked(Exception):
        pass

    def fn():
        raise Locked()

    outcome, _ = classify_outcome(fn, (), ["ok", "locked"])
    assert outcome == "locked"
