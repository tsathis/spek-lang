# spek

**This is not a programming language.** It is a spec format that compiles to
*verification*. There is no runtime, no execution target, and it never
generates implementation code.

```
login(email, password) -> session | wrong | locked
  !db !hash
  : an unknown email and a bad password give the same outcome on purpose
  (known, right) ok
  (known, bad_pw) wrong
  (unknown, any) wrong
  (locked_acct, right) locked
```

Six lines of contract, plus one line of optional guidance. A reviewer knows in seconds that this touches the database, hashes
passwords, has three outcomes, and — critically — that `(unknown, any) wrong`
forbids user enumeration. The machine turns the same six lines into pytest
cases and a static effects check against whatever Python a model wrote.

## Why

Generation is not the bottleneck in AI-assisted development. Verification is.
Models write plausible code faster than anyone can review it, and the model
grading its own homework is not verification.

The usual response is to design a language for models to write. That fixes no
actual failure mode and throws away the training data that makes models good
at Python in the first place. So:

> **Do not compile the spec into implementation code. Compile it into
> verification.**

The model writes Python, where it is strongest. The spec describes only
*properties*, which is a far smaller language. The compiler's output is the
referee.

## Try it

```bash
pip install -e .
spek verify examples/demo/auth.spek examples/demo/auth.py
```

```
....                                                       [100%]
4 passed in 0.45s
login: 0 hatch(es) -- merge on green
OK
```

Now break the contract — make the implementation compare passwords with `==`
instead of hashing:

```
auth.spek:4:7: error E103: spec declares '!hash' but login never does it,
                           and calls nothing that could
    fix: implement it, or drop `!hash` from the spec
```

Or have it reach for the network it never declared:

```
auth.py:50:5: error E101: login uses 'requests.post', but the spec does not
                          declare '!net'
    fix: remove the call, or add `!net` to the spec
```

## What it checks

1. **Examples become tests.** Each `input outcome` line is one pytest case.
   Bare words like `known` are fixtures you bind in ordinary Python.
2. **Effects are checked statically.** `!net` on something that should not
   touch the network is a one-glance security review, and it is the only
   cheaply machine-checkable part of a spec.
3. **Drift is an error, not a convention.** A spec that declares `!hash` over
   code that never hashes has become a lie, and `spek` says so. This is the
   cheapest mechanical answer to spec drift we could find; it is partial, and
   the docs say where it stops.
4. **Hatches are counted.** `? atomic` marks a property examples cannot
   express. Nothing verifies it — the count is a triage signal on the PR.
5. **Notes are optional guidance.** `: reuse the retry helper in utils.py`
   reaches the model writing the code and the human reading the diff. Nothing
   checks a note and no note can fail a build — an example always wins.

| Hatches | Meaning |
|---|---|
| 0 | machine-verifiable; merge on green |
| 1–2 | a human must review the marked properties |
| more than examples | the spec is buying you little; write the code yourself |

## The loop

`spek` closes the generate → verify → repair loop without knowing anything
about any model vendor. It hands a prompt to whatever command you name and
checks what comes back:

```bash
spek loop auth.spek --impl auth.py --agent 'claude -p' --rounds 3
```

Every diagnostic is structured JSON with a stable code, the offending symbol,
and a suggested fix, because a retry loop reads these and prose is not a
protocol:

```bash
spek verify auth.spek auth.py --json
```

## What this is not

It does not verify that the spec is *correct* — nobody does. The claim is
narrower and worth stating plainly: **a spec is roughly twenty times smaller
than its implementation, so human attention goes further on it.** That is a
real but bounded win.

It also degrades honestly, and we measured where. Across six real-world flows
in `examples/complex/` — checkout, webhook delivery, password reset, rate
limiting, CSV import, a double-entry ledger — 21% of assertion lines came out
as hatches, and they were not spread evenly:

> **spek verifies leaves well and composition badly.** A function whose
> correctness is its own input/output behaviour is expressible. A function whose
> correctness is a claim about *how its calls relate to each other* is not.

`reserve_stock`, `debit` and `validate_header` need no hatches. `place_order`,
`transfer` and `import_rows` — the three functions that compose others — need
two each, and all three sit at the line-budget ceiling. The full write-up,
including two predictions the exercise falsified, is in
[`docs/LIMITS.md`](docs/LIMITS.md).

## Documentation

* [`docs/LANGUAGE.md`](docs/LANGUAGE.md) — the whole language, ~830 tokens,
  CI-gated at 1,200 so it always fits in a prompt
* [`docs/PYTHON.md`](docs/PYTHON.md) — the outcome protocol, fixtures, and how
  the effects checker works
* [`docs/LIMITS.md`](docs/LIMITS.md) — six real-world flows, and the measured
  point where the language stops working
* [`examples/`](examples/) — the specs from the design notes
* [`examples/complex/`](examples/complex/) — multi-function flows, strictly
  valid, hatches where spek could not reach
* [`examples/demo/`](examples/demo/) — a spec, an implementation, and fixtures
  that actually run

## Status

v0.1, Python target only. The portability claim — that the same spec verifies
a TypeScript implementation — is untested, and import analysis is exactly the
part that will not transfer cleanly.
