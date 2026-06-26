"""Tests for LocationResolver."""
from __future__ import annotations

import pytest

from awcp_instrumentation.application.applicator.location_resolver import (
    LocationResolutionError,
    LocationResolver,
    ResolvedLocation,
)
from awcp_instrumentation.application.generator.models import InsertionLocation

RESOLVER = LocationResolver()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SIMPLE_SOURCE = """\
import os
import sys

def run():
    x = 1
    return x
"""

SOURCE_WITH_DOCSTRING = """\
import os

def compute():
    \"\"\"Do something.\"\"\"
    result = 42
    return result
"""

SOURCE_NO_IMPORTS = """\
def hello():
    print("hi")
"""

SOURCE_NESTED = """\
import os

class MyAgent:
    def execute(self):
        pass
"""


# ---------------------------------------------------------------------------
# ResolvedLocation
# ---------------------------------------------------------------------------

class TestResolvedLocation:
    def test_is_frozen(self) -> None:
        rl = ResolvedLocation(line_number=1, indent="")
        with pytest.raises((AttributeError, TypeError)):
            rl.line_number = 2  # type: ignore[misc]

    def test_warning_defaults_none(self) -> None:
        rl = ResolvedLocation(line_number=1, indent="")
        assert rl.warning is None


# ---------------------------------------------------------------------------
# TOP_OF_FILE
# ---------------------------------------------------------------------------

class TestTopOfFile:
    def test_resolves_line_1(self) -> None:
        r = RESOLVER.resolve(InsertionLocation.TOP_OF_FILE, SIMPLE_SOURCE)
        assert r.line_number == 1

    def test_resolves_empty_indent(self) -> None:
        r = RESOLVER.resolve(InsertionLocation.TOP_OF_FILE, SIMPLE_SOURCE)
        assert r.indent == ""

    def test_no_warning(self) -> None:
        r = RESOLVER.resolve(InsertionLocation.TOP_OF_FILE, SIMPLE_SOURCE)
        assert r.warning is None

    def test_works_with_empty_source(self) -> None:
        r = RESOLVER.resolve(InsertionLocation.TOP_OF_FILE, "")
        assert r.line_number == 1


# ---------------------------------------------------------------------------
# AFTER_IMPORTS
# ---------------------------------------------------------------------------

class TestAfterImports:
    def test_line_after_last_import(self) -> None:
        r = RESOLVER.resolve(InsertionLocation.AFTER_IMPORTS, SIMPLE_SOURCE)
        # imports are on lines 1-2; result should be line 3
        assert r.line_number == 3

    def test_indent_is_empty(self) -> None:
        r = RESOLVER.resolve(InsertionLocation.AFTER_IMPORTS, SIMPLE_SOURCE)
        assert r.indent == ""

    def test_no_warning_with_imports(self) -> None:
        r = RESOLVER.resolve(InsertionLocation.AFTER_IMPORTS, SIMPLE_SOURCE)
        assert r.warning is None

    def test_fallback_to_top_when_no_imports(self) -> None:
        r = RESOLVER.resolve(InsertionLocation.AFTER_IMPORTS, SOURCE_NO_IMPORTS)
        assert r.line_number == 1
        assert r.warning is not None
        assert "No import" in r.warning


# ---------------------------------------------------------------------------
# BEFORE_FUNCTION_BODY
# ---------------------------------------------------------------------------

