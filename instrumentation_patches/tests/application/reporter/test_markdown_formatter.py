"""Tests for MarkdownFormatter."""
from __future__ import annotations

import pytest

from awcp_instrumentation.application.reporter.builder import ValidationReportBuilder
from awcp_instrumentation.application.reporter.markdown_formatter import MarkdownFormatter
from awcp_instrumentation.application.reporter.models import BuiltReport
from awcp_instrumentation.application.sandbox.models import SandboxValidationResult

FORMATTER = MarkdownFormatter()
BUILDER = ValidationReportBuilder()


def build(result: SandboxValidationResult) -> BuiltReport:
    return BUILDER.build(result)


# ---------------------------------------------------------------------------
# format_name
# ---------------------------------------------------------------------------

class TestFormatName:
    def test_format_name_is_markdown(self) -> None:
        assert FORMATTER.format_name == "markdown"


# ---------------------------------------------------------------------------
# Output is non-empty string
# ---------------------------------------------------------------------------

class TestOutputIsString:
    def test_returns_string(self, fully_passing_result: SandboxValidationResult) -> None:
        output = FORMATTER.format(build(fully_passing_result))
        assert isinstance(output, str)
        assert len(output) > 0

    def test_ends_with_newline(self, fully_passing_result: SandboxValidationResult) -> None:
        output = FORMATTER.format(build(fully_passing_result))
        assert output.endswith("\n")


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

class TestHeader:
    def test_h1_present(self, fully_passing_result: SandboxValidationResult) -> None:
        output = FORMATTER.format(build(fully_passing_result))
        assert output.startswith("#")

    def test_agent_name_in_header(self, fully_passing_result: SandboxValidationResult) -> None:
        output = FORMATTER.format(build(fully_passing_result))
        assert "test_agent" in output.splitlines()[0]

    def test_status_icon_in_header_passing(self, fully_passing_result: SandboxValidationResult) -> None:
        output = FORMATTER.format(build(fully_passing_result))
        assert "✅" in output.splitlines()[0]

    def test_status_icon_in_header_failing(self, partial_failure_result: SandboxValidationResult) -> None:
        output = FORMATTER.format(build(partial_failure_result))
        assert "❌" in output.splitlines()[0]


# ---------------------------------------------------------------------------
# Required sections present
# ---------------------------------------------------------------------------

class TestSectionsPresent:
    def test_summary_section(self, fully_passing_result: SandboxValidationResult) -> None:
        assert "## Summary" in FORMATTER.format(build(fully_passing_result))

    def test_agent_section(self, fully_passing_result: SandboxValidationResult) -> None:
        assert "## Agent Information" in FORMATTER.format(build(fully_passing_result))

    def test_execution_section(self, fully_passing_result: SandboxValidationResult) -> None:
        assert "## Execution Summary" in FORMATTER.format(build(fully_passing_result))

    def test_hook_results_section(self, fully_passing_result: SandboxValidationResult) -> None:
        assert "## Hook Validation Results" in FORMATTER.format(build(fully_passing_result))

    def test_errors_section_always_present(self, fully_passing_result: SandboxValidationResult) -> None:
        assert "## Errors" in FORMATTER.format(build(fully_passing_result))

    def test_warnings_section_always_present(self, fully_passing_result: SandboxValidationResult) -> None:
        assert "## Warnings" in FORMATTER.format(build(fully_passing_result))

    def test_evidence_section(self, fully_passing_result: SandboxValidationResult) -> None:
        assert "## Evidence" in FORMATTER.format(build(fully_passing_result))


# ---------------------------------------------------------------------------
# Conditional sections
# ---------------------------------------------------------------------------

class TestConditionalSections:
    def test_missing_hooks_section_only_when_failures(
        self, fully_passing_result: SandboxValidationResult, partial_failure_result: SandboxValidationResult
    ) -> None:
        passing_output = FORMATTER.format(build(fully_passing_result))
        failing_output = FORMATTER.format(build(partial_failure_result))
        assert "## Missing" not in passing_output
        assert "## Missing" in failing_output

    def test_observations_section_only_when_present(
        self, fully_passing_result: SandboxValidationResult, syntax_error_result: SandboxValidationResult
    ) -> None:
        passing_output = FORMATTER.format(build(fully_passing_result))
        syntax_output = FORMATTER.format(build(syntax_error_result))
        assert "## Runtime Observations" in passing_output
        assert "## Runtime Observations" not in syntax_output

    def test_recommendations_section_only_when_needed(
        self, fully_passing_result: SandboxValidationResult, partial_failure_result: SandboxValidationResult
    ) -> None:
        passing_output = FORMATTER.format(build(fully_passing_result))
        failing_output = FORMATTER.format(build(partial_failure_result))
        assert "## Recommendations" not in passing_output
        assert "## Recommendations" in failing_output


