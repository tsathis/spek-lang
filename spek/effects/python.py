"""Static effect analysis for Python implementations.

Walks the AST looking for calls that look like they touch the network,
db, filesystem, hashing etc.
"""

import ast


class EffectChecker(ast.NodeVisitor):
    def __init__(self):
        self.effects = set()

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
            if attr in ("execute", "query"):
                self.effects.add("db")
            if attr in ("open", "read", "write"):
                self.effects.add("fs")
            if attr in ("sha256", "md5", "hexdigest", "new"):
                self.effects.add("hash")
        self.generic_visit(node)
