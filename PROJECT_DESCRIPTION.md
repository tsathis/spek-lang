# spek: Project Description and Development Context

## Project Identity

**spek** is a Python developer tool and compact specification format for AI-assisted software development. It is intentionally **not** a general-purpose programming language and it does not generate implementation code. Instead, it compiles short human-readable specifications into verification artifacts that judge ordinary implementation code, primarily Python.

The central design principle is:

> Let an AI model write code in the language it already knows well, and use a small, explicit specification as the machine-readable referee.

The project addresses a practical problem in modern AI-assisted development: code generation is fast, but reviewing plausible-looking generated code is expensive. spek makes the expected behavior and permitted side effects explicit, generates executable tests, performs static effect analysis, and feeds structured findings back into an agentic repair loop.

## Core Workflow

The typical workflow is:

1. Write a concise `.spek` contract for one or more functions.
2. Declare expected outcomes, representative examples, and allowed effects such as `!db`, `!net`, `!fs`, or `!hash`.
3. Use `spek prompt` to produce a generation prompt containing the contract and implementation conventions.
4. Let any external coding agent or command write the implementation in Python.
5. Run `spek verify` to lint the specification, statically inspect effects, generate pytest cases, and execute them.
6. If the implementation fails, pass stable diagnostics and test output into the next repair round.
7. Treat remaining `? hatch` properties as explicit human-review items rather than pretending they were verified.

Example contract:

```text
login(email, password) -> session | wrong | locked
  !db !hash
  (known, right) ok
  (known, bad_pw) wrong
  (unknown, any) wrong
  (locked_acct, right) locked
```

This compact contract communicates the function’s outcomes, database and hashing dependencies, security-sensitive behavior, and anti-user-enumeration rule. Bare words such as `known` and `right` are fixtures supplied by ordinary Python rather than being built into the language.

## Language and Contract Model

The language has a deliberately small grammar:

- A signature declares a function, parameters, and named outcomes.
- The first outcome is success; `ok` is an alias for it.
- Example lines map inputs to outcomes or exact return values.
- `!tag` lines declare permitted effects.
- `? text` lines mark requirements that examples cannot machine-check.
- `: text` lines provide optional implementation guidance.
- Multiple specifications can exist in one file.

The implementation enforces a tight body-line budget and a separate note budget. This keeps contracts short enough for a human reviewer to understand quickly and small enough to place directly in an AI prompt. Linting reports issues such as missing examples, unexercised outcomes, duplicate cases, excessive hatches, unknown effects, and budget violations.

The design deliberately excludes types, loops, control flow, inheritance, refinement syntax, and general constraint sublanguages. The goal is a stable verification boundary, not another implementation language.

## Verification Architecture

### Parser, AST, and linting

The lexer and parser convert `.spek` files into a typed specification AST containing signatures, literals, examples, effects, hatches, notes, and source spans. Diagnostics are represented as structured objects with stable error and warning codes, locations, symbols, and suggested fixes.

### Test generation

The Python code generator lowers every example into a `Case` record and emits a pytest module under `.spek/`. Generated tests:

- import the implementation from its file path;
- resolve named fixtures at test execution time;
- support positional arguments, keyword bindings, and setup state;
- map success and non-success outcomes through a documented protocol;
- preserve source line information in test IDs;
- include notes and hatches as visible generated comments;
- include a machine-readable triage table;
- are regenerated from the specification rather than edited manually.

The runtime supports fixture references, fresh per-example mutable state, implementation-module identity preservation, class and method targets, configurable subjects, and configurable outcome classification through `spekconf.py`.

### Static effect analysis

The Python effects checker uses the standard-library `ast` module instead of executing the implementation. It resolves import aliases, recognizes known effect-bearing operations, locates the function named by the specification, and follows calls into module-local helper functions.

It detects:

- undeclared effects, such as a network call under a contract that only permits filesystem access (`E101`);
- declared effects that the implementation never performs (`E103`), exposing specification drift;
- effects hidden behind calls the analyzer cannot inspect (`W301`), reported as warnings rather than false certainty;
- heuristic use of persistent mutable state without `!mem` (`W308`).

Supported effect vocabulary includes network, filesystem, database, subprocess, environment, clock, randomness, hashing/cryptography, console I/O, AI/model calls, and retained memory. The checker is intentionally conservative about its limits: it stops at module boundaries and cannot see through dynamic `getattr` dispatch, so it under-reports rather than over-reports.

### Verification pipeline

`verify` runs the stages in a deliberate order:

1. Parse and lint the specification.
2. Stop immediately on syntax or semantic specification errors.
3. Check implementation effects before running examples.
4. Check fixture bindings statically without importing the fixtures file.
5. Generate the pytest module and fixture stub when appropriate.
6. Run pytest and capture the result.
7. Return a combined verdict, diagnostics, triage information, observations, and test output.

The result model distinguishes errors, warnings, hatches, whether tests ran, and whether they passed. An undeclared side effect therefore blocks execution even if the examples might happen to pass.

## Agentic and AI-Driven Development Design

The project treats an AI coding agent as a replaceable implementation generator, not as the authority that grades its own output.

### Vendor-neutral agent integration

The `loop` command accepts an arbitrary external command, sends the generation or repair prompt over standard input, and checks that the command writes the requested implementation file. This keeps the verification system independent of a particular model vendor, SDK, API, or agent framework.

### Generate, verify, repair loop

