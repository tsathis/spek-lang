# The Python target

How a `.spek` file becomes something that runs. Everything here is
target-specific and deliberately kept out of `LANGUAGE.md`, which has a token
budget to hold.

## The outcome protocol

A signature declares outcomes. The generated test has to decide which one
actually happened, so the implementation and the verifier agree on this:

* **The first outcome is success.** Return normally.
* **Any other outcome** is signalled by raising an exception whose class name
  contains the outcome word -- `locked` is matched by `AccountLockedError` --
  or by returning a value tagged with it: an `.outcome` / `.status` / `.kind`
  attribute, an enum member, or a `(tag, value)` pair.
* An exception that matches nothing fails the test, and the failure message
  says what was expected and how to signal it.

`spek prompt` hands these rules to the model, so generated code is written
against them rather than guessed at.

### Overriding it

A project with its own conventions writes `spekconf.py` next to the
implementation:

```python
def classify(outcomes, result, exc):
    """Return an outcome name, or None to fall back to the default rules."""
    if isinstance(exc, MyFrameworkError):
        return exc.code
    return None
```

## Fixtures

Bare words in examples (`known`, `timeout`, `after_expire`) are fixtures. The
language has no way to describe what they are -- that is the point, and it is
ordinary Python instead. `spek build` and `spek verify` write a stub the first
time and never overwrite it:

```python
# spek_fixtures.py, beside the implementation
from spek.runtime import Fresh, implementation

FIXTURES = {
    "known": "ada@example.com",
    "right": "correct horse battery staple",
    "box": Fresh(list),      # rebuilt for each example
}
```

* `Fresh(factory)` is called per example, for mutable state that must not leak
  between cases.
* `implementation()` returns the *same* module object the tests call. Importing
  the implementation by name here would give you a second, unrelated copy, and
  patching that one changes nothing.
* A `NotImplemented` entry does not count as bound: `spek verify` reports it as
  `E205` by reading the file, never by importing it.

### Setup state

`name=value` where `name` is not a parameter is setup state. It reaches a hook:

```python
def setup(spec: str, bindings: dict) -> None:
    """Put the world into the state the example assumes."""
```

## The effects checker

Reads imports and calls with `ast`, resolves aliases, and follows calls into
module-local helpers. It stops at the module boundary and cannot see through
`getattr`, so it under-reports rather than over-reports.

| Finding | Code | Severity |
|---|---|---|
| uses something undeclared | `E101` | error |
| declares something it never does, with nothing to hide behind | `E103` | error |
| declares something it never does, but calls out through an import | `W301` | warning |
| keeps state without declaring `!mem` | `W308` | warning -- heuristic |

`!mem` is inferred from shape rather than from a name (module-level mutable
globals, `global`, `functools.lru_cache`, subscripting `self.x`), so it is only
ever a warning.

## Generated tests

One `Case` per example, one parametrised test per spec, written to `.spek/` by
default. They are rebuilt on every run: edit the spec, never the tests.

## Commands

```
spek check   spec.spek                  parse and lint the spec alone
spek build   spec.spek --impl impl.py   write the pytest module and a fixtures stub
spek effects spec.spek impl.py          effects only
spek verify  spec.spek impl.py          lint, effects, compile tests, run them
spek prompt  spec.spek --impl impl.py   the generation prompt, for any agent
spek loop    spec.spek --impl impl.py --agent 'claude -p'
```

Every command takes `--json`. Exit codes: `0` clean, `1` findings, `2` usage.
