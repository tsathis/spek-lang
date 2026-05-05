"""Prompts for the model that writes the implementation.

Two of them. `generation_prompt` is issued once and carries the spec plus the
conventions the verifier will hold the code to. `repair_prompt` is issued on
every failed round and carries the structured diagnostics -- it deliberately
restates nothing the model already has, because the diagnostics are the whole
message.
"""

from __future__ import annotations

from .diagnostics import Diagnostic
from .spec_ast import Spec, SpecFile

CONVENTIONS = """\
How the spec is verified. Write the implementation to satisfy these rules.

Outcomes
  `name(args) -> a | b | c` declares the outcomes. The first one, `a`, is
  success: return normally. Any other outcome must be signalled by raising an
  exception whose class name contains that word -- outcome `locked` is matched
  by `AccountLockedError` -- or by returning a value tagged with it via an
  `.outcome` attribute, an enum, or a `(tag, value)` pair. Pick one convention
  and use it throughout the module.

Effects
  `!tag` lines declare every effect the function is allowed to have, directly
  or through any helper it calls in the same module. The checker reads imports
  and calls. Using something the spec does not declare is an error; declaring
  something the code never uses is a warning. The tags are:
    !net   network        !fs    filesystem      !db   database
    !proc  subprocesses   !env   environment     !clock wall-clock time
    !rand  randomness     !hash  hashing/crypto  !io   console
    !ai    model calls    !mem   state kept between calls

Examples
  `input outcome` lines are test cases. Bare words like `known` or `timeout`
  are fixtures bound elsewhere -- treat them as ordinary values of the right
  shape, and do not special-case them by name. A line ending in a literal
  (`"Hello World" "hello-world"`) pins the exact return value.

Hatches
  `? free text` marks a property the tests cannot check. Implement it. Nothing
  will verify that you did, so it is where a reviewer will look hardest.

Notes
  `: free text` is optional guidance -- a pointer to an existing helper, what a
  fixture word means, why an order matters. Nothing verifies a note and no note
  can fail the build, so follow one where it helps and ignore it where it would
  fight an example. An example always wins over a note.
"""


def _render_spec(spec: Spec) -> str:
    params = ", ".join(spec.signature.params)
    outcomes = " | ".join(spec.signature.outcomes)
    lines = [f"{spec.name}({params}) -> {outcomes}"]
    if spec.effects:
        lines.append("  " + " ".join(f"!{tag}" for tag in spec.effect_tags))
    for example in spec.examples:
        shown = ", ".join(_literal(lit) for lit in example.inputs)
        wrapped = f"({shown})" if len(example.inputs) != 1 else shown
        tail = example.outcome if example.expect is None else _literal(example.expect)
        lines.append(f"  {wrapped} {tail}".rstrip())
    for note in spec.notes:
        lines.append(f"  : {note.text}")
    for hatch in spec.hatches:
        lines.append(f"  ? {hatch.text}")
    return "\n".join(lines)


def _literal(lit) -> str:
    from .spec_ast import literal_repr

    return literal_repr(lit)


def generation_prompt(spec_file: SpecFile, target_path: str, language: str = "Python") -> str:
    specs = "\n\n".join(_render_spec(spec) for spec in spec_file)
    names = ", ".join(spec.name for spec in spec_file)
    return f"""\
Write {language} implementing the following spec, into {target_path}.

{specs}

{CONVENTIONS}
Write only {target_path}. Define {names} and whatever private helpers they
need. Do not write tests -- the spec compiles to those.
"""


def repair_prompt(
    spec_file: SpecFile,
    target_path: str,
    diagnostics: list[Diagnostic],
    test_output: str | None = None,
) -> str:
    specs = "\n\n".join(_render_spec(spec) for spec in spec_file)
    findings = "\n".join(f"  {d.render()}" for d in diagnostics) or "  (none)"
    sections = [
        f"{target_path} does not satisfy its spec. Fix it.",
        "",
        specs,
        "",
        "Findings:",
        findings,
    ]
    if test_output:
        sections.extend(["", "Test output:", _indent(test_output.strip())])
    sections.extend(
        [
            "",
            "Change only what the findings call for. Do not edit the spec, and do not",
            "edit the generated tests -- they are rebuilt from the spec on every run.",
        ]
    )
    return "\n".join(sections)


def _indent(text: str, prefix: str = "  ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())
