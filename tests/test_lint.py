from spek.lint import lint, triage
from spek.parser import parse


def codes(source: str, **kwargs) -> list[str]:
    spec_file, diags = parse(source, "t.spek")
    assert not [d for d in diags if d.is_error], [d.render() for d in diags]
    return [d.code for d in lint(spec_file.specs[0], **kwargs)]


def test_clean_spec_has_nothing_to_say():
    assert codes("f(x) -> y | n\n  1 ok\n  2 n\n") == []


def test_unexercised_outcome_is_the_untested_failure_path():
    found = codes("f(x) -> y | n | boom\n  1 ok\n  2 n\n")
    assert found == ["W304"]


def test_arity_mismatch():
    assert "E203" in codes("f(a, b, c) -> y\n  (1, 2) ok\n")


def test_named_input_that_matches_no_parameter_is_setup_and_still_counted():
    found = codes("transfer(src, dst, amount) -> ok | no\n  (a=1, 50) ok\n  2 no\n")
    assert "E203" in found


def test_parameter_bound_twice():
    assert "E208" in codes("f(a, b) -> y\n  (1, a=2) ok\n")


def test_duplicate_outcome_and_effect():
    found = codes("f(x) -> y | y\n  !db !db\n  1 ok\n")
    assert "E301" not in found
    assert "E201" in found and "E102" in found


def test_unknown_effect_tag_warns_but_parses():
    found = codes("f(x) -> y\n  !telepathy\n  1 ok\n")
    assert found == ["W302"]


def test_no_examples():
    found = codes("f(x) -> y\n  !db\n")
    assert "W303" in found


def test_line_budget():
    body = "\n".join(f"  {n} ok" for n in range(8))
    assert "W306" in codes(f"f(x) -> y\n{body}\n")
    assert "W306" not in codes(f"f(x) -> y\n{body}\n", line_budget=20)


def test_hatch_heavy_spec_is_flagged():
    source = (
        "schedule(tasks, workers) -> assignment | infeasible\n"
        "  ? minimizes makespan\n  ? respects dependencies\n"
    )
    assert "W305" in codes(source)


def test_duplicate_example():
    assert "W307" in codes("f(x) -> y | n\n  1 ok\n  1 n\n")


def test_triage_bands():
    def spec_of(source):
        return parse(source, "t.spek")[0].specs[0]

    assert triage(spec_of("f(x) -> y\n  1 ok\n")) == "machine-verifiable"
    assert triage(spec_of("f(x) -> y\n  1 ok\n  ? a\n  ? b\n")) == "needs-review"
    assert triage(spec_of("f(x) -> y\n  ? a\n  ? b\n  ? c\n")) == "hand-written"
