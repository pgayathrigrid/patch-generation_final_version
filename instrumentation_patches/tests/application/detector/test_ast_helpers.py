"""Tests for the private AST helper functions."""

import ast

import pytest

from awcp_instrumentation.application.detector.rules._ast_helpers import (
    get_all_call_sites,
    get_decorator_sites,
    get_import_names,
    get_try_except_lines,
)


def parse(source: str) -> ast.Module:
    return ast.parse(source)


class TestGetImportNames:
    def test_simple_import(self) -> None:
        tree = parse("import logging")
        assert "logging" in get_import_names(tree)

    def test_from_import(self) -> None:
        tree = parse("from opentelemetry import trace")
        names = get_import_names(tree)
        assert "opentelemetry" in names
        assert "trace" in names

    def test_aliased_import(self) -> None:
        tree = parse("import tenacity as t")
        assert "tenacity" in get_import_names(tree)

    def test_multiple_imports(self) -> None:
        tree = parse("import logging\nimport structlog")
        names = get_import_names(tree)
        assert "logging" in names
        assert "structlog" in names

    def test_empty_module(self) -> None:
        tree = parse("")
        assert get_import_names(tree) == set()

    def test_names_are_lowercased(self) -> None:
        tree = parse("import Logging")
        assert "logging" in get_import_names(tree)


class TestGetAllCallSites:
    def test_simple_call(self) -> None:
        tree = parse("foo()")
        sites = get_all_call_sites(tree)
        names = [n for n, _ in sites]
        assert "foo" in names

    def test_method_call(self) -> None:
        tree = parse("logger.info('msg')")
        sites = get_all_call_sites(tree)
        names = [n for n, _ in sites]
        assert "logger.info" in names

    def test_chained_call(self) -> None:
        tree = parse("a.b.c()")
        names = [n for n, _ in get_all_call_sites(tree)]
        assert "a.b.c" in names

    def test_call_inside_with_block(self) -> None:
        tree = parse("with tracer.start_span('op') as span:\n    pass")
        names = [n for n, _ in get_all_call_sites(tree)]
        assert "tracer.start_span" in names

    def test_line_number_captured(self) -> None:
        tree = parse("x = 1\nfoo()")
        for name, line in get_all_call_sites(tree):
            if name == "foo":
                assert line == 2
                return
        pytest.fail("foo() call not found")

    def test_names_are_lowercased(self) -> None:
        tree = parse("Logger.Info()")
        names = [n for n, _ in get_all_call_sites(tree)]
        assert "logger.info" in names

    def test_empty_module(self) -> None:
        tree = parse("")
        assert get_all_call_sites(tree) == []


class TestGetDecoratorSites:
    def test_simple_decorator(self) -> None:
        tree = parse("@retry\ndef fn(): pass")
        names = [n for n, _ in get_decorator_sites(tree)]
        assert "retry" in names

    def test_call_decorator(self) -> None:
        tree = parse("@retry(max_attempts=3)\ndef fn(): pass")
        names = [n for n, _ in get_decorator_sites(tree)]
        assert "retry" in names

    def test_attribute_decorator(self) -> None:
        tree = parse("@module.decorator\ndef fn(): pass")
        names = [n for n, _ in get_decorator_sites(tree)]
        assert "module.decorator" in names

    def test_class_decorator(self) -> None:
        tree = parse("@instrument\nclass Agent: pass")
        names = [n for n, _ in get_decorator_sites(tree)]
        assert "instrument" in names

    def test_no_decorators(self) -> None:
        tree = parse("def fn(): pass")
        assert get_decorator_sites(tree) == []

    def test_names_are_lowercased(self) -> None:
        tree = parse("@Retry\ndef fn(): pass")
        names = [n for n, _ in get_decorator_sites(tree)]
        assert "retry" in names


class TestGetTryExceptLines:
    def test_detects_try_except(self) -> None:
        tree = parse("try:\n    pass\nexcept Exception:\n    pass")
        lines = get_try_except_lines(tree)
        assert len(lines) == 1
        assert lines[0] == 1

    def test_multiple_try_blocks(self) -> None:
        source = "try:\n    pass\nexcept:\n    pass\ntry:\n    pass\nexcept:\n    pass"
        tree = parse(source)
        assert len(get_try_except_lines(tree)) == 2

    def test_no_try_blocks(self) -> None:
        tree = parse("x = 1")
        assert get_try_except_lines(tree) == []
