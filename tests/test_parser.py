from spek.parser import parse
from spek.spec_ast import Named, Num, Str, Sym


def one(source: str):
    spec_file, diags = parse(source, "t.spek")
    assert not [d for d in diags if d.is_error], [d.render() for d in diags]
    assert len(spec_file) == 1
    return spec_file.specs[0]


def test_signature_params_and_outcomes():
    spec = one("login(email, password) -> session | wrong | locked\n  (a, b) ok\n")
    assert spec.name == "login"
    assert spec.signature.params == ("email", "password")
    assert spec.signature.outcomes == ("session", "wrong", "locked")
    assert spec.signature.success == "session"
    assert spec.signature.failures == ("wrong", "locked")


def test_ok_is_an_alias_for_the_first_outcome():
    spec = one("f(x) -> good | bad\n  1 ok\n  2 bad\n")
    assert [e.outcome for e in spec.examples] == ["good", "bad"]


def test_effects_may_share_a_line():
    spec = one("f(x) -> y\n  !db !hash\n  1 ok\n")
    assert spec.effect_tags == ("db", "hash")


def test_hatch_text_is_taken_raw():
    spec = one("f(x) -> y\n  1 ok\n  ? retries 3x with backoff | and more\n")
    assert [h.text for h in spec.hatches] == ["retries 3x with backoff | and more"]


def test_single_outcome_trailer_is_an_expected_value():
    spec = one('slugify(title) -> text\n  "Hello World" "hello-world"\n')
    example = spec.examples[0]
    assert example.inputs == (Str("Hello World"),)
    assert example.outcome == "text"
    assert example.expect == Str("hello-world")


def test_bare_word_in_input_position_stays_a_symbol():
    # `wrong` is also an outcome name, but here it is an input.
    spec = one("login(e, p) -> session | wrong\n  (known, wrong) wrong\n")
    assert spec.examples[0].inputs == (Sym("known"), Sym("wrong"))
    assert spec.examples[0].outcome == "wrong"


def test_unknown_trailer_in_a_multi_outcome_spec_is_an_error():
    _, diags = parse("f(x) -> a | b\n  1 typo\n", "t.spek")
    codes = [d.code for d in diags]
    assert "E202" in codes
    assert "b" in [d for d in diags if d.code == "E202"][0].fix


def test_unknown_trailer_in_a_single_outcome_spec_is_a_symbol():
    spec = one("f(x) -> text\n  1 whatever\n")
    assert spec.examples[0].expect == Sym("whatever")


def test_named_inputs():
    spec = one("f(a, b) -> y\n  (a=1, b=2) ok\n")
    assert spec.examples[0].named == (Named("a", Num(1)), Named("b", Num(2)))
    assert spec.examples[0].positional == ()


def test_literal_kinds():
    spec = one('f(x) -> y\n  1 ok\n  -2.5 ok\n  "s" ok\n  true ok\n  null ok\n')
    assert [e.inputs[0] for e in spec.examples][:2] == [Num(1), Num(-2.5)]
    assert spec.examples[2].inputs[0] == Str("s")


def test_dotted_name_splits_into_owner_and_method():
    spec = one("cache.get(key) -> value | miss\n  k ok\n")
    assert spec.python_owner() == "cache"
    assert spec.python_name() == "get"


def test_several_specs_in_one_file():
    spec_file, diags = parse("a(x) -> y\n  1 ok\nb(x) -> z\n  2 ok\n", "t.spek")
    assert not diags
    assert [s.name for s in spec_file] == ["a", "b"]


def test_comments_and_blank_lines_are_ignored():
    spec = one("# header\n\nf(x) -> y\n\n  1 ok  # trailing\n")
    assert len(spec.examples) == 1


def test_zero_argument_example():
    spec = one("now() -> time | unavailable\n  ok\n  unavailable\n")
    assert spec.examples[0].inputs == ()
    assert [e.outcome for e in spec.examples] == ["time", "unavailable"]


def test_multiple_inputs_without_parens_is_reported():
    _, diags = parse("f(a, b) -> y\n  1 2 ok\n", "t.spek")
    assert [d.code for d in diags] == ["E003"]
    assert "parentheses" in diags[0].fix


def test_body_line_before_any_signature():
    _, diags = parse("  1 ok\n", "t.spek")
    assert [d.code for d in diags] == ["E004"]


def test_unterminated_string():
    _, diags = parse('f(x) -> y\n  "oops ok\n', "t.spek")
    assert "E001" in [d.code for d in diags]


def test_empty_hatch_is_rejected():
    _, diags = parse("f(x) -> y\n  1 ok\n  ?\n", "t.spek")
    assert [d.code for d in diags] == ["E006"]


def test_symbols_are_collected_in_first_seen_order():
    spec = one("f(a, b) -> y | n\n  (known, right) ok\n  (known, wrong) n\n")
    assert spec.symbols == ("known", "right", "wrong")


def test_parse_errors_do_not_stop_later_lines():
    spec_file, diags = parse("f(x) -> y\n  ?\n  1 ok\n", "t.spek")
    assert [d.code for d in diags] == ["E006"]
    assert len(spec_file.specs[0].examples) == 1
