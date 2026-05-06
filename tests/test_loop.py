"""The generate -> verify -> repair loop, driven by a stand-in for the model."""

from pathlib import Path

from spek.loop import CommandGenerator, run

SPEC = """\
slugify(title) -> text
  "Hello World" "hello-world"
  "  a  b  " "a-b"
  "" ""
"""

NAIVE = 'def slugify(title):\n    return title.lower().replace(" ", "-")\n'
CORRECT = (
    "import re\n\n\n"
    'def slugify(title):\n    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")\n'
)


class ScriptedGenerator:
    """Writes a canned implementation per round and records its prompts."""

    def __init__(self, *sources: str):
        self.sources = list(sources)
        self.prompts: list[str] = []

    def __call__(self, prompt: str, target: Path) -> None:
        self.prompts.append(prompt)
        target.write_text(self.sources.pop(0))


def spec_at(tmp_path: Path) -> Path:
    path = tmp_path / "slugify.spek"
    path.write_text(SPEC)
    return path


def test_the_loop_repairs_a_failing_implementation(tmp_path):
    generator = ScriptedGenerator(NAIVE, CORRECT)
    outcome = run(
        spec_at(tmp_path),
        tmp_path / "slugify.py",
        generator=generator,
        out_dir=tmp_path / "build",
    )
    assert outcome.ok
    assert len(outcome.rounds) == 2
    assert not outcome.rounds[0].ok and outcome.rounds[1].ok


def test_the_first_prompt_carries_the_spec_and_the_conventions(tmp_path):
    generator = ScriptedGenerator(CORRECT)
    run(spec_at(tmp_path), tmp_path / "slugify.py", generator=generator, out_dir=tmp_path / "b")
    first = generator.prompts[0]
    assert "slugify(title) -> text" in first
    assert '"Hello World" "hello-world"' in first
    assert "The first one" in first  # the outcome protocol


def test_the_repair_prompt_carries_the_findings(tmp_path):
    generator = ScriptedGenerator(NAIVE, CORRECT)
    run(spec_at(tmp_path), tmp_path / "slugify.py", generator=generator, out_dir=tmp_path / "b")
    repair = generator.prompts[1]
    assert "does not satisfy its spec" in repair
    assert "Test output:" in repair
    assert "do not" in repair and "edit the generated tests" in repair


def test_an_implementation_already_on_disk_is_verified_before_being_touched(tmp_path):
    impl = tmp_path / "slugify.py"
    impl.write_text(CORRECT)
    generator = ScriptedGenerator()  # would raise IndexError if called
    outcome = run(spec_at(tmp_path), impl, generator=generator, out_dir=tmp_path / "b")
    assert outcome.ok
    assert generator.prompts == []


def test_the_loop_gives_up_after_the_round_limit(tmp_path):
    generator = ScriptedGenerator(NAIVE, NAIVE, NAIVE)
    outcome = run(
        spec_at(tmp_path),
        tmp_path / "slugify.py",
        generator=generator,
        max_rounds=3,
        out_dir=tmp_path / "b",
    )
    assert not outcome.ok
    assert len(outcome.rounds) == 3


def test_a_generator_that_writes_nothing_is_reported(tmp_path):
    def generator(prompt: str, target: Path) -> None:
        return None

    outcome = run(
        spec_at(tmp_path), tmp_path / "missing.py", generator=generator, out_dir=tmp_path / "b"
    )
    assert not outcome.ok
    assert "did not write" in (outcome.rounds[0].error or "")


def test_a_spec_that_does_not_parse_never_calls_the_generator(tmp_path):
    path = tmp_path / "bad.spek"
    path.write_text("nonsense\n")
    generator = ScriptedGenerator()
    outcome = run(path, tmp_path / "x.py", generator=generator, out_dir=tmp_path / "b")
    assert not outcome.ok and generator.prompts == []


def test_command_generator_runs_a_shell_command(tmp_path):
    target = tmp_path / "written.py"
    generator = CommandGenerator(f"python3 -c \"open({str(target)!r}, 'w').write('x = 1')\"")
    generator("ignored prompt", target)
    assert target.read_text() == "x = 1"


def test_command_generator_surfaces_a_failure(tmp_path):
    generator = CommandGenerator("python3 -c \"raise SystemExit('nope')\"")
    try:
        generator("prompt", tmp_path / "x.py")
    except RuntimeError as exc:
        assert "nope" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a failing generator must raise")
