"""
Text-based source editor for the Patch Apply Engine.

Performs line-level insertions into Python source code while preserving
existing formatting and applying correct indentation to inserted fragments.

This module never parses Python — all operations are pure text manipulation.
AST analysis for finding insertion points is handled by ``LocationResolver``.
"""
from __future__ import annotations


class SourceEditor:
    """
    Inserts code fragments into Python source code at specified line positions.

    All methods are pure: they receive source as a string and return a new
    string.  The original source is never mutated.

    Indentation handling
    ~~~~~~~~~~~~~~~~~~~~
    The ``indent`` argument to ``insert_before_line`` specifies the base
    indentation that should be prepended to every line of the fragment.
    Relative indentation *within* the fragment is preserved.

    Example::

        fragment = "try:\\n    risky_op()\\nexcept Exception as e:\\n    handle(e)"
        # With indent="    " (4 spaces):
        #     try:
        #         risky_op()
        #     except Exception as e:
        #         handle(e)
    """

    def insert_before_line(
        self,
        source: str,
        line_number: int,
        fragment: str,
        indent: str = "",
    ) -> str:
        """
        Insert *fragment* immediately before *line_number* in *source*.

        Args:
            source:      Current Python source code.
            line_number: 1-indexed target line.  The fragment is inserted so
                         that it appears before this line in the result.
                         Clamped to [1, len(lines)+1].
            fragment:    Code to insert.  May be multi-line.
                         Must not include a trailing blank line (the method
                         adds a newline after the block automatically).
            indent:      Indentation prefix applied to every non-empty line of
                         *fragment*.

        Returns:
            New source string with the fragment inserted.
        """
        lines = source.splitlines(keepends=True)

        # Ensure the last line ends with a newline for clean concatenation.
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"

        indented = self._apply_base_indent(fragment, indent)
        if not indented.endswith("\n"):
            indented += "\n"

        # Clamp insertion index to valid range.
        insert_idx = max(0, min(line_number - 1, len(lines)))
        lines.insert(insert_idx, indented)
        return "".join(lines)

    def append_to_end(self, source: str, fragment: str, indent: str = "") -> str:
        """
        Append *fragment* at the very end of *source*.

        Used as a last-resort fallback when no valid insertion point is found.
        """
        if not source.endswith("\n"):
            source += "\n"
        indented = self._apply_base_indent(fragment, indent)
        if not indented.endswith("\n"):
            indented += "\n"
        return source + indented

    # ------------------------------------------------------------------
    # Indentation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_base_indent(code: str, base_indent: str) -> str:
        """
        Prepend *base_indent* to every non-empty line in *code*.

        Empty lines (containing only whitespace) are left as blank lines
        rather than filled with the indent, which avoids trailing-whitespace
        issues in the output.
        """
        if not base_indent:
            return code
        result_lines = []
        for line in code.splitlines():
            if line.strip():
                result_lines.append(base_indent + line)
            else:
                result_lines.append("")
        return "\n".join(result_lines)
