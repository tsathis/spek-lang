"""Static effect analysis for Python implementations.

Answers one question: given `login(...)` and a module claiming to implement
it, what does that function actually touch? The check runs at function-spec
granularity -- the spec's own function plus the module-local helpers it calls
-- so an unrelated `requests` import elsewhere in the file is not held against
it.

Limits, stated plainly: analysis stops at the module boundary (a call into
another module of the project contributes nothing), and dynamic dispatch
through `getattr` is invisible. Both under-report rather than over-report.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from ..diagnostics import (
    E_EFFECT_NOT_IMPLEMENTED,
    E_IMPL_SYNTAX,
    E_TARGET_NOT_FOUND,
    E_UNDECLARED_EFFECT,
    W_UNDECLARED_HEURISTIC,
    W_UNUSED_EFFECT,
    Diagnostic,
    error,
    warning,
)
from ..spec_ast import Spec
from .python_table import (
    BUILTIN_EFFECTS,
    MEMOIZING_DECORATORS,
    MUTABLE_CONSTRUCTORS,
    effect_for,
    is_opaque,
)
from .vocabulary import KNOWN_EFFECTS, EffectKind, kind_of

_SELF_NAMES = frozenset({"self", "cls"})


@dataclass(frozen=True)
class Observation:
    """One place the implementation reaches for something with an effect."""

    tag: str
    symbol: str
    line: int
    col: int
    via: str

    def as_dict(self) -> dict[str, object]:
        return {
            "tag": self.tag,
            "symbol": self.symbol,
            "line": self.line,
            "col": self.col,
            "via": self.via,
        }


def _dotted(node: ast.AST) -> str | None:
    """`a.b.c` as a string, or None if the chain is not pure attribute access."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


class ModuleIndex:
    """Everything the checker needs to know about one implementation module."""

    def __init__(self, tree: ast.Module):
        self.tree = tree
        self.aliases: dict[str, str] = {}
        self.functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
        self.classes: dict[str, ast.ClassDef] = {}
        self.mutable_globals: set[str] = set()
        self._index_imports(tree)
        self._index_definitions(tree)
        self._index_globals(tree)

    # -- indexing --
    def _index_imports(self, tree: ast.Module) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local = alias.asname or alias.name.split(".")[0]
                    target = alias.name if alias.asname else alias.name.split(".")[0]
                    self.aliases[local] = target
            elif isinstance(node, ast.ImportFrom):
                if node.level:  # relative import: a module we do not follow
                    continue
                module = node.module or ""
                for alias in node.names:
                    local = alias.asname or alias.name
                    self.aliases[local] = f"{module}.{alias.name}" if module else alias.name

    def _index_definitions(self, tree: ast.Module) -> None:
        for node in tree.body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                self.functions[node.name] = node
            elif isinstance(node, ast.ClassDef):
                self.classes[node.name] = node
                for item in node.body:
                    if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                        self.functions[f"{node.name}.{item.name}"] = item

    def _index_globals(self, tree: ast.Module) -> None:
        for node in tree.body:
            if not isinstance(node, ast.Assign | ast.AnnAssign):
                continue
            value = node.value
            if value is None or not self._is_mutable(value):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    self.mutable_globals.add(target.id)

    def _is_mutable(self, value: ast.expr) -> bool:
        if isinstance(value, ast.Dict | ast.List | ast.Set | ast.ListComp | ast.DictComp):
            return True
        if isinstance(value, ast.Call):
            name = self.resolve(_dotted(value.func) or "")
            return name in MUTABLE_CONSTRUCTORS
        return False

    # -- lookups --
    def resolve(self, dotted: str) -> str:
        """Rewrite a name chain through the import aliases."""
        if not dotted:
            return dotted
        head, _, tail = dotted.partition(".")
        target = self.aliases.get(head)
        if target is None:
            return dotted
        return f"{target}.{tail}" if tail else target

    def find(self, spec: Spec) -> tuple[str | None, list[str]]:
        """Locate the function a spec describes. Returns (qualname, candidates)."""
        method = spec.python_name()
        owner = spec.python_owner()

        if owner:
            for candidate in (f"{owner}.{method}", f"{owner.capitalize()}.{method}",
                              f"{owner.title().replace('_', '')}.{method}"):
                if candidate in self.functions:
                    return candidate, []
        elif method in self.functions:
            return method, []

        matches = [q for q in self.functions if q.rsplit(".", 1)[-1] == method]
        if len(matches) == 1:
            return matches[0], []
        return None, sorted(self.functions)


