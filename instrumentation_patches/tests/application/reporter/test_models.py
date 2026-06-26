"""Tests for reporter models."""
from __future__ import annotations

from datetime import datetime

import pytest

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_exec_summary(**kwargs) -> ExecutionSummary:
    defaults = dict(
        mode="full_execution",
        environment="local_python",
        executed=True,
        duration_ms=42.0,
        exit_code=0,
        timed_out=False,
        syntax_valid=True,
        stdout_excerpt="",
        stderr_excerpt="",
    )
    defaults.update(kwargs)
    return ExecutionSummary(**defaults)


def make_report(**kwargs) -> BuiltReport:
    defaults = dict(
        agent=AgentInfo(name="agent", path=None),
        generated_at=datetime.utcnow(),
        overall_status="passed",
        execution_summary=make_exec_summary(),
        summary="Validation PASSED",
        total_hooks=1,
        passed_hooks=1,
        failed_hooks=0,
        skipped_hooks=0,
    )
    defaults.update(kwargs)
    return BuiltReport(**defaults)


# ---------------------------------------------------------------------------
# AgentInfo
# ---------------------------------------------------------------------------

class TestAgentInfo:
    def test_is_frozen(self) -> None:
        a = AgentInfo(name="x", path=None)
        with pytest.raises((AttributeError, TypeError)):
            a.name = "y"  # type: ignore[misc]

    def test_path_optional(self) -> None:
        a = AgentInfo(name="x", path=None)
        assert a.path is None

    def test_fields_stored(self) -> None:
        a = AgentInfo(name="my_agent", path="/path/to/agent.py")
        assert a.name == "my_agent"
        assert a.path == "/path/to/agent.py"


# ---------------------------------------------------------------------------
# ExecutionSummary
# ---------------------------------------------------------------------------

class TestExecutionSummary:
    def test_is_frozen(self) -> None:
        es = make_exec_summary()
        with pytest.raises((AttributeError, TypeError)):
            es.executed = False  # type: ignore[misc]

    def test_all_fields_stored(self) -> None:
        es = make_exec_summary(
            mode="syntax_only", environment="local_python",
            executed=False, duration_ms=None, exit_code=None,
            timed_out=False, syntax_valid=True,
            stdout_excerpt="out", stderr_excerpt="err",
        )
        assert es.mode == "syntax_only"
        assert es.executed is False
        assert es.duration_ms is None


# ---------------------------------------------------------------------------
# HookResult
# ---------------------------------------------------------------------------

class TestHookResult:
    def test_is_frozen(self) -> None:
        r = HookResult(
            category="observability", hook_name="log", status="passed",
            message="ok", stdout="", stderr="",
        )
        with pytest.raises((AttributeError, TypeError)):
            r.status = "failed"  # type: ignore[misc]

    def test_fields(self) -> None:
        r = HookResult(
            category="policy", hook_name="policy_check",
            status="failed", message="not found",
            stdout="", stderr="traceback",
        )
        assert r.category == "policy"
        assert r.status == "failed"
        assert r.stderr == "traceback"


# ---------------------------------------------------------------------------
# ObservationSummary
# ---------------------------------------------------------------------------

class TestObservationSummary:
    def test_is_frozen(self) -> None:
        obs = ObservationSummary(
            category="observability", hook_name="log",
            observed=True, collector="output_pattern",
            stdout_excerpt="INFO", stderr_excerpt="",
        )
        with pytest.raises((AttributeError, TypeError)):
            obs.observed = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ReportError / ReportWarning
# ---------------------------------------------------------------------------

class TestReportError:
    def test_is_frozen(self) -> None:
        e = ReportError(category="policy", error_type="SyntaxError", message="x")
        with pytest.raises((AttributeError, TypeError)):
            e.message = "y"  # type: ignore[misc]

    def test_traceback_default_none(self) -> None:
        e = ReportError(category="policy", error_type="RuntimeError", message="boom")
        assert e.traceback is None


class TestReportWarning:
    def test_is_frozen(self) -> None:
        w = ReportWarning(category="recovery", message="warn")
        with pytest.raises((AttributeError, TypeError)):
            w.message = "x"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# HookRecommendation
# ---------------------------------------------------------------------------

class TestHookRecommendation:
    def test_is_frozen(self) -> None:
        r = HookRecommendation(
            category="policy", hook_name="policy_check",
            action="add", rationale="gov", hint="use guard",
            priority=1, severity="critical",
        )
        with pytest.raises((AttributeError, TypeError)):
            r.severity = "low"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# BuiltReport
# ---------------------------------------------------------------------------

class TestBuiltReport:
    def test_is_passing_true(self) -> None:
        assert make_report(overall_status="passed").is_passing is True

    def test_is_passing_false(self) -> None:
        assert make_report(overall_status="failed").is_passing is False

    def test_has_errors_true(self) -> None:
        r = make_report(errors=[ReportError(category="x", error_type="e", message="m")])
        assert r.has_errors is True

    def test_has_errors_false(self) -> None:
        assert make_report().has_errors is False

    def test_has_warnings_true(self) -> None:
        r = make_report(warnings=[ReportWarning(category="x", message="w")])
        assert r.has_warnings is True

    def test_has_recommendations_true(self) -> None:
        rec = HookRecommendation(
            category="policy", hook_name="p", action="a",
            rationale="r", hint="h", priority=1, severity="high",
        )
        r = make_report(recommendations=[rec])
        assert r.has_recommendations is True

    def test_has_observations_true(self) -> None:
        obs = ObservationSummary(
            category="observability", hook_name="obs",
            observed=True, collector="output_pattern",
            stdout_excerpt="INFO", stderr_excerpt="",
        )
        r = make_report(observations=[obs])
        assert r.has_observations is True

    def test_default_lists_empty(self) -> None:
        r = make_report()
        assert r.hook_results == []
        assert r.missing_hooks == []
        assert r.observations == []
        assert r.errors == []
        assert r.warnings == []
        assert r.recommendations == []

    def test_counts_stored(self) -> None:
        r = make_report(total_hooks=5, passed_hooks=3, failed_hooks=2, skipped_hooks=0)
        assert r.total_hooks == 5
        assert r.passed_hooks == 3
        assert r.failed_hooks == 2
