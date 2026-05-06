import pytest

from spek.runtime import (
    Case,
    Fresh,
    Ref,
    SpekTargetMissing,
    SpekUnboundSymbol,
    classify,
    load_module_from_path,
    resolve,
    run_case,
    target_for,
)

OUTCOMES = ("session", "wrong", "locked")


class AccountLockedError(Exception):
    pass


class WrongCredentials(Exception):
    pass


def test_returning_normally_is_the_first_outcome():
    assert classify(OUTCOMES, "anything", None) == "session"


def test_exception_class_name_selects_the_outcome():
    assert classify(OUTCOMES, None, AccountLockedError()) == "locked"
    assert classify(OUTCOMES, None, WrongCredentials()) == "wrong"


def test_base_classes_are_searched():
    class Specific(AccountLockedError):
        pass

    assert classify(OUTCOMES, None, Specific()) == "locked"


def test_unmatched_exception_is_unclassified():
    assert classify(OUTCOMES, None, ValueError("boom")) is None


def test_outcome_attribute_tags_a_returned_value():
    class Result:
        outcome = "locked"

    assert classify(OUTCOMES, Result(), None) == "locked"


def test_tuple_tag_form():
    assert classify(OUTCOMES, ("wrong", None), None) == "wrong"


def test_enum_member_is_read():
    import enum

    class Outcome(enum.Enum):
        LOCKED = "locked"

    assert classify(OUTCOMES, Outcome.LOCKED, None) == "locked"


def test_longest_outcome_wins_over_a_shorter_substring():
    assert classify(("ok", "not_ok"), None, Exception("not_ok")) == "not_ok"


def test_resolve_binds_symbols():
    assert resolve(Ref("known"), {"known": "ada@example.com"}) == "ada@example.com"
    assert resolve(7, {}) == 7


def test_fresh_fixtures_are_rebuilt_per_lookup():
    bindings = {"box": Fresh(list)}
    first = resolve(Ref("box"), bindings)
    first.append(1)
    assert resolve(Ref("box"), bindings) == []


def test_unbound_symbol_names_itself():
    with pytest.raises(SpekUnboundSymbol) as caught:
        resolve(Ref("known"), {"other": 1})
    assert "known" in str(caught.value) and "other" in str(caught.value)


def _module(tmp_path, source: str, name: str = "impl"):
    path = tmp_path / f"{name}.py"
    path.write_text(source)
    return load_module_from_path(path, name=f"_spek_test_{name}_{abs(hash(source)) % 9999}")


def test_target_for_finds_a_function(tmp_path):
    module = _module(tmp_path, "def login(a, b):\n    return (a, b)\n")
    assert target_for(module, "login")("x", "y") == ("x", "y")


def test_target_for_finds_a_method_on_a_capitalised_class(tmp_path):
    module = _module(tmp_path, "class Cache:\n    def get(self, k):\n        return k\n", "c")
    assert target_for(module, "cache.get")("k") == "k"


def test_target_for_reports_what_is_missing(tmp_path):
    module = _module(tmp_path, "x = 1\n", "empty")
    with pytest.raises(SpekTargetMissing):
        target_for(module, "login")


def test_run_case_passes_when_the_outcome_matches(tmp_path):
    module = _module(
        tmp_path,
        "class WrongCredentials(Exception):\n    pass\n\n"
        "def login(e, p):\n"
        "    if p != 'right':\n        raise WrongCredentials()\n    return e\n",
        "auth_ok",
    )
    run_case(
        module,
        Case(spec="login", target="login", args=("a", "right"),
             outcome="session", outcomes=OUTCOMES, line=3),
    )
    run_case(
        module,
        Case(spec="login", target="login", args=("a", "no"),
             outcome="wrong", outcomes=OUTCOMES, line=4),
    )


def test_run_case_explains_a_wrong_outcome(tmp_path):
    module = _module(tmp_path, "def login(e, p):\n    return e\n", "auth_bad")
    with pytest.raises(AssertionError) as caught:
        run_case(
            module,
            Case(spec="login", target="login", args=("a", "no"),
                 outcome="wrong", outcomes=OUTCOMES, line=4),
        )
    message = str(caught.value)
    assert "should give outcome 'wrong'" in message
    assert "raise an exception" in message


def test_run_case_checks_an_expected_value(tmp_path):
    module = _module(tmp_path, "def slugify(t):\n    return t.upper()\n", "slug")
    with pytest.raises(AssertionError) as caught:
        run_case(
            module,
            Case(spec="slugify", target="slugify", args=("Hi",), outcome="text",
                 outcomes=("text",), expect="hi", has_expect=True, line=2),
        )
    assert "returned 'HI', expected 'hi'" in str(caught.value)


def test_setup_without_a_hook_is_reported(tmp_path):
    module = _module(tmp_path, "def f(x):\n    return x\n", "setupless")
    with pytest.raises(SpekUnboundSymbol) as caught:
        run_case(
            module,
            Case(spec="f", target="f", args=(1,), setup={"seeded": 100},
                 outcome="y", outcomes=("y",), line=2),
        )
    assert "setup" in str(caught.value)