The loop driver supports bounded iterative rounds:

- If no implementation exists, it sends a generation prompt containing the spec and conventions.
- If an implementation already exists, it verifies it before asking an agent to change anything.
- After a failed round, it builds a repair prompt from structured diagnostics and captured pytest output.
- The prompt tells the agent to change only what the findings require and never edit generated tests.
- The process stops on a passing verdict, an agent failure, a missing output file, or the configured round limit.

This is an agentic control loop with a deterministic acceptance boundary. The model proposes code; the compiler-like tool supplies evidence; the next model round receives actionable feedback. Stable diagnostic codes, offending symbols, source locations, and suggested fixes let an agent react programmatically instead of parsing fragile prose.

### Prompt-aware constraints

The generated prompt includes the outcome protocol, effect rules, fixture behavior, hatch semantics, and the original contract. The language reference is guarded by a token-budget test so the protocol remains small enough to use as context for a coding model. Notes provide local guidance without becoming hidden build requirements, while examples always remain authoritative.

## CLI Surface

The package exposes a `spek` command with these operations:

```text
spek check   spec.spek
spek build   spec.spek --impl impl.py
spek effects  spec.spek impl.py
spek verify  spec.spek impl.py
spek prompt  spec.spek --impl impl.py
spek loop    spec.spek --impl impl.py --agent 'claude -p'
```

All diagnostic-oriented commands support `--json`, enabling CI systems, IDE integrations, repair agents, and other automation to consume structured output. Exit codes distinguish a clean result, findings, and command-usage errors.

## Demonstrated Domains and Examples

The repository includes small examples such as login authentication, date parsing, slugification, CSV processing, scheduling, transfers, caching, and user fetching. The canonical authentication demo verifies a real Python implementation using SQLite, password hashing, constant-time comparison, typed session data, and distinct exception-based outcomes.

The complex examples cover six unrelated backend flows:

- checkout and payment;
- webhook delivery;
- password reset;
- rate limiting;
- CSV import;
- double-entry ledger transfers.

Together they contain 18 specifications, 48 examples, 13 hatches, and 6 notes. Ten of the 18 specifications are fully machine-verifiable. The experiment found that hatches account for 21% of assertion lines, below the project’s initial 50–70% expectation, and that no specification exceeded the six-line body budget.

## Engineering Quality and Test Strategy

The project is implemented as a dependency-light Python package targeting Python 3.10+, with pytest and Ruff as development tools. The test suite covers parsing, grammar and token budgets, linting, diagnostics, runtime behavior, fixture isolation, Python code generation, effect analysis, CLI behavior, and end-to-end verification.

Notable regression coverage includes:

- correct and incorrect implementations, including edge-case failures;
- effect mismatches that prevent tests from running;
- import alias resolution and module-local helper traversal;
- specification drift and opaque external calls;
- unbound fixtures detected without importing arbitrary fixture code;
- preservation of existing fixture files;
- generated test syntax and triage output;
- notes remaining inert and unable to change a build verdict;
- agent loops repairing a naive implementation within two rounds;
- pre-existing implementations being verified before any generation request;
- generator failures, missing output files, parse failures, and round limits.

## Measured Boundaries and Honest Limitations

The project does not claim to verify that a specification itself is correct. It verifies the narrower relationship between a compact contract and an implementation.

The measured limitation is composition. Leaf functions such as parsing, validation, lookup, hashing, and a single write are usually well expressed by examples plus effects. Orchestrator functions whose correctness depends on relationships between calls still require hatches for properties such as atomicity, compensation, temporal behavior, idempotency, cross-entity invariants, and resource bounds. The system exposes these gaps explicitly and uses hatch counts as a review-triage signal instead of silently treating prose as proof.

The repository currently has a Python target only. Cross-language portability, including TypeScript implementation verification, is an stated future claim rather than a demonstrated capability. The complex-example exercise measures language expressiveness; it does not yet measure whether an external model consistently generates correct implementations from these contracts.

## Technical Stack

- Python 3.10+
- Standard-library parsing and static analysis with `ast`
- pytest-generated verification modules
- argparse-based CLI
- Dataclasses and typed Python APIs
- JSON diagnostics for automation
- Ruff for linting
- Setuptools package/build configuration
- No runtime dependencies for the core package

## Repository Areas

- `spek/parser.py`, `spek/lexer.py`, `spek/spec_ast.py`: language front end and AST
- `spek/lint.py`, `spek/diagnostics.py`: budgets, triage, and stable findings
- `spek/codegen/python.py`: pytest compilation
- `spek/runtime.py`: fixtures, target loading, and outcome classification
- `spek/effects/`: Python static effect vocabulary and analysis
- `spek/verify.py`: end-to-end referee pipeline
- `spek/prompt.py`, `spek/loop.py`: model prompts and generate-verify-repair orchestration
- `spek/cli.py`: user-facing command line interface
- `docs/`: language reference, Python target behavior, and empirical limits
- `examples/`: compact contracts and real-world flow studies
- `tests/`: unit, integration, CLI, code-generation, and agent-loop coverage

## Accurate Positioning

spek is best described as a **vendor-neutral, contract-driven verification harness for AI-generated Python**, built around a deliberately tiny specification language. Its distinctive contribution is the inversion from code generation to verification: the AI can generate familiar implementation code, while the human-authored contract becomes executable tests, static side-effect policy, structured repair feedback, and an explicit boundary around what still needs human review.
