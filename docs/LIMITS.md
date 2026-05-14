# Where spek stops working

Six real-world flows, written as specs under the current grammar, with hatches
wherever the language could not reach. Every file in `examples/complex/` passes
`spek check` cleanly — no errors, no warnings, nothing over the line budget.

This document is the result of that exercise, including the parts that
contradicted what we expected going in.

## The numbers

18 specs across 6 unrelated domains: 48 examples, 13 hatches, 6 notes.

| File | Specs | Examples | Hatches | Machine-verifiable |
|---|---:|---:|---:|---:|
| `checkout.spek` | 4 | 11 | 3 | 2 / 4 |
| `webhook_delivery.spek` | 3 | 7 | 2 | 2 / 3 |
| `password_reset.spek` | 3 | 10 | 2 | 1 / 3 |
| `rate_limit.spek` | 2 | 5 | 2 | 1 / 2 |
| `csv_import.spek` | 3 | 7 | 2 | 2 / 3 |
| `ledger.spek` | 3 | 8 | 2 | 2 / 3 |
| **total** | **18** | **48** | **13** | **10 / 18** |

Hatches are **21%** of all assertion lines. 0.72 hatches per spec. Ten of
eighteen specs came out fully machine-verifiable.

## Three predictions, two wrong

**"Expect 50–70% hatches." Wrong — it is 21%.** The language reaches further
into real backend logic than we assumed. More than half the specs needed no
hatch at all.

**"The six-line budget will bind." Wrong — nothing exceeded it.** The largest
spec is exactly 6 body lines and there are four of them. The budget is tight
but it did not force a single unnatural split. One caveat: every spec carrying
hatches landed at 5 or 6 body lines, so hatches are what push a spec to the
edge. A function needing three hatches would not fit, and that has not happened
yet.

**"Named states may not scale." Wrong — they scaled fine.** `password_reset`
was written specifically to break this. `validate_token` sequences four
distinct points in a multi-step flow using nothing but `fresh`,
`after_15min`, `after_complete` and `tampered`, and came out with **zero
hatches**. The `cache.get` trick survived contact with a real stateful process.

## What actually broke: composition

The hatches are not spread evenly. They concentrate at one specific place —
**the function that composes other functions.**

| Composed function | Composes | Hatches |
|---|---|---:|
| `place_order` | `reserve_stock` + `charge_card` | 2 |
| `transfer` | `debit` + `credit` | 2 |
| `import_rows` | `validate_header` + per-row writes | 2 |

All three are at the 6-line budget ceiling. All three have exactly two hatches.
Their leaf functions are mostly clean: `reserve_stock`, `debit`, `credit`,
`validate_header` and `enqueue` are all fully machine-verifiable.

The honest summary is sharper than "correctness that is a relation degrades to
comments." It is:

> **spek verifies leaves well and composition badly.** A function whose
> correctness is its own input/output behaviour is expressible. A function whose
> correctness is a claim about *how its calls relate to each other* is not.

## The properties that recur

Grouped across all six domains, the 13 hatches are:

| Property | Where it appeared | Count |
|---|---|---:|
| **Atomicity** — these commit together or not at all | `place_order`, `transfer`, `import_rows` | 3 |
| **Temporal** — backoff, expiry, continuous accrual | `attempt_delivery`, `request_reset`, `refill` | 4 |
| **Idempotency** — calling twice equals calling once | `charge_card` | 1 |
| **Compensation** — undo the earlier step when a later one fails | `place_order` | 1 |
| **Cross-entity invariants** — money is conserved, sessions revoked | `transfer`, `complete_reset` | 2 |
| **Resource bounds** — constant memory | `import_rows` | 1 |
| **Classification** — which errors retry and which do not | `attempt_delivery` | 1 |

**Atomicity is the leading candidate for a real construct.** It appeared in
three domains that share nothing — commerce, accounting, and batch import — and
in each case it was the property a reviewer would most want checked.

The bar set in advance was *a property appearing in four of six files justifies
new syntax*. Atomicity reaches three. **It does not clear the bar**, and on the
evidence here no new construct is warranted yet. Temporal properties reach four
occurrences but across only three files, and they are the ones formal methods
handles and this design explicitly gave up on.

## What this says about the thesis

The claim spek makes is that a spec is ~20× smaller than its implementation, so
human attention goes further. This exercise supports a narrower and more useful
version:

- For **leaf functions** — parse, validate, look up, hash, one write — examples
  plus effect tags genuinely do the job, and the hatch count is zero.
- For **orchestrators** — the function that calls three others and has to get
  the failure paths right — spek pins the happy path and the outcome taxonomy,
  and then hands a reviewer two sentences of English and says "check these."

That second case is still worth something: two marked properties on a
six-line spec is a far better review surface than a 200-line function with
nothing marked. But it is not verification, and the `?` count says so honestly.

## What was not tested

No implementations were written against these specs. This measures what the
*language* can express, not whether a model produces correct code from it.
That is still the open question from the original research notes — take twenty
functions, generate, and count how many come out right — and `spek loop` is the
harness for it.
