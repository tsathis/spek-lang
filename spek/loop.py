"""Generate, verify, repair, repeat.

The driver is deliberately thin and knows nothing about any model vendor. It
shells out to whatever command you name, hands it a prompt on stdin, and
expects the implementation file to exist afterwards. Everything interesting --
deciding whether the code is right -- happens in `verify`.
"""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .prompt import generation_prompt, repair_prompt
from .verify import Result, verify


class Generator(Protocol):
    """Anything that can turn a prompt into an implementation file."""

    def __call__(self, prompt: str, target: Path) -> None: ...


@dataclass
class CommandGenerator:
    """Runs a shell command with the prompt on stdin.

    The command is responsible for writing `target`; spek only checks that it
    did. `spek loop spec.spek --impl auth.py --agent 'claude -p'` is the
    intended shape.
    """

    command: str
    timeout: int = 900
    cwd: Path | None = None

    def __call__(self, prompt: str, target: Path) -> None:
        completed = subprocess.run(
            shlex.split(self.command),
            input=prompt,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            cwd=str(self.cwd) if self.cwd else None,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"generator exited {completed.returncode}: "
                f"{(completed.stderr or completed.stdout).strip()[:2000]}"
            )


@dataclass
class Round:
    index: int
    prompt: str
    result: Result | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.result is not None and self.result.ok

    def as_dict(self) -> dict[str, object]:
        body: dict[str, object] = {"round": self.index, "ok": self.ok}
        if self.error:
            body["error"] = self.error
        if self.result is not None:
            body["summary"] = self.result.summary()
            body["diagnostics"] = [d.to_dict() for d in self.result.diagnostics]
        return body


@dataclass
class LoopOutcome:
    rounds: list[Round] = field(default_factory=list)
    final: Result | None = None

    @property
    def ok(self) -> bool:
        return self.final is not None and self.final.ok

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "rounds": [r.as_dict() for r in self.rounds],
            "triage": self.final.triage if self.final else {},
        }


def run(
    spec_path: str | Path,
    impl_path: str | Path,
    generator: Generator,
    max_rounds: int = 3,
    out_dir: str | Path = ".spek",
    on_round: Callable[[Round], None] | None = None,
) -> LoopOutcome:
    """Drive a model to an implementation the spec accepts.

    Round 1 generates from scratch unless the file already exists, in which
    case the loop starts by verifying what is there -- so a human-written
    implementation gets repaired rather than overwritten.
    """
    spec_path, impl_path = Path(spec_path), Path(impl_path)
    outcome = LoopOutcome()

    from .parser import parse_file

    spec_file, parse_diags = parse_file(str(spec_path))
    if any(d.is_error for d in parse_diags):
        outcome.final = Result(spec_file=None, diagnostics=parse_diags)
        return outcome

    for index in range(1, max_rounds + 1):
        if not impl_path.exists():
            prompt = generation_prompt(spec_file, str(impl_path))
        elif outcome.rounds:
            previous = outcome.rounds[-1].result
            prompt = repair_prompt(
                spec_file,
                str(impl_path),
                list(previous.diagnostics) if previous else [],
                previous.test_output if previous else None,
            )
        else:
            prompt = ""  # verify what is already on disk before asking for anything

        if prompt:
            try:
                generator(prompt, impl_path)
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                round_ = Round(index=index, prompt=prompt, result=None, error=str(exc))
                outcome.rounds.append(round_)
                if on_round:
                    on_round(round_)
                break
            if not impl_path.exists():
                round_ = Round(
                    index=index,
                    prompt=prompt,
                    result=None,
                    error=f"generator did not write {impl_path}",
                )
                outcome.rounds.append(round_)
                if on_round:
                    on_round(round_)
                break

        result = verify(spec_path, impl_path, out_dir=out_dir)
        round_ = Round(index=index, prompt=prompt, result=result)
        outcome.rounds.append(round_)
        outcome.final = result
        if on_round:
            on_round(round_)
        if result.ok:
            break

    return outcome
