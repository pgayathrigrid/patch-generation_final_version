"""
Module-private AST traversal helpers shared by all DetectionRule implementations.

These are pure functions — they only read the AST and never mutate it.
"""
from __future__ import annotations

import ast
from typing import List, Optional, Set, Tuple


def get_import_names(tree: ast.Module) -> Set[str]:
    """
    Return every module and name string imported anywhere in *tree*.

    Examples of what is captured::

        import logging           → {"logging"}
        from opentelemetry import trace  → {"opentelemetry", "trace"}
        import tenacity as t     → {"tenacity"}
    """
    names: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.lower())
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.lower())
            for alias in node.names:
                names.add(alias.name.lower())
    return names


def get_all_call_sites(tree: ast.Module) -> List[Tuple[str, int]]:
    """
    Return ``(full_name, line_number)`` for every function call in *tree*.

    Handles:
    - Simple calls:    ``foo()``         → ``"foo"``
    - Method calls:    ``obj.method()``  → ``"obj.method"``
    - Chained calls:   ``a.b.c()``       → ``"a.b.c"``
    - Context mgrs:    ``with ctx():``   → captured via ast.walk
    """
    results: List[Tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _extract_call_name(node)
            if name is not None:
                results.append((name.lower(), node.lineno))
    return results


def get_decorator_sites(tree: ast.Module) -> List[Tuple[str, int]]:
    """
    Return ``(decorator_name, line_number)`` for every decorator in *tree*.

    Handles:
    - ``@retry``                  → ``"retry"``
    - ``@module.decorator``       → ``"module.decorator"``
    - ``@retry(max_attempts=3)``  → ``"retry"``  (unwraps Call nodes)
    """
    results: List[Tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for dec in node.decorator_list:
                name = _extract_decorator_name(dec)
                if name is not None:
                    line = dec.lineno if hasattr(dec, "lineno") else node.lineno
                    results.append((name.lower(), line))
    return results


def get_try_except_lines(tree: ast.Module) -> List[int]:
    """Return the line numbers of every ``try`` block in *tree*."""
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Try)
    ]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_call_name(node: ast.Call) -> Optional[str]:
    return _extract_expr_name(node.func)


def _extract_decorator_name(node: ast.expr) -> Optional[str]:
    if isinstance(node, ast.Call):
        return _extract_expr_name(node.func)
    return _extract_expr_name(node)


def _extract_expr_name(node: ast.expr) -> Optional[str]:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _extract_expr_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return None
