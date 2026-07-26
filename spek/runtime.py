"""What generated tests call at run time.

An example says `(known, right) ok` -- three things have to happen before that
is executable. `known` has to become a value, the implementation has to be
found and called, and whatever it returns or raises has to be mapped back to
one of the spec's outcome names. This module does those three things, and the
rules it uses are the ones `spek prompt` tells the model about, so the
implementation is written to satisfy them.

The outcome protocol
--------------------
* The first outcome is success: the call returns normally.
* Any other outcome is signalled by raising an exception whose class name
  contains the outcome word (`locked` <- `AccountLockedError`), or by
  returning a value tagged with it -- an `.outcome`/`.status`/`.kind`
  attribute, an enum, or a `(tag, value)` pair.
* A project that wants different rules writes `classify` in its conf module.
"""

from __future__ import annotations

import importlib
import importlib.util
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FIXTURES_MODULE = "spek_fixtures"
CONF_MODULE = "spekconf"

_TAG_ATTRS = ("outcome", "status", "kind", "tag")

#: Implementation modules loaded by path, newest last. The fixtures file
#: needs the *same* module object the tests call, not a fresh import of it.
_LOADED: dict[str, Any] = {}


class SpekUnboundSymbol(LookupError):
    """An example named a fixture that nothing defines."""


class SpekTargetMissing(LookupError):
    """The implementation has no function matching the spec."""


@dataclass(frozen=True)
class Ref:
    """A placeholder for a fixture, resolved when the test runs."""

    name: str


@dataclass(frozen=True)
class Case:
    """One example, lowered into something a test can execute."""

    spec: str
    target: str
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    setup: dict[str, Any] = field(default_factory=dict)
    outcome: str = ""
    outcomes: tuple[str, ...] = ()
    expect: Any = None
    has_expect: bool = False
    line: int = 0

    @property
    def id(self) -> str:
        shown = ", ".join(_show(a) for a in self.args)
        for key, value in self.kwargs.items():
            shown += f"{', ' if shown else ''}{key}={_show(value)}"
        return f"L{self.line}:({shown})->{self.outcome}"


def _show(value: Any) -> str:
    return value.name if isinstance(value, Ref) else repr(value)


# --- loading the pieces -----------------------------------------------------


def load_module_from_path(path: str | Path, name: str | None = None) -> Any:
    """Import a module from a file path, without requiring it be on sys.path."""
    resolved = Path(path).resolve()
    module_name = name or f"_spek_impl_{re.sub(r'[^0-9A-Za-z_]', '_', resolved.stem)}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, resolved)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import {resolved}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    # The implementation's own directory has to be importable for its siblings
    # -- the fixtures file lives there.
    parent = str(resolved.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    spec.loader.exec_module(module)
    _LOADED[resolved.stem] = module
    return module


def implementation(stem: str | None = None) -> Any:
    """The module under test, for a fixtures file that needs to configure it.

    Importing the implementation by name from `spek_fixtures` would give a
    second, unrelated module object -- patching that one changes nothing.
    """
    if stem is not None:
        if stem not in _LOADED:
            raise SpekTargetMissing(f"no implementation loaded for {stem!r}")
        return _LOADED[stem]
    if not _LOADED:
        raise SpekTargetMissing("no implementation has been loaded yet")
    return next(reversed(_LOADED.values()))


def _optional_module(name: str) -> Any | None:
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def fixtures() -> dict[str, Any]:
    module = _optional_module(FIXTURES_MODULE)
    return dict(getattr(module, "FIXTURES", {}) or {}) if module else {}


def resolve(value: Any, bindings: dict[str, Any]) -> Any:
    """Turn `Ref('known')` into whatever the fixtures file says `known` is."""
    if not isinstance(value, Ref):
        return value
    if value.name not in bindings:
        known = ", ".join(sorted(bindings)) or "none defined"
        raise SpekUnboundSymbol(
            f"example uses {value.name!r} but no fixture defines it "
            f"(available: {known}). Add it to {FIXTURES_MODULE}.FIXTURES."
        )
    bound = bindings[value.name]
    return bound() if isinstance(bound, Fresh) else bound


@dataclass(frozen=True)
class Fresh:
    """Wrap a factory so each example gets its own copy of mutable state."""

    build: Callable[[], Any]

    def __call__(self) -> Any:
        return self.build()


def target_for(impl: Any, spec_name: str) -> Callable[..., Any]:
    """Find the callable a spec names, including `cache.get` style methods."""
    method = spec_name.rsplit(".", 1)[-1]
    owner = spec_name.rsplit(".", 1)[0] if "." in spec_name else None

    if owner is None:
        found = getattr(impl, method, None)
        if callable(found):
            return found
        raise SpekTargetMissing(f"{impl.__name__} defines no function {method!r}")

    conf = _optional_module(CONF_MODULE)
    make_subject = getattr(conf, "subject", None) if conf else None
    if make_subject is None:
        fixture_module = _optional_module(FIXTURES_MODULE)
        make_subject = getattr(fixture_module, "subject", None) if fixture_module else None
    if make_subject is not None:
        instance = make_subject(spec_name)
        found = getattr(instance, method, None)
        if callable(found):
            return found

    for candidate in (owner, owner.capitalize(), owner.title().replace("_", "")):
        cls = getattr(impl, candidate, None)
        if isinstance(cls, type):
            found = getattr(cls(), method, None)
            if callable(found):
                return found
    raise SpekTargetMissing(
        f"{impl.__name__} has no {spec_name!r}; define the class, or add "
        f"`subject(name)` to {FIXTURES_MODULE} to build the receiver"
    )


# --- outcome classification -------------------------------------------------


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _match_outcome(text: str, outcomes: tuple[str, ...]) -> str | None:
    """Longest outcome whose word appears in `text`; longest wins over `ok` vs `okish`."""
    needle = _normalise(text)
    hits = [o for o in outcomes if _normalise(o) == needle]
    return max(hits, key=len) if hits else None


def classify(outcomes: tuple[str, ...], result: Any, exc: BaseException | None) -> str | None:
    """Map a call's behaviour onto one of the spec's outcome names."""
    conf = _optional_module(CONF_MODULE)
    override = getattr(conf, "classify", None) if conf else None
    if override is not None:
        decided = override(outcomes, result, exc)
        if decided is not None:
            return decided

    if exc is not None:
        for klass in type(exc).__mro__:
            matched = _match_outcome(klass.__name__, outcomes)
            if matched:
                return matched
        return _match_outcome(str(exc), outcomes)

    for attr in _TAG_ATTRS:
        tag = getattr(result, attr, None)
        if isinstance(tag, str):
            matched = _match_outcome(tag, outcomes)
            if matched:
                return matched
        elif tag is not None and hasattr(tag, "name"):
            matched = _match_outcome(str(tag.name), outcomes)
            if matched:
                return matched

    if hasattr(result, "name") and not isinstance(result, type):
        matched = _match_outcome(str(result.name), outcomes)
        if matched:
            return matched

    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], str):
        matched = _match_outcome(result[0], outcomes)
        if matched:
            return matched

    return outcomes[0] if outcomes else None


