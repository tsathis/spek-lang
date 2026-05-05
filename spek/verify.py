"""The referee: spec in, implementation in, verdict out.

Order matters. Parse errors stop everything, because a spec that does not mean
anything cannot judge code. Effects are checked before tests run, since an
undeclared `!net` is a finding a reviewer wants whether or not the examples
happen to pass.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .codegen.python import fixtures_stub, generate_tests
from .diagnostics import (
    E_UNBOUND_SYMBOL,
    Diagnostic,
    error,
    has_errors,
)
from .effects.python import Observation
from .effects.python import check as check_effects
from .lint import lint_file, triage
from .parser import parse_file
from .spec_ast import SpecFile

FIXTURES_FILENAME = "spek_fixtures.py"
DEFAULT_BUILD_DIR = ".spek"


@dataclass
class Result:
    spec_file: SpecFile | None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
    tests_path: Path | None = None
    test_output: str = ""
    tests_ran: bool = False
    tests_passed: bool = False

    @property
    def ok(self) -> bool:
        if has_errors(self.diagnostics):
            return False
        return self.tests_passed if self.tests_ran else True

    @property
    def triage(self) -> dict[str, dict[str, object]]:
        if self.spec_file is None:
            return {}
        return {
            spec.name: {
                "triage": triage(spec),
                "hatches": [h.text for h in spec.hatches],
                "examples": len(spec.examples),
            }
            for spec in self.spec_file
        }

    def summary(self) -> dict[str, object]:
        errors = sum(1 for d in self.diagnostics if d.is_error)
        return {
            "ok": self.ok,
            "errors": errors,
            "warnings": len(self.diagnostics) - errors,
            "hatches": sum(len(v["hatches"]) for v in self.triage.values()),  # type: ignore[arg-type]
            "tests_ran": self.tests_ran,
            "tests_passed": self.tests_passed,
        }


def check_spec(spec_path: str | Path, line_budget: int | None = None) -> Result:
    """Parse and lint a spec on its own -- no implementation needed."""
    spec_file, diags = parse_file(str(spec_path))
    if has_errors(diags):
        return Result(spec_file=None, diagnostics=diags)
    kwargs = {"line_budget": line_budget} if line_budget is not None else {}
    diags.extend(lint_file(spec_file, **kwargs))
    return Result(spec_file=spec_file, diagnostics=diags)


def build(
    spec_path: str | Path,
    impl_path: str | Path,
    out_dir: str | Path = DEFAULT_BUILD_DIR,
    write_fixtures: bool = True,
) -> tuple[Result, Path | None]:
    """Compile a spec into a pytest module (and a fixtures stub, if missing)."""
    result = check_spec(spec_path)
    if result.spec_file is None:
        return result, None
    tests_path = _emit(result, spec_path, impl_path, out_dir, write_fixtures)
    return result, tests_path


def _emit(
    result: Result,
    spec_path: str | Path,
    impl_path: str | Path,
    out_dir: str | Path,
    write_fixtures: bool,
) -> Path:
    """Write the generated tests, and the fixtures stub when there is none yet."""
    assert result.spec_file is not None
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tests_path = out / f"test_{Path(spec_path).stem}_spek.py"
    tests_path.write_text(
        generate_tests(result.spec_file, str(impl_path), tests_path), encoding="utf-8"
    )
    result.tests_path = tests_path

    if write_fixtures:
        fixtures_path = Path(impl_path).resolve().parent / FIXTURES_FILENAME
        if not fixtures_path.exists() and any(spec.symbols for spec in result.spec_file):
            fixtures_path.write_text(fixtures_stub(result.spec_file), encoding="utf-8")
    return tests_path


def verify(
    spec_path: str | Path,
    impl_path: str | Path,
    out_dir: str | Path = DEFAULT_BUILD_DIR,
    run_tests: bool = True,
    write_fixtures: bool = True,
) -> Result:
    """Full pass: parse, lint, check effects, compile tests, run them."""
    spec_path, impl_path = Path(spec_path), Path(impl_path)
    result = check_spec(spec_path)
    if result.spec_file is None:
        return result

    source = impl_path.read_text(encoding="utf-8")
    for spec in result.spec_file:
        diags, observations = check_effects(spec, source, str(impl_path))
        result.diagnostics.extend(diags)
        result.observations.extend(observations)

    result.diagnostics.extend(_check_fixtures(result.spec_file, impl_path))
    tests_path = _emit(result, spec_path, impl_path, out_dir, write_fixtures)

    if run_tests and not has_errors(result.diagnostics):
        result.tests_ran = True
        result.tests_passed, result.test_output = run_pytest(tests_path)

    return result


def run_pytest(tests_path: Path) -> tuple[bool, str]:
    completed = subprocess.run(
        [
            sys.executable, "-m", "pytest", str(tests_path),
            "-q", "--no-header", "-p", "no:cacheprovider",
        ],
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0, completed.stdout + completed.stderr


def _check_fixtures(spec_file: SpecFile, impl_path: Path) -> list[Diagnostic]:
    """Report unbound symbols by reading the fixtures file, never importing it."""
    required: dict[str, str] = {}
    for spec in spec_file:
        for symbol in spec.symbols:
            required.setdefault(symbol, spec.name)
    if not required:
        return []

    fixtures_path = impl_path.resolve().parent / FIXTURES_FILENAME
    bound = _fixture_keys(fixtures_path)

    return [
        error(
            E_UNBOUND_SYMBOL,
            f"example symbol {symbol!r} has no fixture",
            file=str(fixtures_path),
            symbol=symbol,
            fix=f"add {symbol!r} to FIXTURES in {FIXTURES_FILENAME}",
            extra={"spec": owner},
        )
        for symbol, owner in required.items()
        if symbol not in bound
    ]


def _fixture_keys(path: Path) -> set[str]:
    """Statically read the keys of `FIXTURES = {...}` without executing anything."""
    if not path.exists():
        return set()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return set()

    keys: set[str] = set()
    for node in ast.walk(tree):
        targets = (
            node.targets
            if isinstance(node, ast.Assign)
            else [node.target]
            if isinstance(node, ast.AnnAssign)
            else []
        )
        if not any(isinstance(t, ast.Name) and t.id == "FIXTURES" for t in targets):
            continue
        value = node.value
        if isinstance(value, ast.Dict):
            for key, bound in zip(value.keys, value.values, strict=False):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    if isinstance(bound, ast.Name) and bound.id == "NotImplemented":
                        continue  # a stub entry is not a binding
                    keys.add(key.value)
    return keys
