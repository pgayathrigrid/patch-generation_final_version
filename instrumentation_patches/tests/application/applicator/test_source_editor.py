"""Tests for SourceEditor."""
from __future__ import annotations

import pytest

from awcp_instrumentation.application.applicator.source_editor import SourceEditor

EDITOR = SourceEditor()

SOURCE = """\
import os

def run():
    x = 1
    return x
"""


# ---------------------------------------------------------------------------
# insert_before_line — happy path
# ---------------------------------------------------------------------------

class TestInsertBeforeLine:
    def test_inserts_before_first_line(self) -> None:
        result = EDITOR.insert_before_line(SOURCE, 1, "# header")
        lines = result.splitlines()
        assert lines[0] == "# header"
        assert lines[1] == "import os"

    def test_inserts_before_middle_line(self) -> None:
        result = EDITOR.insert_before_line(SOURCE, 3, "# middle")
        lines = result.splitlines()
        assert "# middle" in lines
        idx = lines.index("# middle")
        assert lines[idx + 1] == "def run():"

    def test_inserts_before_last_line(self) -> None:
        result = EDITOR.insert_before_line(SOURCE, 5, "# before last")
        lines = result.splitlines()
        assert "# before last" in lines

    def test_original_content_preserved(self) -> None:
        result = EDITOR.insert_before_line(SOURCE, 1, "# top")
        assert "import os" in result
        assert "def run():" in result
        assert "    x = 1" in result

    def test_source_unchanged(self) -> None:
        original = SOURCE
        EDITOR.insert_before_line(SOURCE, 1, "# x")
        assert SOURCE == original

    def test_single_line_fragment(self) -> None:
        result = EDITOR.insert_before_line(SOURCE, 4, "    logger.info('start')")
        assert "    logger.info('start')" in result

    def test_multiline_fragment(self) -> None:
        fragment = "try:\n    risky()\nexcept Exception:\n    pass"
        result = EDITOR.insert_before_line(SOURCE, 4, fragment)
        assert "try:" in result
        assert "    risky()" in result

    def test_line_number_clamped_to_start(self) -> None:
        result = EDITOR.insert_before_line(SOURCE, -5, "# negative")
        lines = result.splitlines()
        assert lines[0] == "# negative"

    def test_line_number_beyond_end_appends(self) -> None:
        result = EDITOR.insert_before_line(SOURCE, 9999, "# end")
        assert "# end" in result
        assert result.endswith("# end\n")


# ---------------------------------------------------------------------------
# Indentation
# ---------------------------------------------------------------------------

class TestIndentation:
    def test_indent_applied_to_single_line(self) -> None:
        result = EDITOR.insert_before_line(SOURCE, 4, "logger.info('x')", indent="    ")
        assert "    logger.info('x')" in result

    def test_indent_applied_to_multiline(self) -> None:
        fragment = "a = 1\nb = 2"
        result = EDITOR.insert_before_line(SOURCE, 4, fragment, indent="    ")
        assert "    a = 1" in result
        assert "    b = 2" in result

    def test_relative_indent_preserved(self) -> None:
        fragment = "if True:\n    nested()"
        result = EDITOR.insert_before_line(SOURCE, 4, fragment, indent="    ")
        assert "    if True:" in result
        assert "        nested()" in result

    def test_empty_lines_not_indented(self) -> None:
        fragment = "a = 1\n\nb = 2"
        result = EDITOR.insert_before_line(SOURCE, 4, fragment, indent="    ")
        lines = result.splitlines()
        blank_lines = [l for l in lines if l == ""]
        assert blank_lines  # blank line preserved as empty

    def test_no_indent_when_empty_string(self) -> None:
        result = EDITOR.insert_before_line(SOURCE, 1, "x = 1", indent="")
        assert "x = 1" in result
        lines = result.splitlines()
        assert lines[0] == "x = 1"


# ---------------------------------------------------------------------------
# append_to_end
# ---------------------------------------------------------------------------

class TestAppendToEnd:
    def test_appends_fragment(self) -> None:
        result = EDITOR.append_to_end(SOURCE, "# appended")
        assert result.endswith("# appended\n")

    def test_appends_with_indent(self) -> None:
        result = EDITOR.append_to_end(SOURCE, "pass", indent="    ")
        assert "    pass" in result

    def test_adds_trailing_newline_to_source(self) -> None:
        no_newline = "import os"
        result = EDITOR.append_to_end(no_newline, "import sys")
        assert "import os\nimport sys" in result

    def test_original_content_present(self) -> None:
        result = EDITOR.append_to_end(SOURCE, "# footer")
        assert "import os" in result
        assert "def run():" in result


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_source_insert_at_1(self) -> None:
        result = EDITOR.insert_before_line("", 1, "# empty")
        assert "# empty" in result

    def test_fragment_gets_trailing_newline(self) -> None:
        result = EDITOR.insert_before_line(SOURCE, 1, "x = 1")
        assert result.startswith("x = 1\n")

    def test_fragment_already_has_newline_not_doubled(self) -> None:
        result = EDITOR.insert_before_line(SOURCE, 1, "x = 1\n")
        # Should NOT have "x = 1\n\n" at the start
        assert not result.startswith("x = 1\n\n")
