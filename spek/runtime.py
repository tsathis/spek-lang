"""Runtime support: fixtures and target loading."""

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
