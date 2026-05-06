"""spek -- a spec format that compiles to verification, not to code.

Not a programming language. There is no runtime for the spec, no execution
target, no code generation. A `.spek` file compiles to tests and an effects
check against an implementation someone else wrote.
"""

from .diagnostics import Diagnostic, Severity, SpekError
from .lint import lint, lint_file, triage
from .parser import parse, parse_file
from .spec_ast import Spec, SpecFile

__version__ = "0.1.0"

__all__ = [
    "Diagnostic",
    "Severity",
    "Spec",
    "SpecFile",
    "SpekError",
    "__version__",
    "lint",
    "lint_file",
    "parse",
    "parse_file",
    "triage",
]
