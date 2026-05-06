"""The terseness gate.

The whole thesis is that a spec is small enough to read and small enough to
paste into a prompt. If the language reference itself sprawls, the argument
is already lost -- so the size is a test, not an aspiration.
"""

import math
import re
from pathlib import Path

#: The budget from the design notes: the full language reference, prose
#: included, fits in this many tokens.
TOKEN_BUDGET = 1200

DOCS = Path(__file__).resolve().parent.parent / "docs"
EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def estimate_tokens(text: str) -> int:
    """A deterministic stand-in for a tokenizer.

    Two rough models of BPE, whichever is larger: four characters per token,
    and 1.3 tokens per whitespace-delimited word. No dependency, no drift
    between tokenizer versions, and it errs high on the table- and
    code-heavy text this file is guarding.
    """
    chars = math.ceil(len(text) / 4)
    words = math.ceil(len(re.findall(r"\S+", text)) * 1.3)
    return max(chars, words)


def test_the_language_reference_fits_in_a_prompt():
    reference = (DOCS / "LANGUAGE.md").read_text(encoding="utf-8")
    tokens = estimate_tokens(reference)
    assert tokens <= TOKEN_BUDGET, (
        f"docs/LANGUAGE.md is ~{tokens} tokens, over the {TOKEN_BUDGET} budget. "
        "Cut something before adding something."
    )


def test_the_generation_prompt_conventions_stay_small():
    from spek.prompt import CONVENTIONS

    assert estimate_tokens(CONVENTIONS) <= 500


#: The grammar was nine productions in v0.1. The note line made it ten. Any
#: further growth should be an argued decision, not a drift -- hence the exact
#: assertion rather than an upper bound.
GRAMMAR_PRODUCTIONS = 10


def test_the_grammar_has_not_grown_unnoticed():
    reference = (DOCS / "LANGUAGE.md").read_text(encoding="utf-8")
    grammar = reference.split("```ebnf")[1].split("```")[0]
    productions = [line for line in grammar.splitlines() if "=" in line]
    assert len(productions) == GRAMMAR_PRODUCTIONS, productions


def test_every_example_spec_stays_within_the_line_budget():
    """Covers examples/complex/ too -- the real-world specs get no exemption.

    A scenario that cannot fit is a finding to bring back, not a budget to
    raise. See docs/LIMITS.md.
    """
    from spek.lint import LINE_BUDGET, NOTE_BUDGET
    from spek.parser import parse_file

    seen = 0
    for path in sorted(EXAMPLES.rglob("*.spek")):
        if not path.is_file():
            continue  # `.spek/` build directories share the suffix
        spec_file, diags = parse_file(str(path))
        assert not [d for d in diags if d.is_error], path
        for spec in spec_file:
            seen += 1
            assert spec.body_lines <= LINE_BUDGET, f"{path}: {spec.name}"
            assert spec.note_lines <= NOTE_BUDGET, f"{path}: {spec.name}"
    assert seen >= 25, "expected the complex examples to be covered too"


def test_the_complex_examples_are_clean():
    """They are the stress test, so they must pass with no findings at all."""
    from spek.verify import check_spec

    paths = sorted((EXAMPLES / "complex").glob("*.spek"))
    assert len(paths) == 6
    for path in paths:
        result = check_spec(path)
        assert result.diagnostics == [], [d.render() for d in result.diagnostics]
