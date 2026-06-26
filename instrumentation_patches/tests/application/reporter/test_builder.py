"""Tests for ValidationReportBuilder."""
from __future__ import annotations

from datetime import datetime

import pytest

from awcp_instrumentation.application.reporter.builder import ValidationReportBuilder
from awcp_instrumentation.application.reporter.models import BuiltReport
from awcp_instrumentation.application.sandbox.models import SandboxValidationResult
from awcp_instrumentation.domain.enums.hook_category import HookCategory

BUILDER = ValidationReportBuilder()


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

class TestReturnType:
    def test_returns_built_report(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        assert isinstance(result, BuiltReport)


# ---------------------------------------------------------------------------
# AgentInfo
# ---------------------------------------------------------------------------

class TestAgentInfo:
    def test_agent_name_extracted(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        assert result.agent.name == "test_agent"

    def test_agent_path_is_string_or_none(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        # path is either None or a string (AgentSource.from_string derives it from the name)
        assert result.agent.path is None or isinstance(result.agent.path, str)


# ---------------------------------------------------------------------------
# Overall status
# ---------------------------------------------------------------------------

class TestOverallStatus:
    def test_passed_when_all_pass(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        assert result.overall_status == "passed"
        assert result.is_passing is True

    def test_failed_when_any_fail(self, partial_failure_result: SandboxValidationResult) -> None:
        result = BUILDER.build(partial_failure_result)
        assert result.overall_status == "failed"
        assert result.is_passing is False

    def test_failed_on_syntax_error(self, syntax_error_result: SandboxValidationResult) -> None:
        result = BUILDER.build(syntax_error_result)
        assert result.overall_status == "failed"


# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------

class TestTimestamp:
    def test_generated_at_is_datetime(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        assert isinstance(result.generated_at, datetime)


# ---------------------------------------------------------------------------
# ExecutionSummary
# ---------------------------------------------------------------------------

class TestExecutionSummary:
    def test_environment_name(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        assert result.execution_summary.environment == "local_python"

    def test_executed_true(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        assert result.execution_summary.executed is True

    def test_executed_false_on_syntax_error(self, syntax_error_result: SandboxValidationResult) -> None:
        result = BUILDER.build(syntax_error_result)
        assert result.execution_summary.executed is False

    def test_syntax_valid_true(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        assert result.execution_summary.syntax_valid is True

    def test_syntax_valid_false(self, syntax_error_result: SandboxValidationResult) -> None:
        result = BUILDER.build(syntax_error_result)
        assert result.execution_summary.syntax_valid is False

    def test_mode_value(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        assert result.execution_summary.mode == "full_execution"

    def test_duration_ms(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        assert result.execution_summary.duration_ms == 42.0

    def test_stdout_excerpt(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        assert "task_started" in result.execution_summary.stdout_excerpt

    def test_stdout_excerpt_capped(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        assert len(result.execution_summary.stdout_excerpt) <= 500


# ---------------------------------------------------------------------------
# Hook results
# ---------------------------------------------------------------------------

class TestHookResults:
    def test_one_result_per_hook(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        assert len(result.hook_results) == 1

    def test_hook_status_passed(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        assert result.hook_results[0].status == "passed"

    def test_hook_status_failed(self, partial_failure_result: SandboxValidationResult) -> None:
        result = BUILDER.build(partial_failure_result)
        statuses = {r.category: r.status for r in result.hook_results}
        assert statuses["task_failed"] == "failed"
        assert statuses["task_started"] == "passed"

    def test_hook_category_value(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        assert result.hook_results[0].category == "task_started"

    def test_hook_name(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        assert result.hook_results[0].hook_name == "task_started_hook"

    def test_hook_message_populated(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        assert result.hook_results[0].message != ""


# ---------------------------------------------------------------------------
# Counts
# ---------------------------------------------------------------------------

class TestCounts:
    def test_total_hooks(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        assert result.total_hooks == 1

    def test_passed_hooks(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        assert result.passed_hooks == 1
        assert result.failed_hooks == 0

    def test_partial_counts(self, partial_failure_result: SandboxValidationResult) -> None:
        result = BUILDER.build(partial_failure_result)
        assert result.total_hooks == 2
        assert result.passed_hooks == 1
        assert result.failed_hooks == 1


# ---------------------------------------------------------------------------
# Missing hooks
# ---------------------------------------------------------------------------

class TestMissingHooks:
    def test_empty_when_all_pass(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        assert result.missing_hooks == []

    def test_failed_category_in_missing(self, partial_failure_result: SandboxValidationResult) -> None:
        result = BUILDER.build(partial_failure_result)
        assert "task_failed" in result.missing_hooks

    def test_passed_category_not_in_missing(self, partial_failure_result: SandboxValidationResult) -> None:
        result = BUILDER.build(partial_failure_result)
        assert "task_started" not in result.missing_hooks


# ---------------------------------------------------------------------------
# Observations
# ---------------------------------------------------------------------------

class TestObservations:
    def test_observations_populated(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        assert len(result.observations) == 1

    def test_observation_fields(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        obs = result.observations[0]
        assert obs.category == "task_started"
        assert obs.observed is True
        assert obs.collector == "output_pattern"

    def test_empty_observations_when_not_executed(self, syntax_error_result: SandboxValidationResult) -> None:
        result = BUILDER.build(syntax_error_result)
        assert result.observations == []


# ---------------------------------------------------------------------------
# Errors and warnings
# ---------------------------------------------------------------------------

class TestErrors:
    def test_no_errors_when_passing(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        assert result.errors == []

    def test_errors_populated(self, partial_failure_result: SandboxValidationResult) -> None:
        result = BUILDER.build(partial_failure_result)
        assert len(result.errors) == 1
        assert result.errors[0].error_type == "MissingFragment"
        assert result.errors[0].category == "task_failed"

    def test_syntax_error_in_errors(self, syntax_error_result: SandboxValidationResult) -> None:
        result = BUILDER.build(syntax_error_result)
        assert any(e.error_type == "SyntaxError" for e in result.errors)


class TestWarnings:
    def test_no_warnings_when_passing(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        assert result.warnings == []

    def test_warnings_populated(self, partial_failure_result: SandboxValidationResult) -> None:
        result = BUILDER.build(partial_failure_result)
        assert len(result.warnings) == 1
        assert result.warnings[0].category == "task_started"


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

class TestRecommendations:
    def test_no_recommendations_when_all_pass(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        assert result.recommendations == []

    def test_recommendation_for_failed_hook(self, partial_failure_result: SandboxValidationResult) -> None:
        result = BUILDER.build(partial_failure_result)
        assert len(result.recommendations) == 1
        rec = result.recommendations[0]
        assert rec.category == "task_failed"
        assert rec.hook_name == "task_failed_hook"

    def test_recommendation_draws_from_gap(self, partial_failure_result: SandboxValidationResult) -> None:
        result = BUILDER.build(partial_failure_result)
        rec = result.recommendations[0]
        assert "task_failed" in rec.action.lower()
        assert rec.severity == "high"

    def test_recommendation_has_hint(self, partial_failure_result: SandboxValidationResult) -> None:
        result = BUILDER.build(partial_failure_result)
        assert result.recommendations[0].hint != ""

    def test_syntax_error_produces_recommendation(self, syntax_error_result: SandboxValidationResult) -> None:
        result = BUILDER.build(syntax_error_result)
        assert len(result.recommendations) == 1


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

class TestSummary:
    def test_summary_non_empty(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        assert result.summary != ""

    def test_summary_contains_status(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        assert "PASSED" in result.summary

    def test_summary_contains_failed_count(self, partial_failure_result: SandboxValidationResult) -> None:
        result = BUILDER.build(partial_failure_result)
        assert "FAILED" in result.summary
        assert "1 failed" in result.summary

    def test_summary_contains_runtime(self, fully_passing_result: SandboxValidationResult) -> None:
        result = BUILDER.build(fully_passing_result)
        assert "Runtime" in result.summary or "ms" in result.summary
