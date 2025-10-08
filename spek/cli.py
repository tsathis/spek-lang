"""Command line interface."""

import argparse
import json
from pathlib import Path

from spek.parser import Parser
from spek.lint import Linter
from spek.verify import Verifier


def main():
    parser = argparse.ArgumentParser(prog="spek")
    sub = parser.add_subparsers(dest="command")

    check = sub.add_parser("check")
    check.add_argument("spec")
    check.add_argument("--json", action="store_true")

    verify = sub.add_parser("verify")
    verify.add_argument("spec")
    verify.add_argument("impl")
    verify.add_argument("--json", action="store_true")

    prompt = sub.add_parser("prompt")
    prompt.add_argument("spec")
    prompt.add_argument("--impl")

    loop = sub.add_parser("loop")
    loop.add_argument("spec")
    loop.add_argument("--impl", required=True)
    loop.add_argument("--agent", required=True)
    loop.add_argument("--rounds", type=int, default=3)

    args = parser.parse_args()

    if args.command == "check":
        text = Path(args.spec).read_text()
        module = Parser(text).parse()
        diags = Linter().lint_module(module)
        for d in diags.items:
            print(f"{args.spec}:{d.line}: {d.severity.value}: {d.code}: {d.message}")
        return 1 if diags.has_errors() else 0

    if args.command == "verify":
        text = Path(args.spec).read_text()
        diags = Verifier().verify(text, args.impl)
        for d in diags.items:
            print(f"{args.spec}:{d.line}: {d.severity.value}: {d.code}: {d.message}")
        return 1 if diags.has_errors() else 0

    if args.command == "prompt":
        text = Path(args.spec).read_text()
        module = Parser(text).parse()
        from spek.prompt import PromptGenerator
        for spec in module.specs:
            print(PromptGenerator(spec).generation_prompt())
        return 0

    if args.command == "loop":
        text = Path(args.spec).read_text()
        module = Parser(text).parse()
        from spek.loop import Loop
        ok = True
        for spec in module.specs:
            l = Loop(spec, args.impl, args.agent, max_rounds=args.rounds)
            ok = ok and l.run()
        return 0 if ok else 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    exit(main())
