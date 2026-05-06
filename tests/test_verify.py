"""End-to-end: a spec, an implementation, and the verdict between them."""

from pathlib import Path

from spek.verify import build, check_spec, verify

SLUGIFY_SPEC = """\
slugify(title) -> text
  "Hello World" "hello-world"
  "  a  b  " "a-b"
  "" ""
"""

GOOD_SLUGIFY = """\
import re


def slugify(title):
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
"""

BAD_SLUGIFY = """\
def slugify(title):
    return title.lower().replace(" ", "-")
"""


def project(tmp_path: Path, spec: str, impl: str, name: str = "slugify"):
    spec_path = tmp_path / f"{name}.spek"
    impl_path = tmp_path / f"{name}.py"
    spec_path.write_text(spec)
    impl_path.write_text(impl)
    return spec_path, impl_path


def test_a_correct_implementation_passes(tmp_path):
    spec_path, impl_path = project(tmp_path, SLUGIFY_SPEC, GOOD_SLUGIFY)
    result = verify(spec_path, impl_path, out_dir=tmp_path / "build")
    assert result.ok, result.test_output
    assert result.tests_ran and result.tests_passed
    assert result.summary()["hatches"] == 0


def test_an_incorrect_implementation_fails_on_the_edge_case(tmp_path):
    spec_path, impl_path = project(tmp_path, SLUGIFY_SPEC, BAD_SLUGIFY)
    result = verify(spec_path, impl_path, out_dir=tmp_path / "build")
    assert not result.ok
    assert result.tests_ran and not result.tests_passed
    # "  a  b  " collapses to "--a--b--" under the naive implementation.
    assert "a-b" in result.test_output


def test_effect_errors_stop_the_tests_from_running(tmp_path):
    spec_path, impl_path = project(
        tmp_path,
        "fetch(id) -> user | missing\n  !fs\n  1 ok\n  2 missing\n",
        "import requests\n\ndef fetch(id):\n    return requests.get(id)\n",
        name="fetch",
    )
    result = verify(spec_path, impl_path, out_dir=tmp_path / "build")
    assert not result.ok
    assert not result.tests_ran
    assert {"E101", "E103"} <= {d.code for d in result.diagnostics}


def test_unbound_symbols_are_found_without_importing_the_fixtures(tmp_path):
    spec_path, impl_path = project(
        tmp_path,
        "fetch(id) -> user | missing\n  known ok\n  unknown missing\n",
        "def fetch(id):\n    return id\n",
        name="fetch",
    )
    (tmp_path / "spek_fixtures.py").write_text(
        "raise RuntimeError('importing this would blow up')\nFIXTURES = {'known': 1}\n"
    )
    result = verify(spec_path, impl_path, out_dir=tmp_path / "build", run_tests=False)
    unbound = [d for d in result.diagnostics if d.code == "E205"]
    assert [d.symbol for d in unbound] == ["unknown"]


def test_a_stub_entry_does_not_count_as_a_binding(tmp_path):
    spec_path, impl_path = project(
        tmp_path,
        "fetch(id) -> user | missing\n  known ok\n  unknown missing\n",
        "def fetch(id):\n    return id\n",
        name="fetch",
    )
    (tmp_path / "spek_fixtures.py").write_text(
        "FIXTURES = {'known': NotImplemented, 'unknown': 2}\n"
    )
    result = verify(spec_path, impl_path, out_dir=tmp_path / "build", run_tests=False)
    assert [d.symbol for d in result.diagnostics if d.code == "E205"] == ["known"]


def test_a_fixtures_stub_is_written_when_there_is_none(tmp_path):
    spec_path, impl_path = project(
        tmp_path,
        "fetch(id) -> user | missing\n  known ok\n  unknown missing\n",
        "def fetch(id):\n    return id\n",
        name="fetch",
    )
    verify(spec_path, impl_path, out_dir=tmp_path / "build", run_tests=False)
    stub = (tmp_path / "spek_fixtures.py").read_text()
    assert "'known': NotImplemented" in stub


def test_an_existing_fixtures_file_is_never_overwritten(tmp_path):
    spec_path, impl_path = project(
        tmp_path,
        "fetch(id) -> user | missing\n  known ok\n  unknown missing\n",
        "def fetch(id):\n    return id\n",
        name="fetch",
    )
    fixtures = tmp_path / "spek_fixtures.py"
    fixtures.write_text("FIXTURES = {'known': 1, 'unknown': 2}\n")
    verify(spec_path, impl_path, out_dir=tmp_path / "build", run_tests=False)
    assert fixtures.read_text() == "FIXTURES = {'known': 1, 'unknown': 2}\n"


def test_build_writes_tests_without_needing_an_implementation(tmp_path):
    spec_path = tmp_path / "s.spek"
    spec_path.write_text(SLUGIFY_SPEC)
    result, tests_path = build(spec_path, tmp_path / "not_written_yet.py", out_dir=tmp_path / "b")
    assert tests_path is not None and tests_path.exists()
    assert result.ok


def test_check_spec_reports_triage(tmp_path):
    spec_path = tmp_path / "s.spek"
    spec_path.write_text("f(x) -> y\n  1 ok\n  ? atomic\n")
    result = check_spec(spec_path)
    assert result.triage["f"]["triage"] == "needs-review"
    assert result.summary()["hatches"] == 1


def test_a_spec_that_does_not_parse_stops_everything(tmp_path):
    spec_path = tmp_path / "s.spek"
    spec_path.write_text("this is not a spec\n")
    result = check_spec(spec_path)
    assert result.spec_file is None
    assert not result.ok


def test_the_bundled_demo_verifies():
    root = Path(__file__).resolve().parent.parent / "examples" / "demo"
    result = verify(root / "auth.spek", root / "auth.py", out_dir=root / ".spek")
    assert result.ok, result.test_output + "\n" + "\n".join(
        d.render() for d in result.diagnostics
    )
    # The demo carries one hatch and two notes; only the hatch drives triage.
    assert result.triage["login"]["triage"] == "needs-review"
    assert len(result.triage["login"]["hatches"]) == 1


def test_a_note_the_implementation_ignores_cannot_fail_the_build(tmp_path):
    """The whole point of `optional`. Nothing may ever check a note."""
    spec_path, impl_path = project(
        tmp_path,
        'slugify(title) -> text\n'
        '  : use a compiled regex module-level, never str.replace\n'
        '  "Hello World" "hello-world"\n'
        '  "" ""\n',
        # Deliberately does exactly what the note says not to.
        'def slugify(title):\n'
        '    return title.lower().replace(" ", "-")\n',
    )
    result = verify(spec_path, impl_path, out_dir=tmp_path / "build")
    assert result.ok, result.test_output
    assert [d.code for d in result.diagnostics] == []
