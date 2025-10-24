# spek Language Reference (draft)

## Grammar

```
spec = signature body
signature = IDENT "(" params ")" "->" outcomes
body = (effect | hatch | note | example)*
effect = "!" IDENT
hatch = "?" TEXT
note = ":" TEXT
example = "(" inputs ")" outcome
```

First outcome is success.

more to write here