def _unwrap(result: Any) -> Any:
    """The value an example's `expect` compares against."""
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], str):
        return result[1]
    for attr in ("value", "data"):
        if hasattr(result, attr) and hasattr(result, "outcome"):
            return getattr(result, attr)
    return result


# --- the assertion ----------------------------------------------------------


def run_case(impl: Any, case: Case) -> None:
    """Execute one example and assert its outcome. Raises AssertionError on failure."""
    bindings = fixtures()
    conf = _optional_module(CONF_MODULE)
    setup_hook = getattr(conf, "setup", None) if conf else None
    if setup_hook is None:
        fixture_module = _optional_module(FIXTURES_MODULE)
        setup_hook = getattr(fixture_module, "setup", None) if fixture_module else None

    setup = {key: resolve(value, bindings) for key, value in case.setup.items()}
    if setup_hook is not None:
        setup_hook(case.spec, setup)
    elif setup:
        raise SpekUnboundSymbol(
            f"example on line {case.line} supplies setup {sorted(setup)} but no "
            f"`setup(spec, bindings)` hook exists in {FIXTURES_MODULE} or {CONF_MODULE}"
        )

    args = tuple(resolve(a, bindings) for a in case.args)
    kwargs = {key: resolve(value, bindings) for key, value in case.kwargs.items()}
    call = target_for(impl, case.target)

    result: Any = None
    raised: BaseException | None = None
    try:
        result = call(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - classification is the whole point
        raised = exc

    actual = classify(case.outcomes, result, raised)

    if actual != case.outcome:
        raise AssertionError(_explain(case, actual, result, raised))

    if case.has_expect:
        expected = resolve(case.expect, bindings)
        value = _unwrap(result)
        if value != expected:
            raise AssertionError(
                f"{case.target}{_args_repr(args, kwargs)} returned {value!r}, "
                f"expected {expected!r}  [{case.spec} line {case.line}]"
            )


def _args_repr(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    shown = [repr(a) for a in args] + [f"{k}={v!r}" for k, v in kwargs.items()]
    return "(" + ", ".join(shown) + ")"


def _explain(case: Case, actual: str | None, result: Any, exc: BaseException | None) -> str:
    head = (
        f"{case.target} should give outcome {case.outcome!r} but gave "
        f"{actual!r}  [{case.spec} line {case.line}]"
    )
    if exc is not None:
        return (
            f"{head}\n  raised {type(exc).__name__}: {exc}\n"
            f"  outcomes: {', '.join(case.outcomes)}\n"
            f"  to signal {case.outcome!r}, raise an exception whose class name "
            f"contains {case.outcome!r}"
        )
    return (
        f"{head}\n  returned {result!r}\n"
        f"  outcomes: {', '.join(case.outcomes)}\n"
        f"  to signal {case.outcome!r}, raise an exception named for it or return a "
        f"value tagged with it"
    )
