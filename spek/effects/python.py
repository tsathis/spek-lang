"""Static effect analysis for Python implementations.

Walks the AST looking for calls that look like they touch the network,
db, filesystem etc. Very rough first pass, only catches requests.get for now.
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
            if node.func.attr == "get":
                self.effects.add("net")
        self.generic_visit(node)
