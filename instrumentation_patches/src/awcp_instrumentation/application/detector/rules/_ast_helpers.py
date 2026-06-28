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


def get_calls_with_kwarg_names(tree: ast.Module) -> List[Tuple[str, int, frozenset]]:
    """Return ``(call_name, line, frozenset_of_kwarg_names)`` for every call in *tree*.

    The kwarg set lets detection rules distinguish two calls that share the same
    hook type (e.g. two ``SIGNAL_RECEIVED`` dispatches where one has ``flag_name=``
    and the other has ``attempt=``).
    """
    results: List[Tuple[str, int, frozenset]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _extract_call_name(node)
            if name is not None:
                kwargs = frozenset(
                    kw.arg for kw in node.keywords if kw.arg is not None
                )
                results.append((name.lower(), node.lineno, kwargs))
    return results


def get_function_variable_names(tree: ast.Module) -> dict:
    """Return ``{function_name: [variable_names]}`` for every function in *tree*.

    Collects parameter names, local assignment targets, for-loop targets,
    with-statement bindings, and exception handler aliases so the LLM prompt
    can tell the generator which variable names actually exist in each function.
    """
    result: dict = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        names: List[str] = []

        # Parameters
        args = node.args
        for arg in args.args + args.posonlyargs + args.kwonlyargs:
            names.append(arg.arg)
        if args.vararg:
            names.append(args.vararg.arg)
        if args.kwarg:
            names.append(args.kwarg.arg)

        # Body: assignments, for-loops, with-statements, except aliases
        for child in ast.walk(node):
            if isinstance(child, ast.Assign):
                for t in child.targets:
                    names.extend(_extract_assign_names(t))
            elif isinstance(child, (ast.AnnAssign, ast.AugAssign)):
                names.extend(_extract_assign_names(child.target))
            elif isinstance(child, (ast.For, ast.AsyncFor)):
                names.extend(_extract_assign_names(child.target))
            elif isinstance(child, ast.withitem) and child.optional_vars:
                names.extend(_extract_assign_names(child.optional_vars))
            elif isinstance(child, ast.ExceptHandler) and child.name:
                names.append(child.name)

        result[node.name] = sorted(set(names))
    return result


def _extract_assign_names(node: ast.expr) -> List[str]:
    """Recursively pull variable names out of an assignment target node."""
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        names: List[str] = []
        for elt in node.elts:
            names.extend(_extract_assign_names(elt))
        return names
    if isinstance(node, ast.Starred):
        return _extract_assign_names(node.value)
    return []


def get_all_attribute_accesses(tree: ast.Module) -> List[Tuple[str, int]]:
    """Return ``(full.name, line_number)`` for every attribute access in *tree*.

    Captures ``X.Y`` and ``X.Y.Z`` accesses regardless of whether they are
    used as callables, arguments, or stand-alone expressions.  This lets
    detection rules find ``HookType.TASK_STARTED`` style references that are
    passed as arguments to ``get_manager().dispatch(...)`` rather than called
    directly.
    """
    results: List[Tuple[str, int]] = []
    seen: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and hasattr(node, "lineno"):
            name = _extract_expr_name(node)
            if name:
                key = (name, node.lineno)
                if key not in seen:
                    seen.add(key)
                    results.append((name.lower(), node.lineno))
    return results


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
