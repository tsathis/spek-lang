"""Command line entry point.

Every command takes `--json`, because the retry loop reads these outputs and
prose is not a protocol.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .diagnostics import Diagnostic, to_json
from .effects.python import check as check_effects
from .lint import LINE_BUDGET, triage
from .loop import CommandGenerator, Round
from .loop import run as run_loop
from .parser import parse_file
from .prompt import generation_prompt
from .verify import DEFAULT_BUILD_DIR, Result, build, check_spec, verify

OK, FINDINGS, USAGE = 0, 1, 2


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "handler", None):
        parser.print_help()
        return USAGE
    try:
        return args.handler(args)
        return USAGE


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spek",
        description="A spec format that compiles to verification, not to code.",
    )
    parser.add_argument("--version", action="version", version=f"spek {__version__}")
    subs = parser.add_subparsers(dest="command")

    check = subs.add_parser("check", help="parse and lint a spec on its own")
    check.add_argument("spec")
    check.add_argument("--budget", type=int, default=LINE_BUDGET, help="body-line budget")
    _json_flag(check)
    check.set_defaults(handler=_cmd_check)

    build_cmd = subs.add_parser("build", help="compile a spec into a pytest module")
    build_cmd.add_argument("spec")
    build_cmd.add_argument("--impl", required=True, help="implementation the tests will exercise")
    build_cmd.add_argument("--out", default=DEFAULT_BUILD_DIR, help="directory for generated tests")
    build_cmd.add_argument(
        "--no-fixtures", action="store_true", help="do not write a fixtures stub"
    )
    _json_flag(build_cmd)
    build_cmd.set_defaults(handler=_cmd_build)

    effects = subs.add_parser("effects", help="check declared effects against an implementation")
    effects.add_argument("spec")
    effects.add_argument("impl")
    effects.add_argument("--show", action="store_true", help="list everything observed")
    _json_flag(effects)
    effects.set_defaults(handler=_cmd_effects)

    verify_cmd = subs.add_parser("verify", help="lint, check effects, compile tests, run them")
    verify_cmd.add_argument("spec")
    verify_cmd.add_argument("impl")
    verify_cmd.add_argument("--out", default=DEFAULT_BUILD_DIR)
    verify_cmd.add_argument("--no-tests", action="store_true", help="skip running pytest")
    verify_cmd.add_argument("--no-fixtures", action="store_true")
    _json_flag(verify_cmd)
    verify_cmd.set_defaults(handler=_cmd_verify)

    prompt = subs.add_parser("prompt", help="print the generation prompt for a spec")
    prompt.add_argument("spec")
    prompt.add_argument("--impl", required=True)
    prompt.set_defaults(handler=_cmd_prompt)

    loop = subs.add_parser("loop", help="generate, verify and repair until the spec accepts")
    loop.add_argument("spec")
    loop.add_argument("--impl", required=True)
    loop.add_argument("--agent", required=True, help="command that writes --impl from stdin")
    loop.add_argument("--rounds", type=int, default=3)
    loop.add_argument("--out", default=DEFAULT_BUILD_DIR)
    _json_flag(loop)
    loop.set_defaults(handler=_cmd_loop)

    return parser


def _json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="structured output for tooling")


# --- commands ---------------------------------------------------------------


def _cmd_check(args: argparse.Namespace) -> int:
    result = check_spec(args.spec, line_budget=args.budget)
    return _report(result, args.json, label=f"check {args.spec}")


def _cmd_build(args: argparse.Namespace) -> int:
    result, tests_path = build(
        args.spec, args.impl, out_dir=args.out, write_fixtures=not args.no_fixtures
    )
    if args.json:
        print(
            to_json(
                result.diagnostics,
                tests=str(tests_path) if tests_path else None,
                triage=result.triage,
                summary=result.summary(),
            )
        )
    else:
        _print_diagnostics(result.diagnostics)
        if tests_path:
            print(f"wrote {tests_path}")
        _print_triage(result)
    return OK if not _errors(result.diagnostics) else FINDINGS


def _cmd_effects(args: argparse.Namespace) -> int:
    spec_file, diags = parse_file(args.spec)
    observations = []
    if not _errors(diags):
        source = Path(args.impl).read_text(encoding="utf-8")
        for spec in spec_file:
            spec_diags, spec_obs = check_effects(spec, source, args.impl)
            diags.extend(spec_diags)
            observations.extend(spec_obs)

    if args.json:
        print(to_json(diags, observed=[o.as_dict() for o in observations]))
    else:
        _print_diagnostics(diags)
        if args.show:
            for obs in observations:
                print(f"  !{obs.tag:6} {obs.symbol}  ({args.impl}:{obs.line}, in {obs.via})")
        if not diags:
            declared = ", ".join(f"!{t}" for s in spec_file for t in s.effect_tags) or "none"
            print(f"effects match: {declared}")
    return OK if not _errors(diags) else FINDINGS


def _cmd_verify(args: argparse.Namespace) -> int:
    result = verify(
        args.spec,
        args.impl,
        out_dir=args.out,
        run_tests=not args.no_tests,
        write_fixtures=not args.no_fixtures,
    )
    if args.json:
        print(
            to_json(
                result.diagnostics,
                summary=result.summary(),
                triage=result.triage,
                tests=str(result.tests_path) if result.tests_path else None,
                test_output=result.test_output or None,
            )
        )
        return OK if result.ok else FINDINGS

    _print_diagnostics(result.diagnostics)
    if result.tests_ran:
        print(_tail(result.test_output))
    elif not args.no_tests:
        print("tests not run: fix the errors above first")
    _print_triage(result)
    print("OK" if result.ok else "FAILED")
    return OK if result.ok else FINDINGS


def _cmd_prompt(args: argparse.Namespace) -> int:
    spec_file, diags = parse_file(args.spec)
    if _errors(diags):
        _print_diagnostics(diags)
        return FINDINGS
    print(generation_prompt(spec_file, args.impl))
    return OK


def _cmd_loop(args: argparse.Namespace) -> int:
    def announce(round_: Round) -> None:
        if args.json:
            return
        if round_.error:
            print(f"round {round_.index}: {round_.error}", file=sys.stderr)
        elif round_.result is not None:
            summary = round_.result.summary()
            print(
                f"round {round_.index}: {summary['errors']} error(s), "
                f"{summary['warnings']} warning(s), "
                f"tests {'passed' if summary['tests_passed'] else 'failed'}"
            )

    outcome = run_loop(
        args.spec,
        args.impl,
        generator=CommandGenerator(args.agent),
        max_rounds=args.rounds,
        out_dir=args.out,
        on_round=announce,
    )

    if args.json:
        print(json.dumps(outcome.as_dict(), indent=2))
    else:
        if outcome.final is not None:
            _print_diagnostics(outcome.final.diagnostics)
            _print_triage(outcome.final)
        print("OK" if outcome.ok else "FAILED")
    return OK if outcome.ok else FINDINGS


# --- output -----------------------------------------------------------------


def _errors(diags: list[Diagnostic]) -> int:
    return sum(1 for d in diags if d.is_error)


def _report(result: Result, as_json: bool, label: str) -> int:
    if as_json:
        print(to_json(result.diagnostics, summary=result.summary(), triage=result.triage))
    else:
        _print_diagnostics(result.diagnostics)
        _print_triage(result)
        if not result.diagnostics:
            print(f"{label}: clean")
    return OK if not _errors(result.diagnostics) else FINDINGS


def _print_diagnostics(diags: list[Diagnostic]) -> None:
    for diagnostic in diags:
        stream = sys.stderr if diagnostic.is_error else sys.stdout
        print(diagnostic.render(), file=stream)


def _print_triage(result: Result) -> None:
    if result.spec_file is None:
        return
    for spec in result.spec_file:
        hatches = len(spec.hatches)
        note = {
            "machine-verifiable": "merge on green",
            "needs-review": "a human must check the marked properties",
            "hand-written": "the spec is buying you little; review this by hand",
        }[triage(spec)]
        print(f"{spec.name}: {hatches} hatch(es) -- {note}")


def _tail(output: str, lines: int = 25) -> str:
    rows = output.strip().splitlines()
    if len(rows) <= lines:
        return "\n".join(rows)
    return "\n".join(["...", *rows[-lines:]])


if __name__ == "__main__":
    raise SystemExit(main())
