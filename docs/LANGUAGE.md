# The spek language

**This is not a programming language.** It is a spec format that compiles to
verification. No runtime, no execution target, no code generation. Five lines
a human reads in four seconds, that the machine turns into tests and an
effects check.

## Grammar

```ebnf
spec     = sig, { line } ;
sig      = name, "(", [ params ], ")", "->", outcomes ;
params   = ident, { ",", ident } ;
outcomes = ident, { "|", ident } ;
line     = effect | example | hatch | note ;
effect   = "!", ident ;
example  = input, ws, outcome ;
hatch    = "?", text ;
note     = ":", text ;
input    = literal | "(", literal, { ",", literal }, ")" ;
```

The signature starts at column 0; body lines are indented. `#` begins a
comment. One file may hold several specs.

## The rules

| Rule | Syntax | Meaning |
|---|---|---|
| Signature | `name(args) -> a \| b \| c` | `\|` separates outcomes |
| Effect | `!tag` | what the function is allowed to touch |
| Example | `input outcome` | input, then expected outcome |
| Hatch | `? free text` | a requirement; unverified, a human must check |
| Note | `: free text` | optional guidance; nothing checks it |

```
login(email, password) -> session | wrong | locked
  !db !hash
  (known, right) ok
  (known, bad_pw) wrong
  (unknown, any) wrong
  (locked_acct, right) locked
```

## Outcomes

The first outcome is success. `ok` is an alias for it, so `(known, right) ok`
and `(known, right) session` mean the same thing.

## Effects

`!tag` declares an effect. Checked tags: `net` `fs` `db` `proc` `env` `clock`
`rand` `hash` `io` `ai` `mem`. Any other word parses but verifies nothing.

Effects are checked against the implementation's imports and calls, covering
the function and the module-local helpers it reaches. Using an undeclared
effect is an error. Declaring one the code never performs is also an error --
that is spec drift -- unless the function calls out through an import the
analysis cannot follow, when it becomes a warning.

## Examples

Values are strings, numbers, `true`, `false`, `null`, or a bare word. A bare
word is a *fixture*: `known` means whatever your fixtures file says it means.
`name=value` binds a parameter by name; if the name is not a parameter it is
setup state passed to your setup hook instead.

One input per parameter. Wrap two or more in parentheses.

The last token on the line is an outcome when it names one, otherwise it is
the exact expected return value:

```
slugify(title) -> text
  "Hello World" "hello-world"
  "" ""
```

In a spec with several outcomes, an unrecognised bare word at the end is a
typo, not a value — pin exact values with a string or number there.

## Notes

`: text` is optional guidance, chiefly for whoever writes the implementation --
a pointer to an existing helper, what a fixture word means, why an order
matters. It reaches the generation prompt and the generated tests, and nothing
verifies it, so **a note can never fail a build**. An example always wins over
a note.

The one distinction to keep sharp:

| | `? hatch` | `: note` |
|---|---|---|
| what it is | a requirement on the finished code | guidance for whoever writes it |
| optional | no -- it must hold, nothing can check it | yes -- freely ignorable |
| counted in triage | yes | no |

Notes sit outside the body-line budget but have their own cap of three.
Guidance that applies repo-wide belongs in `CLAUDE.md`; a note is for this one
function. `#` remains a plain comment, stripped by the lexer and seen by
nothing downstream.

## Hatches

`? text` marks a property examples cannot express: `? atomic`, `? constant
memory`, `? retries 3x with backoff`. Nothing checks it. The count is the
triage signal:

| Hatches | Meaning |
|---|---|
| 0 | machine-verifiable; merge on green |
| 1–2 | a human must review the marked properties |
| more than examples | the spec is buying you little; write the code yourself |

## Not in the language, permanently

Types · loops · control flow · refinement syntax · constraint sublanguages ·
inheritance · anything without a clean mapping to every target language.

Every one of these will be requested. Each is the slide toward a
general-purpose language, which is where the project dies. A feature that
cannot be justified against the token budget does not ship.
