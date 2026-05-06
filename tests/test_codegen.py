import ast

from spek.codegen.python import fixtures_stub, generate_tests
from spek.parser import parse


def parsed(source: str):
    spec_file, diags = parse(source, "t.spek")
    assert not [d for d in diags if d.is_error], [d.render() for d in diags]
    return spec_file


LOGIN = (
    "login(email, password) -> session | wrong | locked\n"
    "  !db !hash\n"
    "  (known, right) ok\n"
    "  (unknown, any) wrong\n"
)


def test_generated_module_is_valid_python(tmp_path):
    code = generate_tests(parsed(LOGIN), "auth.py", tmp_path / "test_x.py")
    ast.parse(code)


def test_generated_module_carries_one_case_per_example(tmp_path):
    code = generate_tests(parsed(LOGIN), "auth.py", tmp_path / "test_x.py")
    assert code.count("Case(") == 2
    assert 'outcome=\'session\'' in code and 'outcome=\'wrong\'' in code
    assert "Ref('known')" in code
    assert "def test_login(case: Case)" in code


def test_generated_module_never_contains_an_implementation(tmp_path):
    code = generate_tests(parsed(LOGIN), "auth.py", tmp_path / "test_x.py")
    tree = ast.parse(code)
    defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert defined == {"test_login"}


def test_hatches_become_comments_and_a_triage_table(tmp_path):
    source = "f(x) -> y\n  1 ok\n  ? atomic\n"
    code = generate_tests(parsed(source), "a.py", tmp_path / "test_x.py")
    assert "? atomic" in code
    assert "not verified" in code
    namespace: dict = {}
    exec(compile(ast.parse(_triage_only(code)), "<t>", "exec"), namespace)
    assert namespace["SPEK_TRIAGE"]["f"] == {
        "triage": "needs-review",
        "hatches": ["atomic"],
        "examples": 1,
    }


def _triage_only(code: str) -> str:
    start = code.index("SPEK_TRIAGE")
    return code[start:]


def test_expected_values_are_lowered(tmp_path):
    code = generate_tests(
        parsed('slugify(t) -> text\n  "Hello World" "hello-world"\n'),
        "s.py",
        tmp_path / "test_x.py",
    )
    assert "has_expect=True" in code
    assert "expect='hello-world'" in code


def test_named_inputs_split_into_kwargs_and_setup(tmp_path):
    code = generate_tests(
        parsed("t(src, dst, amount) -> ok | no\n  (a, b, amount=5) ok\n  (a, b, 1) no\n"),
        "t.py",
        tmp_path / "test_x.py",
    )
    assert "kwargs={'amount': 5}" in code


def test_setup_bindings_are_separated(tmp_path):
    code = generate_tests(
        parsed("t(x) -> ok | no\n  (seeded=100, 1) ok\n  2 no\n"),
        "t.py",
        tmp_path / "test_x.py",
    )
    assert "setup={'seeded': 100}" in code


def test_spec_with_no_examples_emits_no_test(tmp_path):
    code = generate_tests(parsed("f(x) -> y\n  ? everything\n"), "a.py", tmp_path / "test_x.py")
    ast.parse(code)
    assert "def test_" not in code
    assert "no examples" in code


def test_module_import_mode(tmp_path):
    code = generate_tests(parsed(LOGIN), "pkg.auth", tmp_path / "t.py", impl_is_module=True)
    assert "import pkg.auth as _IMPL" in code


def test_fixtures_stub_names_every_symbol():
    stub = fixtures_stub(parsed(LOGIN))
    ast.parse(stub)
    for symbol in ("known", "right", "unknown", "any"):
        assert f"{symbol!r}: NotImplemented" in stub


def test_fixtures_stub_adds_a_setup_hook_when_setup_is_used():
    stub = fixtures_stub(parsed("t(x) -> ok | no\n  (seeded=1, 2) ok\n  3 no\n"))
    ast.parse(stub)
    assert "def setup(spec: str, bindings: dict)" in stub


def test_generated_names_survive_a_dotted_spec(tmp_path):
    code = generate_tests(
        parsed("cache.get(key) -> value | miss\n  a ok\n  b miss\n"), "c.py", tmp_path / "t.py"
    )
    ast.parse(code)
    assert "def test_cache_get(" in code
    assert "target='cache.get'" in code
