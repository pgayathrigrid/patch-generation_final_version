"""
Location resolver for the Patch Apply Engine.

Translates an ``InsertionLocation`` enum value into a concrete line number
and indentation string by inspecting the live source via the ``ast`` module.

No source code is modified here — this module is read-only.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Optional

from awcp_instrumentation.application.generator.models import InsertionLocation


# ---------------------------------------------------------------------------
# ResolvedLocation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResolvedLocation:
    """
    The result of resolving an ``InsertionLocation`` against real source code.

    Attributes:
        line_number: 1-indexed line number.  The code fragment will be
                     inserted immediately BEFORE this line.
        indent:      Indentation string to prepend to every line of the
                     inserted fragment so it aligns with the surrounding code.
        warning:     Set when the requested location was unavailable and a
                     fallback was used.  ``None`` on a clean resolution.
    """

    line_number: int
    indent: str
    warning: Optional[str] = None


# ---------------------------------------------------------------------------
# LocationResolutionError
# ---------------------------------------------------------------------------

class LocationResolutionError(Exception):
    """
    Raised when a location cannot be resolved and no valid fallback exists.

    Callers should convert this into an ``ApplyError`` so that one
    unresolvable location does not abort the rest of the apply run.
    """


# ---------------------------------------------------------------------------
# LocationResolver
# ---------------------------------------------------------------------------

class LocationResolver:
    """
    Resolves ``InsertionLocation`` values to concrete source positions.

    Uses Python's built-in ``ast`` module for analysis.  The source is
    never mutated.

    Notes on ``AROUND_FUNCTION``:
        Full body-wrapping (e.g. wrapping an entire function in try/except)
        requires structural source manipulation beyond simple line insertion.
        In this implementation ``AROUND_FUNCTION`` resolves to the same
        position as ``BEFORE_FUNCTION_BODY`` and records a warning.
        A future iteration using ``libcst`` can replace this method without
        changing the public interface.

    Notes on ``INLINE``:
        ``INLINE`` means the LLM has determined placement contextually.
        This resolver treats it as ``BEFORE_FUNCTION_BODY`` when a
        ``target_function`` is provided, or ``AFTER_IMPORTS`` otherwise,
        and records a warning in both cases.
    """

    def resolve(
        self,
        location: InsertionLocation,
        source: str,
        target_function: Optional[str] = None,
    ) -> ResolvedLocation:
        """
        Resolve *location* within *source*.

        Args:
            location:        The ``InsertionLocation`` from the ``PatchChange``.
            source:          Current Python source code to analyse.
            target_function: Required for ``BEFORE_FUNCTION_BODY`` and
                             ``AROUND_FUNCTION``.  Ignored for file-level
                             locations.

        Returns:
            A ``ResolvedLocation`` with the insertion line and indentation.

        Raises:
            LocationResolutionError: When the location cannot be resolved
                                     (e.g. ``target_function`` not found).
        """
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            raise LocationResolutionError(
                f"Source could not be parsed: {exc}"
            ) from exc

        if location == InsertionLocation.TOP_OF_FILE:
            return self._resolve_top_of_file()

        if location == InsertionLocation.AFTER_IMPORTS:
            return self._resolve_after_imports(tree, source)

        if location == InsertionLocation.BEFORE_FUNCTION_BODY:
            return self._resolve_before_function_body(tree, source, target_function)

        if location == InsertionLocation.AROUND_FUNCTION:
            return self._resolve_around_function(tree, source, target_function)

        if location == InsertionLocation.INLINE:
            return self._resolve_inline(tree, source, target_function)

        raise LocationResolutionError(f"Unknown InsertionLocation: {location!r}")

    # ------------------------------------------------------------------
    # Location-specific resolvers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_top_of_file() -> ResolvedLocation:
        return ResolvedLocation(line_number=1, indent="")

    @staticmethod
    def _resolve_after_imports(tree: ast.Module, source: str) -> ResolvedLocation:
        last_import_line = 0
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                end = getattr(node, "end_lineno", None) or node.lineno
                last_import_line = max(last_import_line, end)

        if last_import_line == 0:
            # No imports found — insert at the top of the file.
            return ResolvedLocation(
                line_number=1,
                indent="",
                warning="No import statements found; inserting at top of file.",
            )
        return ResolvedLocation(line_number=last_import_line + 1, indent="")

    def _resolve_before_function_body(
        self,
        tree: ast.Module,
        source: str,
        target_function: Optional[str],
    ) -> ResolvedLocation:
        if not target_function:
            # No target → fall back to after imports
            fallback = self._resolve_after_imports(tree, source)
            return ResolvedLocation(
                line_number=fallback.line_number,
                indent=fallback.indent,
                warning=(
                    "BEFORE_FUNCTION_BODY requested but no target_function provided; "
                    "falling back to AFTER_IMPORTS."
                ),
            )

        result = self._find_function_body_start(tree, source, target_function)
        if result is None:
            raise LocationResolutionError(
                f"Function '{target_function}' not found in source."
            )
        body_line, indent = result
        return ResolvedLocation(line_number=body_line, indent=indent)

    def _resolve_around_function(
        self,
        tree: ast.Module,
        source: str,
        target_function: Optional[str],
    ) -> ResolvedLocation:
        """
        AROUND_FUNCTION falls back to BEFORE_FUNCTION_BODY with a warning.

        Full body-wrapping requires structural CST manipulation (libcst).
        """
        resolved = self._resolve_before_function_body(tree, source, target_function)
        warning = (
            "AROUND_FUNCTION is not yet supported for full body-wrapping; "
            "code was inserted at the start of the function body instead. "
            "Upgrade to libcst-based applier for complete wrapping support."
        )
        return ResolvedLocation(
            line_number=resolved.line_number,
            indent=resolved.indent,
            warning=warning,
        )

    def _resolve_inline(
        self,
        tree: ast.Module,
        source: str,
        target_function: Optional[str],
    ) -> ResolvedLocation:
        """
        INLINE inserts after the initial variable assignments in the function
        body so that local variables like ``task_id`` are already defined.

        Falls back to BEFORE_FUNCTION_BODY if no initial assignments are found,
        or AFTER_IMPORTS when no target function is given.
        """
        if target_function:
            result = self._find_inline_point(tree, source, target_function)
            if result is not None:
                line_number, indent = result
                return ResolvedLocation(line_number=line_number, indent=indent)
            # Fall back to BEFORE_FUNCTION_BODY if function not found or empty
            resolved = self._resolve_before_function_body(tree, source, target_function)
            return ResolvedLocation(
                line_number=resolved.line_number,
                indent=resolved.indent,
                warning=(
                    f"INLINE location in '{target_function}' fell back to "
                    "start of function body."
                ),
            )

        fallback = self._resolve_after_imports(tree, source)
        return ResolvedLocation(
            line_number=fallback.line_number,
            indent=fallback.indent,
            warning=(
                "INLINE location with no target_function resolved to AFTER_IMPORTS. "
                "Review insertion point for correctness."
            ),
        )

    # ------------------------------------------------------------------
    # AST helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_function_body_start(
        tree: ast.Module,
        source: str,
        function_name: str,
    ) -> Optional[tuple[int, str]]:
        """
        Find the first statement line of *function_name* and its indentation.

        Returns ``(line_number, indent_string)`` or ``None`` if not found.
        """
        source_lines = source.splitlines()

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name != function_name:
                continue
            if not node.body:
                continue

            first_stmt = node.body[0]

            # Skip docstrings — insert after them, not before
            if (
                isinstance(first_stmt, ast.Expr)
                and isinstance(first_stmt.value, ast.Constant)
                and isinstance(first_stmt.value.value, str)
                and len(node.body) > 1
            ):
                first_stmt = node.body[1]

            line_number = first_stmt.lineno

            # Detect indentation from the source line
            if 1 <= line_number <= len(source_lines):
                raw_line = source_lines[line_number - 1]
                indent = raw_line[: len(raw_line) - len(raw_line.lstrip())]
            else:
                indent = "    "

            return line_number, indent

        return None

    @staticmethod
    def _find_inline_point(
        tree: ast.Module,
        source: str,
        function_name: str,
    ) -> Optional[tuple[int, str]]:
        """
        Find the first line AFTER any leading variable assignments in the
        function body of *function_name*.

        This lets INLINE patches reference local variables (like ``task_id``)
        that are assigned at the top of the function body, without needing to
        know exactly which line they appear on.

        Algorithm:
        1. Skip an optional leading docstring.
        2. Walk forward through body statements while they are pure assignments
           (``ast.Assign``, ``ast.AnnAssign``, ``ast.AugAssign``).
        3. Return the line immediately after the last such assignment, which is
           the first line of real logic where all setup variables exist.
        4. If there are no leading assignments, returns the first body line
           (same as ``_find_function_body_start``).
        """
        source_lines = source.splitlines()

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name != function_name:
                continue
            if not node.body:
                continue

            body = node.body
            start = 0

            # Skip leading docstring
            if (
                len(body) > 1
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                start = 1

            # Walk forward past initial assignment statements
            last_setup_end: Optional[int] = None
            for stmt in body[start:]:
                if isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                    last_setup_end = getattr(stmt, "end_lineno", None) or stmt.lineno
                else:
                    break

            if last_setup_end is not None:
                insert_line = last_setup_end + 1
            else:
                insert_line = body[start].lineno

            # Detect indentation from the insertion-point line
            if 1 <= insert_line <= len(source_lines):
                raw_line = source_lines[insert_line - 1]
                indent = raw_line[: len(raw_line) - len(raw_line.lstrip())]
            else:
                indent = "    "

            return insert_line, indent

        return None