# ---------------------------------------------------------------------------
# Content correctness
# ---------------------------------------------------------------------------

class TestContentCorrectness:
    def test_overall_status_in_summary(self, fully_passing_result: SandboxValidationResult) -> None:
        output = FORMATTER.format(build(fully_passing_result))
        assert "PASSED" in output

    def test_failed_status_in_summary(self, partial_failure_result: SandboxValidationResult) -> None:
        output = FORMATTER.format(build(partial_failure_result))
        assert "FAILED" in output

    def test_hook_name_in_results_table(self, fully_passing_result: SandboxValidationResult) -> None:
        output = FORMATTER.format(build(fully_passing_result))
        assert "task_started_hook" in output

    def test_passed_icon_in_results(self, fully_passing_result: SandboxValidationResult) -> None:
        output = FORMATTER.format(build(fully_passing_result))
        assert "✅" in output

    def test_failed_icon_in_results(self, partial_failure_result: SandboxValidationResult) -> None:
        output = FORMATTER.format(build(partial_failure_result))
        assert "❌" in output

    def test_environment_name_in_execution(self, fully_passing_result: SandboxValidationResult) -> None:
        output = FORMATTER.format(build(fully_passing_result))
        assert "local_python" in output

    def test_missing_hook_category_listed(self, partial_failure_result: SandboxValidationResult) -> None:
        output = FORMATTER.format(build(partial_failure_result))
        assert "task_failed" in output

    def test_error_type_in_errors_section(self, partial_failure_result: SandboxValidationResult) -> None:
        output = FORMATTER.format(build(partial_failure_result))
        assert "MissingFragment" in output

    def test_no_errors_message(self, fully_passing_result: SandboxValidationResult) -> None:
        output = FORMATTER.format(build(fully_passing_result))
        assert "_No errors._" in output

    def test_no_warnings_message(self, fully_passing_result: SandboxValidationResult) -> None:
        output = FORMATTER.format(build(fully_passing_result))
        assert "_No warnings._" in output

    def test_recommendation_action_in_output(self, partial_failure_result: SandboxValidationResult) -> None:
        output = FORMATTER.format(build(partial_failure_result))
        assert "**Action:**" in output

    def test_evidence_not_executed_message(self, syntax_error_result: SandboxValidationResult) -> None:
        output = FORMATTER.format(build(syntax_error_result))
        assert "not executed" in output.lower() or "syntax" in output.lower()

    def test_markdown_pipe_tables(self, fully_passing_result: SandboxValidationResult) -> None:
        output = FORMATTER.format(build(fully_passing_result))
        # GFM tables use | as delimiter
        assert "|" in output

    def test_observation_collector_name(self, fully_passing_result: SandboxValidationResult) -> None:
        output = FORMATTER.format(build(fully_passing_result))
        assert "output_pattern" in output

    def test_summary_line_in_blockquote(self, fully_passing_result: SandboxValidationResult) -> None:
        output = FORMATTER.format(build(fully_passing_result))
        # Summary is rendered as a blockquote line
        assert "> " in output


# ---------------------------------------------------------------------------
# include_stdout_stderr option
# ---------------------------------------------------------------------------

class TestIncludeStdoutStderr:
    def test_stdout_section_when_enabled(self, fully_passing_result: SandboxValidationResult) -> None:
        formatter = MarkdownFormatter(include_stdout_stderr=True)
        output = formatter.format(build(fully_passing_result))
        assert "Hook Output Detail" in output

    def test_no_stdout_section_when_disabled(self, fully_passing_result: SandboxValidationResult) -> None:
        output = FORMATTER.format(build(fully_passing_result))
        assert "Hook Output Detail" not in output
