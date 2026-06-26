"""Tests for JsonFormatter."""
from __future__ import annotations

import json
from datetime import datetime

import pytest

from awcp_instrumentation.application.reporter.builder import ValidationReportBuilder
from awcp_instrumentation.application.reporter.json_formatter import JsonFormatter
from awcp_instrumentation.application.reporter.models import (
    AgentInfo,
    BuiltReport,
    ExecutionSummary,
    HookRecommendation,
    HookResult,
    ObservationSummary,
    ReportError,
    ReportWarning,
)
from awcp_instrumentation.application.sandbox.models import SandboxValidationResult

FORMATTER = JsonFormatter()
BUILDER = ValidationReportBuilder()


def build(result: SandboxValidationResult) -> BuiltReport:
    return BUILDER.build(result)


# ---------------------------------------------------------------------------
# format_name
# ---------------------------------------------------------------------------

class TestFormatName:
    def test_format_name_is_json(self) -> None:
        assert FORMATTER.format_name == "json"


# ---------------------------------------------------------------------------
# Output is valid JSON
# ---------------------------------------------------------------------------

class TestValidJson:
    def test_returns_valid_json(self, fully_passing_result: SandboxValidationResult) -> None:
        output = FORMATTER.format(build(fully_passing_result))
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_partial_failure_valid_json(self, partial_failure_result: SandboxValidationResult) -> None:
        output = FORMATTER.format(build(partial_failure_result))
        json.loads(output)  # must not raise

    def test_syntax_error_valid_json(self, syntax_error_result: SandboxValidationResult) -> None:
        output = FORMATTER.format(build(syntax_error_result))
        json.loads(output)  # must not raise


# ---------------------------------------------------------------------------
# Top-level fields present
# ---------------------------------------------------------------------------

class TestTopLevelFields:
    def _parsed(self, result: SandboxValidationResult) -> dict:
        return json.loads(FORMATTER.format(build(result)))

    def test_agent_field(self, fully_passing_result: SandboxValidationResult) -> None:
        assert "agent" in self._parsed(fully_passing_result)

    def test_overall_status_field(self, fully_passing_result: SandboxValidationResult) -> None:
        data = self._parsed(fully_passing_result)
        assert data["overall_status"] == "passed"

    def test_generated_at_field(self, fully_passing_result: SandboxValidationResult) -> None:
        data = self._parsed(fully_passing_result)
        assert "generated_at" in data

    def test_execution_summary_field(self, fully_passing_result: SandboxValidationResult) -> None:
        data = self._parsed(fully_passing_result)
        assert "execution_summary" in data

    def test_hook_results_field(self, fully_passing_result: SandboxValidationResult) -> None:
        data = self._parsed(fully_passing_result)
        assert "hook_results" in data
        assert isinstance(data["hook_results"], list)

    def test_missing_hooks_field(self, fully_passing_result: SandboxValidationResult) -> None:
        data = self._parsed(fully_passing_result)
        assert "missing_hooks" in data

    def test_observations_field(self, fully_passing_result: SandboxValidationResult) -> None:
        data = self._parsed(fully_passing_result)
        assert "observations" in data

    def test_errors_field(self, fully_passing_result: SandboxValidationResult) -> None:
        data = self._parsed(fully_passing_result)
        assert "errors" in data

    def test_warnings_field(self, fully_passing_result: SandboxValidationResult) -> None:
        data = self._parsed(fully_passing_result)
        assert "warnings" in data

    def test_recommendations_field(self, fully_passing_result: SandboxValidationResult) -> None:
        data = self._parsed(fully_passing_result)
        assert "recommendations" in data

    def test_summary_field(self, fully_passing_result: SandboxValidationResult) -> None:
        data = self._parsed(fully_passing_result)
        assert "summary" in data
        assert data["summary"] != ""

    def test_count_fields(self, fully_passing_result: SandboxValidationResult) -> None:
        data = self._parsed(fully_passing_result)
        assert "total_hooks" in data
        assert "passed_hooks" in data
        assert "failed_hooks" in data
        assert "skipped_hooks" in data


# ---------------------------------------------------------------------------
# datetime serialisation
# ---------------------------------------------------------------------------

class TestDatetimeSerialization:
    def test_generated_at_is_string(self, fully_passing_result: SandboxValidationResult) -> None:
        data = json.loads(FORMATTER.format(build(fully_passing_result)))
        assert isinstance(data["generated_at"], str)

    def test_generated_at_parseable(self, fully_passing_result: SandboxValidationResult) -> None:
        data = json.loads(FORMATTER.format(build(fully_passing_result)))
        # Should be ISO 8601 parseable
        datetime.fromisoformat(data["generated_at"])


# ---------------------------------------------------------------------------
# Content correctness
# ---------------------------------------------------------------------------

class TestContentCorrectness:
    def test_agent_name_in_json(self, fully_passing_result: SandboxValidationResult) -> None:
        data = json.loads(FORMATTER.format(build(fully_passing_result)))
        assert data["agent"]["name"] == "test_agent"

    def test_hook_result_status(self, fully_passing_result: SandboxValidationResult) -> None:
        data = json.loads(FORMATTER.format(build(fully_passing_result)))
        assert data["hook_results"][0]["status"] == "passed"

    def test_error_in_json(self, partial_failure_result: SandboxValidationResult) -> None:
        data = json.loads(FORMATTER.format(build(partial_failure_result)))
        assert len(data["errors"]) == 1
        assert data["errors"][0]["error_type"] == "MissingFragment"

    def test_missing_hooks_in_json(self, partial_failure_result: SandboxValidationResult) -> None:
        data = json.loads(FORMATTER.format(build(partial_failure_result)))
        assert "task_failed" in data["missing_hooks"]

    def test_recommendation_in_json(self, partial_failure_result: SandboxValidationResult) -> None:
        data = json.loads(FORMATTER.format(build(partial_failure_result)))
        assert len(data["recommendations"]) == 1
        assert data["recommendations"][0]["category"] == "task_failed"


# ---------------------------------------------------------------------------
# Custom constructor options
# ---------------------------------------------------------------------------

class TestConstructorOptions:
    def test_custom_indent(self, fully_passing_result: SandboxValidationResult) -> None:
        formatter = JsonFormatter(indent=4)
        output = formatter.format(build(fully_passing_result))
        # 4-space indent: lines should have 4-space padding
        assert "    " in output

    def test_format_name_still_json(self) -> None:
        assert JsonFormatter(indent=0).format_name == "json"
