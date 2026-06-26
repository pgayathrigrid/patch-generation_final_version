"""
Import manager for the Patch Apply Engine.

Handles deduplication and injection of import statements so that patches
never introduce duplicate imports into the target source file.
"""
from __future__ import annotations

import ast
from typing import List, Set


class ImportManager:
    """
    Deduplicates import candidates against existing source imports and injects
    accepted imports into the correct position in the source.

    Deduplication strategy
    ~~~~~~~~~~~~~~~~~~~~~~
    An import candidate is considered a duplicate when ANY of the following
    match against the current source:

    1. **Exact string match** — ``"import logging"`` is already a source line.
    2. **Module-name match** — ``import logging as log`` is already present
       (same top-level module, different alias).
    3. **From-import match** — ``from opentelemetry import trace`` is already
       present (same module and imported name).

    This handles the most common real-world cases without requiring a full
    dependency-graph analysis.

    Injection position
    ~~~~~~~~~~~~~~~~~~
    New imports are inserted immediately after the last existing import block
    in the source.  When no imports exist, they are prepended at the top.
    """

    def filter_new_imports(
        self, source: str, candidates: List[str]
    ) -> List[str]:
        """
        Return only those *candidates* that are not already imported in *source*.

        Args:
            source:     Current Python source code.
            candidates: Import statements proposed by the patch.

        Returns:
            A filtered list containing only genuinely new imports.
        """
        existing = self._existing_import_keys(source)
        result: List[str] = []
        seen_in_candidates: Set[str] = set()

        for candidate in candidates:
            stripped = candidate.strip()
            if not stripped:
                continue
            keys = self._import_keys_for_statement(stripped)
            if not keys:
                continue
            # Skip if all keys are already present in the source
            if keys.issubset(existing):
                continue
            # Also deduplicate within the candidate list itself
            new_keys = keys - seen_in_candidates
            if not new_keys:
                continue
            seen_in_candidates.update(keys)
            result.append(stripped)

        return result

    def inject_imports(
        self, source: str, imports: List[str]
    ) -> str:
        """
        Insert *imports* into *source* after the last existing import block.

        If the source already has no imports, the new imports are prepended
        at the top of the file.

        Args:
            source:  Current Python source code.
            imports: Import statements to insert (already deduplicated).

        Returns:
            Source code with the new imports inserted.
        """
        if not imports:
            return source

        insertion_line = self._find_last_import_line(source)
        lines = source.splitlines(keepends=True)

        # Ensure last line ends with newline for clean concatenation
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"

        block = "\n".join(imports) + "\n"
        insert_idx = insertion_line  # 0-indexed: insert after index (insertion_line - 1)

        lines.insert(insert_idx, block)
        return "".join(lines)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _existing_import_keys(source: str) -> Set[str]:
        """
        Return a set of normalised import keys already present in *source*.

        Key format:
        - ``import X``             → ``"X"``
        - ``import X as Y``        → ``"X"``  (alias ignored)
        - ``from X import Y``      → ``"X.Y"``
        - ``from X import Y as Z`` → ``"X.Y"`` (alias ignored)
        """
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return set()

        keys: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    keys.add(alias.name.lower())
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    keys.add(f"{module}.{alias.name}".lower())
        return keys

    @staticmethod
    def _import_keys_for_statement(statement: str) -> Set[str]:
        """
        Parse *statement* and return its import keys (same format as above).

        Returns an empty set if the statement is not a valid import.
        """
        try:
            tree = ast.parse(statement.strip())
        except SyntaxError:
            return set()

        keys: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    keys.add(alias.name.lower())
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    keys.add(f"{module}.{alias.name}".lower())
        return keys

    @staticmethod
    def _find_last_import_line(source: str) -> int:
        """
        Return the 0-indexed position to insert after the last import.

        E.g. if the last import is on line 3 (1-indexed), returns 3
        so that the new import is inserted after index 2 (0-indexed).
        """
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return 0

        last_line = 0
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                end = getattr(node, "end_lineno", None) or node.lineno
                last_line = max(last_line, end)

        return last_line  # 0-indexed insert-after position
