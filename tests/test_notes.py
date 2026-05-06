"""The note line: optional guidance that nothing verifies.

The property under test throughout is that a note is *inert*. It reaches the
prompts and the generated tests, and it changes no verdict anywhere.
"""

import ast
import re

from spek.codegen.python import generate_tests
from spek.lint import NOTE_BUDGET, lint, triage
from spek.parser import parse
from spek.prompt import generation_prompt, repair_prompt

SPEC = """\
login(email, password) -> session | wrong | locked
  !db !hash
  : known is a user that exists and is not locked
  : reuse the session helper in tokens.py
  (known, right) ok
  (unknown, any) wrong
  (locked_acct, right) locked
  ? password compared in constant time
"""


def one(source: str):
    spec_file, diags = parse(source, "t.spek")
    assert not [d for d in diags if d.is_error], [d.render() for d in diags]
    return spec_file.specs[0]


def test_notes_are_parsed_and_kept_in_order():
    spec = one(SPEC)
    assert [n.text for n in spec.notes] == [
        "known is a user that exists and is not locked",
        "reuse the session helper in tokens.py",
    ]


def test_a_note_keeps_its_colons_and_punctuation():
    spec = one("f(x) -> y\n  : see RFC 7231: section 6.5.1 -- status codes\n  1 ok\n")
    assert spec.notes[0].text == "see RFC 7231: section 6.5.1 -- status codes"


def test_notes_do_not_eat_the_body_budget():
    spec = one(SPEC)
    assert spec.body_lines == 5  # 1 effect line + 3 examples + 1 hatch
    assert spec.note_lines == 2


def test_effects_sharing_a_line_count_once():
    """The budget measures what the eye traverses, not how many items exist."""
    assert one("f(x) -> y\n  !db !hash !net\n  1 ok\n").body_lines == 2
    assert one("f(x) -> y\n  !db\n  !hash\n  !net\n  1 ok\n").body_lines == 4


def test_a_spec_at_budget_still_passes_with_notes_added():
    body = "f(x) -> y\n" + "".join(f"  {n} ok\n" for n in range(6))
    with_notes = body + "".join(f"  : note {n}\n" for n in range(3))
    assert [d.code for d in lint(one(with_notes))] == []


def test_notes_are_not_a_triage_signal():
    spec = one("f(x) -> y\n  : a\n  : b\n  : c\n  1 ok\n")
    assert triage(spec) == "machine-verifiable"
    assert not spec.hatches


def test_a_hatch_still_drives_triage_when_notes_are_present():
    assert triage(one(SPEC)) == "needs-review"


def test_too_many_notes_warns():
    source = "f(x) -> y\n  1 ok\n" + "".join(f"  : note {n}\n" for n in range(NOTE_BUDGET + 1))
    found = [d for d in lint(one(source)) if d.code == "W309"]
    assert len(found) == 1
    assert "CLAUDE.md" in found[0].fix


def test_the_note_budget_is_configurable():
    source = "f(x) -> y\n  1 ok\n" + "".join(f"  : note {n}\n" for n in range(5))
    assert [d.code for d in lint(one(source), note_budget=10)] == []


def test_an_empty_note_is_rejected():
    _, diags = parse("f(x) -> y\n  1 ok\n  :\n", "t.spek")
    assert [d.code for d in diags] == ["E007"]


def test_a_note_is_not_confused_with_an_example():
    spec = one("f(x) -> y | n\n  : 1 ok\n  1 ok\n  2 n\n")
    assert len(spec.examples) == 2
    assert spec.notes[0].text == "1 ok"


def test_notes_reach_the_generation_prompt():
    spec_file, _ = parse(SPEC, "t.spek")
    prompt = generation_prompt(spec_file, "auth.py")
    assert ": reuse the session helper in tokens.py" in prompt


def test_notes_reach_the_repair_prompt():
    spec_file, _ = parse(SPEC, "t.spek")
    assert ": reuse the session helper in tokens.py" in repair_prompt(spec_file, "auth.py", [])


def test_the_prompt_tells_the_model_notes_are_optional():
    from spek.prompt import CONVENTIONS

    assert "optional guidance" in CONVENTIONS
    assert "An example always wins over a note." in CONVENTIONS


def test_notes_become_comments_in_the_generated_tests(tmp_path):
    spec_file, _ = parse(SPEC, "t.spek")
    code = generate_tests(spec_file, "auth.py", tmp_path / "test_x.py")
    ast.parse(code)
    assert "#   : reuse the session helper in tokens.py" in code


def test_a_note_never_changes_the_generated_cases(tmp_path):
    """A note adds comments and shifts source line numbers. Nothing else."""
    plain = "f(x) -> y | n\n  1 ok\n  2 n\n"
    noted = "f(x) -> y | n\n  : do it the fast way\n  1 ok\n  2 n\n"
    without = generate_tests(parse(plain, "t.spek")[0], "a.py", tmp_path / "t.py")
    with_note = generate_tests(parse(noted, "t.spek")[0], "a.py", tmp_path / "t.py")

    def executable(code: str) -> list[str]:
        return [
            re.sub(r"line=\d+", "line=N", line)
            for line in code.splitlines()
            if not line.lstrip().startswith("#")
        ]

    assert executable(without) == executable(with_note)


def test_a_note_shifts_the_recorded_line_of_a_later_example():
    """The line number must point at the real line in the file."""
    spec = one("f(x) -> y\n  : guidance\n  1 ok\n")
    assert spec.examples[0].span.line == 3
