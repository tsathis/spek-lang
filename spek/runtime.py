"""Runtime support: fixtures, target loading, outcome classification."""

import importlib


class FixtureContext:
    def __init__(self, fixtures):
        self.fixtures = fixtures

    def get(self, name):
        return self.fixtures.get(name)


class Target:
    def __init__(self, module_name, func_name):
        self.module_name = module_name
        self.func_name = func_name

    def load(self):
        module = importlib.import_module(self.module_name)
        return getattr(module, self.func_name)


def classify_outcome(func, args, outcomes):
    """First outcome is success. Others map to an exception whose class
    name (lowercased) matches the outcome name."""
    try:
        result = func(*args)
        return outcomes[0], result
    except Exception as e:
        name = type(e).__name__.lower()
        if name in [o.lower() for o in outcomes]:
            return name, None
        raise
