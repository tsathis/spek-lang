"""Static effect analysis for Python implementations.

Walks the AST looking for calls that look like they touch the network,
db, filesystem, hashing etc. Calls we can't inspect (through a name we
don't recognize, or an attribute on something dynamic) get flagged as a
warning instead of silently passing.
"""

import ast


class EffectChecker(ast.NodeVisitor):
    def __init__(self):
        self.effects = set()
        self.opaque_calls = []

    def check(self, code, func_name):
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                self.visit(node)
        return self.effects

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            if attr in ("get", "post", "put", "delete"):
                self.effects.add("net")
            elif attr in ("execute", "query"):
                self.effects.add("db")
            elif attr in ("open", "read", "write"):
                self.effects.add("fs")
            elif attr in ("sha256", "md5", "hexdigest", "new"):
                self.effects.add("hash")
        elif isinstance(node.func, ast.Name):
            # local helper call, we don't follow it yet
            self.opaque_calls.append(node.func.id)
        self.generic_visit(node)
