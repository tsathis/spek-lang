"""Checks on the spec itself, independent of any implementation.

Two jobs. The errors here catch specs that cannot mean anything (an example
naming three inputs for a two-parameter function). The warnings are the
review signal -- an outcome no example exercises is the failure path nobody
tested, and that is the single most useful thing this file reports.
"""

from __future__ import annotations

from .diagnostics import (
    E_ARITY_MISMATCH,
    E_DUPLICATE_EFFECT,
    E_DUPLICATE_OUTCOME,
    E_PARAM_BOUND_TWICE,
    W_DUPLICATE_EXAMPLE,
    W_HATCH_HEAVY,
    W_NO_EXAMPLES,
    W_OUTCOME_UNEXERCISED,
    W_OVER_BUDGET,
    W_TOO_MANY_NOTES,
    W_UNKNOWN_EFFECT,
    Diagnostic,
    error,
    warning,
)
from .effects.vocabulary import KNOWN_EFFECTS
from .spec_ast import Spec, SpecFile, literal_repr

#: Body lines a reviewer takes in at a glance. Past this the spec gets skimmed,
#: which defeats the point of having one.
LINE_BUDGET = 6

#: Notes sit outside the body budget -- charging them against it would just mean
#: nobody writes them. They get their own, tighter cap on a simple principle:
#: repo-wide guidance for an agent already belongs in CLAUDE.md, so a note here
#: is for guidance specific to this one function. Needing a fourth line is a
#: sign the guidance is not function-specific.
NOTE_BUDGET = 3