class _EffectVisitor(ast.NodeVisitor):
    """Collects effect observations from one function body."""

    def __init__(self, index: ModuleIndex, qualname: str):
        self.index = index
        self.qualname = qualname
        self.observations: list[Observation] = []
        self.calls: list[str] = []
        #: Calls into code this analysis cannot see through.
        self.opaque: list[str] = []

    def _record(self, tag: str, symbol: str, node: ast.AST) -> None:
        self.observations.append(
            Observation(
                tag=tag,
                symbol=symbol,
                line=getattr(node, "lineno", 0),
                col=getattr(node, "col_offset", 0) + 1,
                via=self.qualname,
            )
        )

    def visit_Attribute(self, node: ast.Attribute) -> None:
        chain = _dotted(node)
        if chain is None:
            self.generic_visit(node)
            return
        head = chain.split(".", 1)[0]
        if head in _SELF_NAMES:
            return  # instance state; handled by the mem heuristic
        resolved = self.index.resolve(chain)
        tag = effect_for(resolved)
        if tag:
            self._record(tag, resolved, node)
        # A resolved chain is all names; nothing further to descend into.

    def visit_Name(self, node: ast.Name) -> None:
        resolved = self.index.resolve(node.id)
        tag = effect_for(resolved)
        if tag:
            self._record(tag, resolved, node)
        elif node.id in BUILTIN_EFFECTS and node.id not in self.index.functions:
            self._record(BUILTIN_EFFECTS[node.id], node.id, node)
        elif node.id in self.index.mutable_globals:
            self._record("mem", node.id, node)

    def visit_Call(self, node: ast.Call) -> None:
        target = self._local_callee(node.func)
        if target:
            self.calls.append(target)
        else:
            self._note_if_opaque(node.func)
        self.generic_visit(node)

    def _note_if_opaque(self, func: ast.expr) -> None:
        chain = _dotted(func)
        if chain is None:
            return
        head = chain.split(".", 1)[0]
        if head not in self.index.aliases:
            return  # a local name; nothing was imported to hide behind
        resolved = self.index.resolve(chain)
        if is_opaque(resolved):
            self.opaque.append(resolved)

    def visit_Global(self, node: ast.Global) -> None:
        for name in node.names:
            self._record("mem", name, node)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        for name in node.names:
            self._record("mem", name, node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        chain = _dotted(node.value)
        if chain and chain.split(".", 1)[0] in _SELF_NAMES and "." in chain:
            self._record("mem", chain, node)
        self.generic_visit(node)

    def _local_callee(self, func: ast.expr) -> str | None:
        """A call into another function of this same module, if it is one."""
        if isinstance(func, ast.Name):
            return func.id if func.id in self.index.functions else None
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id in _SELF_NAMES:
                owner = self.qualname.rsplit(".", 1)[0] if "." in self.qualname else None
                candidate = f"{owner}.{func.attr}" if owner else func.attr
                return candidate if candidate in self.index.functions else None
        return None


def _decorator_effects(
    node: ast.FunctionDef | ast.AsyncFunctionDef, index: ModuleIndex, qualname: str
) -> list[Observation]:
    found: list[Observation] = []
    for decorator in node.decorator_list:
        expr = decorator.func if isinstance(decorator, ast.Call) else decorator
        resolved = index.resolve(_dotted(expr) or "")
        if resolved in MEMOIZING_DECORATORS:
            found.append(
                Observation("mem", resolved, decorator.lineno, decorator.col_offset + 1, qualname)
            )
    return found


def observe(
    spec: Spec, index: ModuleIndex, qualname: str
) -> tuple[list[Observation], list[str]]:
    """Walk the target function and every module-local helper it reaches.

    Returns the effects observed and the calls that were opaque -- imports this
    analysis could not see through, which is what separates "the spec drifted"
    from "we could not tell".
    """
    observations: list[Observation] = []
    opaque: list[str] = []
    seen: set[str] = set()
    queue = [qualname]

    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        node = index.functions.get(current)
        if node is None:
            continue
        visitor = _EffectVisitor(index, current)
        observations.extend(_decorator_effects(node, index, current))
        for statement in node.body:
            visitor.visit(statement)
        observations.extend(visitor.observations)
        opaque.extend(visitor.opaque)
        queue.extend(callee for callee in visitor.calls if callee not in seen)

    return observations, opaque


def check(
    spec: Spec, source: str, path: str | None = None
) -> tuple[list[Diagnostic], list[Observation]]:
    """Compare a spec's declared effects against what the code actually does."""
    try:
        tree = ast.parse(source, filename=path or "<impl>")
    except SyntaxError as exc:
        return (
            [
                error(
                    E_IMPL_SYNTAX,
                    f"implementation does not parse: {exc.msg}",
                    file=path,
                    line=exc.lineno,
                    col=exc.offset,
                )
            ],
            [],
        )

    index = ModuleIndex(tree)
    qualname, candidates = index.find(spec)
    if qualname is None:
        hint = ", ".join(candidates[:8]) or "the module defines no functions"
        return (
            [
                error(
                    E_TARGET_NOT_FOUND,
                    f"no function named {spec.python_name()!r} in {path or 'the implementation'}",
                    file=path,
                    symbol=spec.name,
                    fix=f"define it, or rename an existing one; found: {hint}",
                    extra={"candidates": candidates},
                )
            ],
            [],
        )

    observations, opaque = observe(spec, index, qualname)
    return _reconcile(spec, observations, opaque, path, qualname), observations


def _reconcile(
    spec: Spec,
    observations: list[Observation],
    opaque: list[str],
    path: str | None,
    qualname: str,
) -> list[Diagnostic]:
    declared = set(spec.effect_tags)
    diags: list[Diagnostic] = []

    reported: set[tuple[str, str]] = set()
    for obs in observations:
        if obs.tag in declared or (obs.tag, obs.symbol) in reported:
            continue
        reported.add((obs.tag, obs.symbol))
        via = "" if obs.via == qualname else f" (reached via {obs.via})"
        if kind_of(obs.tag) is EffectKind.HEURISTIC:
            diags.append(
                warning(
                    W_UNDECLARED_HEURISTIC,
                    f"{qualname} appears to keep state via {obs.symbol!r}{via}, "
                    f"but the spec does not declare '!{obs.tag}'",
                    file=path,
                    line=obs.line,
                    col=obs.col,
                    symbol=obs.symbol,
                    fix=f"add `!{obs.tag}` to the spec, or make the function pure",
                    extra={"effect": obs.tag},
                )
            )
        else:
            diags.append(
                error(
                    E_UNDECLARED_EFFECT,
                    f"{qualname} uses {obs.symbol!r}{via}, "
                    f"but the spec does not declare '!{obs.tag}'",
                    file=path,
                    line=obs.line,
                    col=obs.col,
                    symbol=obs.symbol,
                    fix=f"remove the call, or add `!{obs.tag}` to the spec",
                    extra={"effect": obs.tag},
                )
            )

    diags.extend(_unimplemented(spec, observations, opaque, qualname))
    return diags


def _unimplemented(
    spec: Spec, observations: list[Observation], opaque: list[str], qualname: str
) -> list[Diagnostic]:
    """Effects the spec promises that the code does not deliver.

    This is the cheap drift check. A spec declaring `!hash` over an
    implementation that compares passwords with `==` is a spec that has become
    a lie, and it is an error. It is only downgraded to a warning when the
    function calls out through an import we cannot follow, because then the
    hashing might genuinely be happening one module over.
    """
    observed = {obs.tag for obs in observations}
    blind = sorted(set(opaque))
    diags: list[Diagnostic] = []

    for effect in spec.effects:
        if effect.tag in observed or effect.tag not in KNOWN_EFFECTS:
            continue
        common = {
            "file": spec.file,
            "line": effect.span.line,
            "col": effect.span.col,
            "symbol": effect.tag,
            "extra": {"effect": effect.tag, "opaque_calls": blind},
        }
        if blind:
            diags.append(
                warning(
                    W_UNUSED_EFFECT,
                    f"spec declares '!{effect.tag}' but {qualname} shows no sign of it; "
                    f"it may happen inside {blind[0]}"
                    + (f" (+{len(blind) - 1} more)" if len(blind) > 1 else ""),
                    fix=f"confirm {blind[0]} does the work, or drop `!{effect.tag}`",
                    **common,
                )
            )
        else:
            diags.append(
                error(
                    E_EFFECT_NOT_IMPLEMENTED,
                    f"spec declares '!{effect.tag}' but {qualname} never does it, "
                    f"and calls nothing that could",
                    fix=f"implement it, or drop `!{effect.tag}` from the spec",
                    **common,
                )
            )
    return diags
