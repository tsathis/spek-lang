# spek: Project Description

## What is spek

spek is a Python tool for verifying AI generated code. it takes a small
specification and an implementation and checks whether they agree, using
generated pytest cases and static effect analysis.

## Design goals

- Small grammar, examples and effects only
- Generated tests, not hand written ones
- Works with any external coding agent, not tied to one vendor

## Example

```
login(user, pass) -> ok | fail
  !db !hash
  (exists, correct) ok
  (exists, wrong) fail
  (missing, any) fail
```
