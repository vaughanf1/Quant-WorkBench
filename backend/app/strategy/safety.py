"""AST safety validation for strategy files (ported from tickflow-stock-panel).

An allowlist of imports plus denylists of calls, dunder attributes and string
subscripts. As the original honestly notes: an AST allowlist is defence in
depth, not a true sandbox — strategy files still execute in-process. AI- and
user-authored files are validated here both at save time and again by the
loader before every exec, so a hand-tampered file on disk cannot bypass the
API-level check.
"""
from __future__ import annotations

import ast

ALLOWED_IMPORT_MODULES = {"polars", "numpy", "datetime", "math", "__future__"}

FORBIDDEN_CALLS = {
    "open", "exec", "eval", "compile", "__import__", "globals", "locals",
    "vars", "dir", "getattr", "setattr", "delattr", "type", "input", "breakpoint",
}

FORBIDDEN_ATTRS = {
    "__globals__", "__builtins__", "__class__", "__subclasses__", "__mro__",
    "__bases__", "__base__", "__dict__", "__code__", "__import__", "__loader__",
    "__spec__", "__wrapped__",
}

FORBIDDEN_STR_SUBSCRIPTS = {"__builtins__", "__import__", "__globals__"}


def validate_safety(code: str) -> str | None:
    """Return an error string if ``code`` violates the safety rules, else None."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"syntax error: {exc}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in ALLOWED_IMPORT_MODULES:
                    return f"import of '{alias.name}' is not allowed"
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root not in ALLOWED_IMPORT_MODULES:
                return f"import from '{node.module}' is not allowed"
        elif isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in FORBIDDEN_CALLS:
                return f"call to '{fn.id}' is not allowed"
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ATTRS:
                return f"attribute '{node.attr}' is not allowed"
        elif isinstance(node, ast.Subscript):
            sl = node.slice
            if isinstance(sl, ast.Constant) and isinstance(sl.value, str) \
                    and sl.value in FORBIDDEN_STR_SUBSCRIPTS:
                return f"subscript '{sl.value}' is not allowed"
    return None
