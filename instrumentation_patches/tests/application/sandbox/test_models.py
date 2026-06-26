"""Tests for Sandbox Validation Engine models."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from awcp_instrumentation.application.sandbox.models import (
    ExecutionRecord,
    RuntimeObservation,
    SandboxExecutionMode,
    SandboxValidationResult,
    ValidationError,
    ValidationEvidence,
    ValidationWarning,
)
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.entities.validation_report import (
    HookValidationResult,
    ValidationReport,
)
from awcp_instrumentation.domain.enums.hook_category import HookCategory
from awcp_instrumentation.domain.enums.validation_status import ValidationStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_record(
    stdout: str = "",
    stderr: str = "",
    exit_code: int = 0,
    duration_ms: float = 10.0,
    timed_out: bool = False,
) -> ExecutionRecord:
    return ExecutionRecord(
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        duration_ms=duration_ms,
        timed_out=timed_out,
    )


def make_evidence(
    executed: bool = True,
    syntax_valid: bool = True,
    exit_code: int | None = 0,
    timed_out: bool = False,
    observations: list | None = None,
) -> ValidationEvidence:
    return ValidationEvidence(
        execution_mode=SandboxExecutionMode.FULL_EXECUTION,
        environment_name="local_python",
        executed=executed,
        stdout="",
        stderr="",
        exit_code=exit_code,
        duration_ms=10.0 if executed else None,
        timed_out=timed_out,
        syntax_valid=syntax_valid,
        observations=observations or [],
    )


def make_hook(category: HookCategory = HookCategory.TASK_STARTED) -> GovernanceHook:
    return GovernanceHook(
        category=category,
        name=f"{category.value}_hook",
        description="test",
        signature="hook()",
        line_number=None,
    )


def make_report(
    status: ValidationStatus = ValidationStatus.PASSED,
    hook_results: list | None = None,
) -> ValidationReport:
    return ValidationReport(
        agent_name="test_agent",
        overall_status=status,
        hook_results=hook_results or [],
    )


def make_svr(
    report: ValidationReport | None = None,
    evidence: ValidationEvidence | None = None,
    errors: list | None = None,
    warnings: list | None = None,
) -> SandboxValidationResult:
    patched = MagicMock()
    return SandboxValidationResult(
        patched_source_ref=patched,
        report=report or make_report(),
        evidence=evidence or make_evidence(),
        errors=errors or [],
        warnings=warnings or [],
        generated_at=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# SandboxExecutionMode
# ---------------------------------------------------------------------------

class TestSandboxExecutionMode:
    def test_values(self) -> None:
        assert SandboxExecutionMode.SYNTAX_ONLY.value == "syntax_only"
        assert SandboxExecutionMode.IMPORT_CHECK.value == "import_check"
        assert SandboxExecutionMode.FULL_EXECUTION.value == "full_execution"

    def test_is_str_enum(self) -> None:
        assert isinstance(SandboxExecutionMode.SYNTAX_ONLY, str)


# ---------------------------------------------------------------------------
# ExecutionRecord
# ---------------------------------------------------------------------------

class TestExecutionRecord:
    def test_is_frozen(self) -> None:
        r = make_record()
        with pytest.raises((AttributeError, TypeError)):
            r.stdout = "x"  # type: ignore[misc]

    def test_succeeded_true_on_zero_exit(self) -> None:
        assert make_record(exit_code=0).succeeded is True

    def test_succeeded_false_on_nonzero(self) -> None:
        assert make_record(exit_code=1).succeeded is False

    def test_succeeded_false_on_timeout(self) -> None:
        assert make_record(exit_code=0, timed_out=True).succeeded is False

    def test_combined_output(self) -> None:
        r = make_record(stdout="hello", stderr="world")
        assert "hello" in r.combined_output
        assert "world" in r.combined_output

    def test_metadata_default_empty(self) -> None:
        assert make_record().metadata == {}

    def test_metadata_preserved(self) -> None:
        r = ExecutionRecord(
            stdout="", stderr="", exit_code=0,
            duration_ms=1.0, timed_out=False,
            metadata={"trace_id": "abc123"},
        )
        assert r.metadata["trace_id"] == "abc123"


# ---------------------------------------------------------------------------
# ValidationError
# ---------------------------------------------------------------------------

class TestValidationError:
    def test_is_frozen(self) -> None:
        e = ValidationError(
            category=HookCategory.TASK_FAILED, error_type="SyntaxError", message="x"
        )
        with pytest.raises((AttributeError, TypeError)):
            e.message = "y"  # type: ignore[misc]

    def test_optional_fields_default_none(self) -> None:
        e = ValidationError(
            category=HookCategory.TASK_FAILED, error_type="RuntimeError", message="oops"
        )
        assert e.traceback is None
        assert e.line_number is None

    def test_all_fields_stored(self) -> None:
        e = ValidationError(
            category=HookCategory.LLM_CALL,
            error_type="TimeoutError",
            message="timed out",
            traceback="Traceback ...",
            line_number=42,
        )
        assert e.category == HookCategory.LLM_CALL
        assert e.error_type == "TimeoutError"
        assert e.traceback == "Traceback ..."
        assert e.line_number == 42


# ---------------------------------------------------------------------------
# ValidationWarning
# ---------------------------------------------------------------------------

class TestValidationWarning:
    def test_is_frozen(self) -> None:
        w = ValidationWarning(category=HookCategory.BUDGET_WARN, message="warn")
        with pytest.raises((AttributeError, TypeError)):
            w.message = "other"  # type: ignore[misc]

    def test_fields(self) -> None:
        w = ValidationWarning(category=HookCategory.BUDGET_EXHAUSTED, message="slow")
        assert w.category == HookCategory.BUDGET_EXHAUSTED
        assert w.message == "slow"


# ---------------------------------------------------------------------------
# RuntimeObservation
# ---------------------------------------------------------------------------

class TestRuntimeObservation:
    def test_is_frozen(self) -> None:
        obs = RuntimeObservation(
            category=HookCategory.TASK_STARTED,
            hook_name="log_decision",
            observed=True,
            stdout_excerpt="INFO log",
            stderr_excerpt="",
            signal_patterns=["INFO"],
            collector_name="output_pattern",
        )
        with pytest.raises((AttributeError, TypeError)):
            obs.observed = False  # type: ignore[misc]

    def test_all_fields(self) -> None:
        obs = RuntimeObservation(
            category=HookCategory.TASK_FAILED,
            hook_name="policy_check",
            observed=False,
            stdout_excerpt="",
            stderr_excerpt="",
            signal_patterns=["policy", "governance"],
            collector_name="output_pattern",
        )
        assert obs.category == HookCategory.TASK_FAILED
        assert obs.observed is False
        assert "policy" in obs.signal_patterns


# ---------------------------------------------------------------------------
# ValidationEvidence
# ---------------------------------------------------------------------------

class TestValidationEvidence:
    def test_is_frozen(self) -> None:
        e = make_evidence()
        with pytest.raises((AttributeError, TypeError)):
            e.executed = False  # type: ignore[misc]

    def test_had_runtime_error_true(self) -> None:
        e = make_evidence(executed=True, exit_code=1)
        assert e.had_runtime_error is True

    def test_had_runtime_error_false_when_not_executed(self) -> None:
        e = make_evidence(executed=False, exit_code=None)
        assert e.had_runtime_error is False

    def test_had_runtime_error_false_on_zero_exit(self) -> None:
        e = make_evidence(executed=True, exit_code=0)
        assert e.had_runtime_error is False

    def test_combined_output(self) -> None:
        e = ValidationEvidence(
            execution_mode=SandboxExecutionMode.FULL_EXECUTION,
            environment_name="local_python",
            executed=True,
            stdout="hello",
            stderr="world",
            exit_code=0,
            duration_ms=10.0,
            timed_out=False,
            syntax_valid=True,
        )
        assert "hello" in e.combined_output
        assert "world" in e.combined_output

    def test_observations_default_empty(self) -> None:
        e = make_evidence()
        assert e.observations == []


# ---------------------------------------------------------------------------
# SandboxValidationResult
# ---------------------------------------------------------------------------

class TestSandboxValidationResult:
    def test_is_valid_true(self) -> None:
        result = make_svr(report=make_report(status=ValidationStatus.PASSED))
        assert result.is_valid is True

    def test_is_valid_false_on_failed(self) -> None:
        result = make_svr(report=make_report(status=ValidationStatus.FAILED))
        assert result.is_valid is False

    def test_is_valid_false_on_skipped(self) -> None:
        result = make_svr(report=make_report(status=ValidationStatus.SKIPPED))
        assert result.is_valid is False

    def test_passed_count(self) -> None:
        hook = make_hook()
        r1 = HookValidationResult(hook=hook, status=ValidationStatus.PASSED)
        r2 = HookValidationResult(hook=hook, status=ValidationStatus.FAILED)
        report = make_report(hook_results=[r1, r2])
        result = make_svr(report=report)
        assert result.passed_count == 1
        assert result.failed_count == 1

    def test_skipped_count(self) -> None:
        hook = make_hook()
        r = HookValidationResult(hook=hook, status=ValidationStatus.SKIPPED)
        report = make_report(hook_results=[r])
        result = make_svr(report=report)
        assert result.skipped_count == 1

    def test_has_errors_true(self) -> None:
        err = ValidationError(
            category=HookCategory.TASK_FAILED, error_type="SyntaxError", message="x"
        )
        result = make_svr(errors=[err])
        assert result.has_errors is True

    def test_has_errors_false(self) -> None:
        result = make_svr(errors=[])
        assert result.has_errors is False

    def test_has_warnings_true(self) -> None:
        w = ValidationWarning(category=HookCategory.TASK_STARTED, message="w")
        result = make_svr(warnings=[w])
        assert result.has_warnings is True

    def test_has_warnings_false(self) -> None:
        result = make_svr(warnings=[])
        assert result.has_warnings is False

    def test_generated_at_is_datetime(self) -> None:
        result = make_svr()
        assert isinstance(result.generated_at, datetime)