class TestBeforeFunctionBody:
    def test_finds_function(self) -> None:
        r = RESOLVER.resolve(
            InsertionLocation.BEFORE_FUNCTION_BODY,
            SIMPLE_SOURCE,
            target_function="run",
        )
        # "x = 1" is line 5
        assert r.line_number == 5

    def test_indentation_detected(self) -> None:
        r = RESOLVER.resolve(
            InsertionLocation.BEFORE_FUNCTION_BODY,
            SIMPLE_SOURCE,
            target_function="run",
        )
        assert r.indent == "    "

    def test_skips_docstring(self) -> None:
        r = RESOLVER.resolve(
            InsertionLocation.BEFORE_FUNCTION_BODY,
            SOURCE_WITH_DOCSTRING,
            target_function="compute",
        )
        # docstring on line 4, "result = 42" on line 5
        assert r.line_number == 5

    def test_raises_when_function_not_found(self) -> None:
        with pytest.raises(LocationResolutionError, match="not found"):
            RESOLVER.resolve(
                InsertionLocation.BEFORE_FUNCTION_BODY,
                SIMPLE_SOURCE,
                target_function="nonexistent",
            )

    def test_fallback_when_no_target_function(self) -> None:
        r = RESOLVER.resolve(
            InsertionLocation.BEFORE_FUNCTION_BODY,
            SIMPLE_SOURCE,
            target_function=None,
        )
        assert r.warning is not None
        assert "BEFORE_FUNCTION_BODY" in r.warning

    def test_method_inside_class(self) -> None:
        r = RESOLVER.resolve(
            InsertionLocation.BEFORE_FUNCTION_BODY,
            SOURCE_NESTED,
            target_function="execute",
        )
        # "pass" is line 5
        assert r.line_number == 5
        assert r.indent == "        "  # 8 spaces (inside class)

    def test_no_warning_on_success(self) -> None:
        r = RESOLVER.resolve(
            InsertionLocation.BEFORE_FUNCTION_BODY,
            SIMPLE_SOURCE,
            target_function="run",
        )
        assert r.warning is None


# ---------------------------------------------------------------------------
# AROUND_FUNCTION
# ---------------------------------------------------------------------------

class TestAroundFunction:
    def test_falls_back_to_before_function_body(self) -> None:
        r_before = RESOLVER.resolve(
            InsertionLocation.BEFORE_FUNCTION_BODY,
            SIMPLE_SOURCE,
            target_function="run",
        )
        r_around = RESOLVER.resolve(
            InsertionLocation.AROUND_FUNCTION,
            SIMPLE_SOURCE,
            target_function="run",
        )
        assert r_around.line_number == r_before.line_number

    def test_produces_warning(self) -> None:
        r = RESOLVER.resolve(
            InsertionLocation.AROUND_FUNCTION,
            SIMPLE_SOURCE,
            target_function="run",
        )
        assert r.warning is not None
        assert "AROUND_FUNCTION" in r.warning

    def test_raises_when_function_missing(self) -> None:
        with pytest.raises(LocationResolutionError):
            RESOLVER.resolve(
                InsertionLocation.AROUND_FUNCTION,
                SIMPLE_SOURCE,
                target_function="no_such_fn",
            )


# ---------------------------------------------------------------------------
# INLINE
# ---------------------------------------------------------------------------

class TestInline:
    def test_with_target_function_resolves_to_body(self) -> None:
        r = RESOLVER.resolve(
            InsertionLocation.INLINE,
            SIMPLE_SOURCE,
            target_function="run",
        )
        # should equal BEFORE_FUNCTION_BODY position for "run"
        assert r.line_number == 5

    def test_with_target_function_has_warning(self) -> None:
        r = RESOLVER.resolve(
            InsertionLocation.INLINE,
            SIMPLE_SOURCE,
            target_function="run",
        )
        assert r.warning is not None
        assert "INLINE" in r.warning

    def test_without_target_function_falls_back_to_after_imports(self) -> None:
        r = RESOLVER.resolve(
            InsertionLocation.INLINE,
            SIMPLE_SOURCE,
            target_function=None,
        )
        assert r.line_number == 3  # after line-2 imports
        assert r.warning is not None

    def test_inline_no_target_no_imports_fallback(self) -> None:
        r = RESOLVER.resolve(
            InsertionLocation.INLINE,
            SOURCE_NO_IMPORTS,
            target_function=None,
        )
        assert r.line_number == 1


# ---------------------------------------------------------------------------
# Syntax error in source
# ---------------------------------------------------------------------------

class TestSyntaxError:
    def test_raises_resolution_error_on_bad_source(self) -> None:
        bad = "def broken(:\n    pass\n"
        with pytest.raises(LocationResolutionError, match="parsed"):
            RESOLVER.resolve(InsertionLocation.AFTER_IMPORTS, bad)