def lint_file(
    spec_file: SpecFile, line_budget: int = LINE_BUDGET, note_budget: int = NOTE_BUDGET
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    for spec in spec_file:
        diags.extend(lint(spec, line_budget=line_budget, note_budget=note_budget))
    return diags


def lint(
    spec: Spec, line_budget: int = LINE_BUDGET, note_budget: int = NOTE_BUDGET
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    diags.extend(_check_outcomes(spec))
    diags.extend(_check_effects(spec))
    diags.extend(_check_examples(spec))
    diags.extend(_check_coverage(spec))
    diags.extend(_check_budget(spec, line_budget, note_budget))
    return diags


def _check_outcomes(spec: Spec) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    seen: set[str] = set()
    for outcome in spec.signature.outcomes:
        if outcome in seen:
            diags.append(
                error(
                    E_DUPLICATE_OUTCOME,
                    f"outcome {outcome!r} is declared twice",
                    file=spec.file,
                    line=spec.signature.span.line,
                    col=spec.signature.span.col,
                    symbol=outcome,
                    fix="each outcome must be named once",
                )
            )
        seen.add(outcome)
    return diags


def _check_effects(spec: Spec) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    seen: set[str] = set()
    for effect in spec.effects:
        if effect.tag in seen:
            diags.append(
                error(
                    E_DUPLICATE_EFFECT,
                    f"effect '!{effect.tag}' is declared twice",
                    file=spec.file,
                    line=effect.span.line,
                    col=effect.span.col,
                    symbol=effect.tag,
                )
            )
        seen.add(effect.tag)
        if effect.tag not in KNOWN_EFFECTS:
            diags.append(
                warning(
                    W_UNKNOWN_EFFECT,
                    f"'!{effect.tag}' is not a checkable effect; it documents but verifies nothing",
                    file=spec.file,
                    line=effect.span.line,
                    col=effect.span.col,
                    symbol=effect.tag,
                    fix=f"known tags: {', '.join(sorted(KNOWN_EFFECTS))}",
                )
            )
    return diags


def _check_examples(spec: Spec) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    params = spec.signature.params
    seen_inputs: dict[tuple[str, ...], int] = {}

    for example in spec.examples:
        bound = [lit.name for lit in example.named if lit.name in params]
        supplied = len(example.positional) + len(bound)
        if supplied != len(params):
            setup = [lit.name for lit in example.named if lit.name not in params]
            note = f" ({', '.join(setup)} named no parameter)" if setup else ""
            diags.append(
                error(
                    E_ARITY_MISMATCH,
                    f"example supplies {supplied} input(s) for "
                    f"{len(params)} parameter(s){note}",
                    file=spec.file,
                    line=example.span.line,
                    col=example.span.col,
                    symbol=spec.name,
                    fix=f"give one input per parameter: ({', '.join(params)})",
                    extra={"params": list(params), "supplied": supplied},
                )
            )

        filled = set(params[: len(example.positional)])
        for named in example.named:
            if named.name in filled:
                diags.append(
                    error(
                        E_PARAM_BOUND_TWICE,
                        f"{named.name!r} is filled positionally and named again",
                        file=spec.file,
                        line=example.span.line,
                        col=example.span.col,
                        symbol=named.name,
                        fix=f"give {named.name!r} once: either in position or as {named.name}=...",
                    )
                )

        key = tuple(literal_repr(lit) for lit in example.inputs)
        if key in seen_inputs:
            diags.append(
                warning(
                    W_DUPLICATE_EXAMPLE,
                    f"the same input is already given on line {seen_inputs[key]}",
                    file=spec.file,
                    line=example.span.line,
                    col=example.span.col,
                    fix="drop the duplicate, or vary the input",
                )
            )
        else:
            seen_inputs[key] = example.span.line

    if not spec.examples:
        diags.append(
            warning(
                W_NO_EXAMPLES,
                f"{spec.name} has no examples; nothing about it is executable",
                file=spec.file,
                line=spec.signature.span.line,
                col=spec.signature.span.col,
                symbol=spec.name,
                fix="add at least one `input outcome` line",
            )
        )
    return diags


def _check_coverage(spec: Spec) -> list[Diagnostic]:
    """An outcome no example reaches is an untested failure path."""
    exercised = {example.outcome for example in spec.examples}
    diags: list[Diagnostic] = []
    for outcome in spec.signature.outcomes:
        if outcome in exercised:
            continue
        diags.append(
            warning(
                W_OUTCOME_UNEXERCISED,
                f"no example produces outcome {outcome!r}",
                file=spec.file,
                line=spec.signature.span.line,
                col=spec.signature.span.col,
                symbol=outcome,
                fix=f"add an example ending in `{outcome}`, or drop the outcome",
            )
        )
    return diags


def _check_budget(spec: Spec, line_budget: int, note_budget: int) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    if spec.body_lines > line_budget:
        diags.append(
            warning(
                W_OVER_BUDGET,
                f"{spec.body_lines} body lines exceeds the {line_budget}-line budget; "
                "a spec this long gets skimmed",
                file=spec.file,
                line=spec.signature.span.line,
                col=spec.signature.span.col,
                symbol=spec.name,
                fix="split the function, or drop the examples that pin the same behaviour",
                extra={"body_lines": spec.body_lines, "budget": line_budget},
            )
        )
    if spec.note_lines > note_budget:
        diags.append(
            warning(
                W_TOO_MANY_NOTES,
                f"{spec.note_lines} notes exceeds the {note_budget}-note budget; "
                "guidance this general is not specific to this function",
                file=spec.file,
                line=spec.notes[note_budget].span.line,
                col=spec.notes[note_budget].span.col,
                symbol=spec.name,
                fix="move repo-wide guidance into CLAUDE.md and keep notes to this function",
                extra={"notes": spec.note_lines, "budget": note_budget},
            )
        )
    if spec.hatches and len(spec.hatches) > len(spec.examples):
        diags.append(
            warning(
                W_HATCH_HEAVY,
                f"{len(spec.hatches)} hatches to {len(spec.examples)} examples; "
                "the spec is buying you little here",
                file=spec.file,
                line=spec.signature.span.line,
                col=spec.signature.span.col,
                symbol=spec.name,
                fix="this function's correctness is a relation, not a set of points -- "
                "review it by hand",
            )
        )
    return diags


def triage(spec: Spec) -> str:
    """The `?`-count signal a reviewer reads first."""
    count = len(spec.hatches)
    if count == 0:
        return "machine-verifiable"
    if count <= 2:
        return "needs-review"
    return "hand-written"
