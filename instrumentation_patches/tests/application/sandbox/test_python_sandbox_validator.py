"""
Tests for PythonSandboxValidator.

All tests use mock SandboxEnvironment and EvidenceCollector so no subprocess
is spawned.  LocalPythonSandbox has its own test file.
"""
from __future__ import annotations

from datetime import datetime
from typing import List
from unittest.mock import MagicMock

import pytest

from awcp_instrumentation.application.applicator.models import (
    ApplyError,
    ApplyStatus,
    PatchedSource,
)
from awcp_instrumentation.application.gap_reporter.models import (
    GovernanceGap,
    GovernanceRecommendation,
    GovernanceRisk,
    RiskSeverity,
)
from awcp_instrumentation.application.generator.models import (
    InsertionLocation,
    PatchChange,
    PatchGenerationResult,
    PatchMetadata,
    PatchProposal,
    ProposalStatus,
)
from awcp_instrumentation.application.sandbox.evidence_collector import EvidenceCollector
from awcp_instrumentation.application.sandbox.models import (
    ExecutionRecord,
    RuntimeObservation,
    SandboxExecutionMode,
    SandboxValidationResult,
    ValidationError,
)
from awcp_instrumentation.application.sandbox.python_sandbox_validator import (
    PythonSandboxValidator,
)
from awcp_instrumentation.application.sandbox.sandbox_environment import SandboxEnvironment
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory
from awcp_instrumentation.domain.enums.validation_status import ValidationStatus


# ---------------------------------------------------------------------------
# Source fixtures
# ---------------------------------------------------------------------------

PATCHED_SOURCE = """\
import os
import logging

logger = logging.getLogger(__name__)

def run():
    logger.info("decision made")
    policy_check()
    x = 1
    return x
"""

SYNTAX_ERROR_SOURCE = "def broken(:\n    pass\n"


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def make_agent(source: str = PATCHED_SOURCE) -> AgentSource:
    return AgentSource.from_string(source, "test_agent")


def make_hook(category: HookCategory = HookCategory.TASK_STARTED) -> GovernanceHook:
    return GovernanceHook(
        category=category, name=f"{category.value}_hook",
        description="test", signature=None, line_number=None,
    )


def make_gap(category: HookCategory = HookCategory.TASK_STARTED) -> GovernanceGap:
    return GovernanceGap(
        hook=make_hook(category),
        risk=GovernanceRisk(severity=RiskSeverity.HIGH, description="x", impact="y"),
        recommendation=GovernanceRecommendation(
            action="add", rationale="gov", instrumentation_hint="hint", priority=1
        ),
    )


def make_metadata() -> PatchMetadata:
    return PatchMetadata(
        model="m", provider_name="p",
        prompt_tokens=1, completion_tokens=1,
        temperature=0.2, generated_at=datetime.utcnow(),
    )


def make_change(
    fragment: str,
    location: InsertionLocation = InsertionLocation.BEFORE_FUNCTION_BODY,
    target_function: str | None = "run",
) -> PatchChange:
    return PatchChange(
        code_fragment=fragment,
        location=location,
        target_function=target_function,
        explanation="test",
    )


def make_proposal(
    category: HookCategory = HookCategory.TASK_STARTED,
    fragments: list[str] | None = None,
) -> PatchProposal:
    if fragments is None:
        fragments = ['logger.info("decision made")']
    return PatchProposal(
        gap=make_gap(category),
        status=ProposalStatus.SUCCESS,
        changes=[make_change(f) for f in fragments],
        import_additions=["import logging"],
        explanation="test",
        confidence=0.9,
        metadata=make_metadata(),
        raw_llm_response="{}",
    )


def make_patched(
    source: str = PATCHED_SOURCE,
    proposals: list[PatchProposal] | None = None,
) -> PatchedSource:
    agent = make_agent(source)
    gen = MagicMock(spec=PatchGenerationResult)
    return PatchedSource(
        original_agent=agent,
        patched_source=source,
        applied_proposals=proposals if proposals is not None else [make_proposal()],
        warnings=[],
        errors=[],
    )


def make_record(
    exit_code: int = 0,
    stdout: str = "",
    stderr: str = "",
    timed_out: bool = False,
) -> ExecutionRecord:
    return ExecutionRecord(
        stdout=stdout, stderr=stderr,
        exit_code=exit_code, duration_ms=10.0, timed_out=timed_out,
    )


class MockSandbox(SandboxEnvironment):
    """Test double for SandboxEnvironment."""

    def __init__(self, record: ExecutionRecord | None = None) -> None:
        self._record = record or make_record()
        self.call_count = 0
        self.last_source: str | None = None

    @property
    def environment_name(self) -> str:
        return "mock_sandbox"

    def execute(self, source: str, agent_name: str, timeout_seconds: float) -> ExecutionRecord:
        self.call_count += 1
        self.last_source = source
        return self._record


class MockCollector(EvidenceCollector):
    """Test double for EvidenceCollector."""

    def __init__(self, observations: list[RuntimeObservation] | None = None) -> None:
        self._observations = observations or []
        self.call_count = 0

    @property
    def collector_name(self) -> str:
        return "mock_collector"

    def collect(self, record: ExecutionRecord, applied_proposals) -> list[RuntimeObservation]:
        self.call_count += 1
        return self._observations


def make_validator(
    mode: SandboxExecutionMode = SandboxExecutionMode.FULL_EXECUTION,
    sandbox: SandboxEnvironment | None = None,
    collectors: list[EvidenceCollector] | None = None,
    timeout: float = 5.0,
) -> PythonSandboxValidator:
    return PythonSandboxValidator(
        execution_mode=mode,
        timeout_seconds=timeout,
        sandbox=sandbox or MockSandbox(),
        collectors=collectors if collectors is not None else [],
    )


# ---------------------------------------------------------------------------
# Return type and basic structure
# ---------------------------------------------------------------------------

class TestReturnType:
    def test_returns_sandbox_validation_result(self) -> None:
        v = make_validator()
        result = v.validate(make_patched())
        assert isinstance(result, SandboxValidationResult)

    def test_patched_source_ref_preserved(self) -> None:
        v = make_validator()
        patched = make_patched()
        result = v.validate(patched)
        assert result.patched_source_ref is patched

    def test_report_populated(self) -> None:
        v = make_validator()
        result = v.validate(make_patched())
        assert result.report is not None

    def test_evidence_populated(self) -> None:
        v = make_validator()
        result = v.validate(make_patched())
        assert result.evidence is not None

    def test_generated_at_is_datetime(self) -> None:
        v = make_validator()
        result = v.validate(make_patched())
        assert isinstance(result.generated_at, datetime)


# ---------------------------------------------------------------------------
# SYNTAX_ONLY mode
# ---------------------------------------------------------------------------

class TestSyntaxOnlyMode:
    def test_no_execution_in_syntax_only(self) -> None:
        sandbox = MockSandbox()
        v = make_validator(mode=SandboxExecutionMode.SYNTAX_ONLY, sandbox=sandbox)
        v.validate(make_patched())
        assert sandbox.call_count == 0

    def test_evidence_executed_false(self) -> None:
        v = make_validator(mode=SandboxExecutionMode.SYNTAX_ONLY)
        result = v.validate(make_patched())
        assert result.evidence.executed is False

    def test_passed_when_syntax_ok_and_fragment_present(self) -> None:
        v = make_validator(mode=SandboxExecutionMode.SYNTAX_ONLY)
        result = v.validate(make_patched())
        assert result.report.overall_status == ValidationStatus.PASSED

    def test_failed_on_syntax_error(self) -> None:
        v = make_validator(mode=SandboxExecutionMode.SYNTAX_ONLY)
        patched = make_patched(source=SYNTAX_ERROR_SOURCE)
        result = v.validate(patched)
        assert result.report.overall_status == ValidationStatus.FAILED

    def test_syntax_error_recorded_in_errors(self) -> None:
        v = make_validator(mode=SandboxExecutionMode.SYNTAX_ONLY)
        result = v.validate(make_patched(source=SYNTAX_ERROR_SOURCE))
        assert any(e.error_type == "SyntaxError" for e in result.errors)

    def test_evidence_syntax_valid_true(self) -> None:
        v = make_validator(mode=SandboxExecutionMode.SYNTAX_ONLY)
        result = v.validate(make_patched())
        assert result.evidence.syntax_valid is True

    def test_evidence_syntax_valid_false_on_error(self) -> None:
        v = make_validator(mode=SandboxExecutionMode.SYNTAX_ONLY)
        result = v.validate(make_patched(source=SYNTAX_ERROR_SOURCE))
        assert result.evidence.syntax_valid is False


# ---------------------------------------------------------------------------
# FULL_EXECUTION mode — successful execution
# ---------------------------------------------------------------------------

class TestFullExecutionSuccess:
    def test_sandbox_called_once(self) -> None:
        sandbox = MockSandbox(make_record(exit_code=0))
        v = make_validator(sandbox=sandbox)
        v.validate(make_patched())
        assert sandbox.call_count == 1

    def test_passed_on_zero_exit_and_fragment_present(self) -> None:
        v = make_validator(sandbox=MockSandbox(make_record(exit_code=0)))
        result = v.validate(make_patched())
        assert result.report.overall_status == ValidationStatus.PASSED

    def test_evidence_executed_true(self) -> None:
        v = make_validator(sandbox=MockSandbox(make_record(exit_code=0)))
        result = v.validate(make_patched())
        assert result.evidence.executed is True

    def test_evidence_environment_name(self) -> None:
        v = make_validator(sandbox=MockSandbox())
        result = v.validate(make_patched())
        assert result.evidence.environment_name == "mock_sandbox"

    def test_stdout_captured_in_evidence(self) -> None:
        v = make_validator(sandbox=MockSandbox(make_record(stdout="hook output")))
        result = v.validate(make_patched())
        assert result.evidence.stdout == "hook output"

    def test_stderr_captured_in_evidence(self) -> None:
        v = make_validator(sandbox=MockSandbox(make_record(stderr="INFO: log")))
        result = v.validate(make_patched())
        assert result.evidence.stderr == "INFO: log"

    def test_no_errors_on_clean_run(self) -> None:
        v = make_validator(sandbox=MockSandbox(make_record(exit_code=0)))
        result = v.validate(make_patched())
        assert result.errors == []


# ---------------------------------------------------------------------------
# FULL_EXECUTION mode — runtime failure
# ---------------------------------------------------------------------------

class TestFullExecutionFailure:
    def test_failed_on_nonzero_exit(self) -> None:
        v = make_validator(sandbox=MockSandbox(make_record(exit_code=1, stderr="Error")))
        result = v.validate(make_patched())
        assert result.report.overall_status == ValidationStatus.FAILED

    def test_runtime_error_recorded(self) -> None:
        v = make_validator(sandbox=MockSandbox(make_record(exit_code=1)))
        result = v.validate(make_patched())
        assert any(e.error_type == "RuntimeError" for e in result.errors)

    def test_timeout_sets_error_type(self) -> None:
        v = make_validator(sandbox=MockSandbox(make_record(exit_code=-1, timed_out=True)))
        result = v.validate(make_patched())
        assert any(e.error_type == "TimeoutError" for e in result.errors)

    def test_failed_status_on_timeout(self) -> None:
        v = make_validator(sandbox=MockSandbox(make_record(exit_code=-1, timed_out=True)))
        result = v.validate(make_patched())
        assert result.report.overall_status == ValidationStatus.FAILED

    def test_timed_out_in_evidence(self) -> None:
        v = make_validator(sandbox=MockSandbox(make_record(exit_code=-1, timed_out=True)))
        result = v.validate(make_patched())
        assert result.evidence.timed_out is True


# ---------------------------------------------------------------------------
# Static presence check
# ---------------------------------------------------------------------------

class TestPresenceCheck:
    def test_failed_when_fragment_missing(self) -> None:
        # Proposal expects "missing_hook()" but source doesn't have it
        proposal = make_proposal(fragments=["missing_hook()"])
        v = make_validator(sandbox=MockSandbox(make_record(exit_code=0)))
        result = v.validate(make_patched(proposals=[proposal]))
        assert result.report.overall_status == ValidationStatus.FAILED

    def test_missing_fragment_error_recorded(self) -> None:
        proposal = make_proposal(fragments=["missing_hook()"])
        v = make_validator(sandbox=MockSandbox(make_record(exit_code=0)))
        result = v.validate(make_patched(proposals=[proposal]))
        assert any(e.error_type == "MissingFragment" for e in result.errors)

    def test_passed_when_fragment_present(self) -> None:
        proposal = make_proposal(fragments=['logger.info("decision made")'])
        v = make_validator(sandbox=MockSandbox(make_record(exit_code=0)))
        result = v.validate(make_patched(proposals=[proposal]))
        assert result.report.overall_status == ValidationStatus.PASSED

    def test_partial_failure_when_one_missing(self) -> None:
        p1 = make_proposal(
            category=HookCategory.TASK_STARTED,
            fragments=['logger.info("decision made")'],
        )
        p2 = make_proposal(
            category=HookCategory.TASK_FAILED,
            fragments=["missing_policy_hook()"],
        )
        v = make_validator(sandbox=MockSandbox(make_record(exit_code=0)))
        result = v.validate(make_patched(proposals=[p1, p2]))
        hook_statuses = {r.hook.category: r.status for r in result.report.hook_results}
        assert hook_statuses[HookCategory.TASK_STARTED] == ValidationStatus.PASSED
        assert hook_statuses[HookCategory.TASK_FAILED] == ValidationStatus.FAILED


# ---------------------------------------------------------------------------
# Evidence collection
# ---------------------------------------------------------------------------

class TestEvidenceCollection:
    def test_collector_called_on_execution(self) -> None:
        collector = MockCollector()
        v = make_validator(sandbox=MockSandbox(), collectors=[collector])
        v.validate(make_patched())
        assert collector.call_count == 1

    def test_collector_not_called_in_syntax_only(self) -> None:
        collector = MockCollector()
        v = make_validator(
            mode=SandboxExecutionMode.SYNTAX_ONLY,
            collectors=[collector],
        )
        v.validate(make_patched())
        assert collector.call_count == 0

    def test_observations_in_evidence(self) -> None:
        obs = RuntimeObservation(
            category=HookCategory.TASK_STARTED, hook_name="obs_hook",
            observed=True, stdout_excerpt="INFO", stderr_excerpt="",
            signal_patterns=["INFO"], collector_name="mock_collector",
        )
        collector = MockCollector([obs])
        v = make_validator(sandbox=MockSandbox(), collectors=[collector])
        result = v.validate(make_patched())
        assert len(result.evidence.observations) == 1

    def test_multiple_collectors_merged(self) -> None:
        obs1 = RuntimeObservation(
            category=HookCategory.TASK_STARTED, hook_name="obs",
            observed=True, stdout_excerpt="a", stderr_excerpt="",
            signal_patterns=["a"], collector_name="c1",
        )
        obs2 = RuntimeObservation(
            category=HookCategory.TASK_FAILED, hook_name="pol",
            observed=False, stdout_excerpt="", stderr_excerpt="",
            signal_patterns=["policy"], collector_name="c2",
        )
        c1 = MockCollector([obs1])
        c2 = MockCollector([obs2])
        v = make_validator(sandbox=MockSandbox(), collectors=[c1, c2])
        result = v.validate(make_patched())
        assert len(result.evidence.observations) == 2

    def test_collector_exception_adds_warning(self) -> None:
        class BrokenCollector(EvidenceCollector):
            @property
            def collector_name(self) -> str:
                return "broken"
            def collect(self, record, proposals):
                raise RuntimeError("collector failed")

        v = make_validator(sandbox=MockSandbox(), collectors=[BrokenCollector()])
        result = v.validate(make_patched())
        assert result.has_warnings is True


# ---------------------------------------------------------------------------
# No applied proposals
# ---------------------------------------------------------------------------

class TestNoProposals:
    def test_empty_proposals_skipped_status(self) -> None:
        v = make_validator(sandbox=MockSandbox(make_record(exit_code=0)))
        result = v.validate(make_patched(proposals=[]))
        assert result.report.overall_status == ValidationStatus.SKIPPED

    def test_no_hook_results_when_no_proposals(self) -> None:
        v = make_validator(sandbox=MockSandbox())
        result = v.validate(make_patched(proposals=[]))
        assert result.report.hook_results == []


# ---------------------------------------------------------------------------
# Syntax error aborts execution
# ---------------------------------------------------------------------------

class TestSyntaxErrorAbortsExecution:
    def test_sandbox_not_called_on_syntax_error(self) -> None:
        sandbox = MockSandbox()
        v = make_validator(sandbox=sandbox)
        v.validate(make_patched(source=SYNTAX_ERROR_SOURCE))
        assert sandbox.call_count == 0

    def test_all_hooks_failed_on_syntax_error(self) -> None:
        v = make_validator(sandbox=MockSandbox())
        proposals = [
            make_proposal(HookCategory.TASK_STARTED),
            make_proposal(HookCategory.TASK_FAILED),
        ]
        result = v.validate(make_patched(source=SYNTAX_ERROR_SOURCE, proposals=proposals))
        assert all(
            r.status == ValidationStatus.FAILED
            for r in result.report.hook_results
        )


# ---------------------------------------------------------------------------
# IMPORT_CHECK mode
# ---------------------------------------------------------------------------

class TestImportCheckMode:
    def test_no_subprocess_in_import_check(self) -> None:
        sandbox = MockSandbox()
        v = make_validator(mode=SandboxExecutionMode.IMPORT_CHECK, sandbox=sandbox)
        v.validate(make_patched())
        assert sandbox.call_count == 0

    def test_evidence_not_executed(self) -> None:
        v = make_validator(mode=SandboxExecutionMode.IMPORT_CHECK)
        result = v.validate(make_patched())
        assert result.evidence.executed is False

    def test_passed_on_valid_compilable_source(self) -> None:
        v = make_validator(mode=SandboxExecutionMode.IMPORT_CHECK)
        result = v.validate(make_patched())
        assert result.report.overall_status == ValidationStatus.PASSED


# ---------------------------------------------------------------------------
# Dependency injection
# ---------------------------------------------------------------------------

class TestDependencyInjection:
    def test_custom_sandbox_used(self) -> None:
        sandbox = MockSandbox(make_record(exit_code=0))
        v = PythonSandboxValidator(sandbox=sandbox)
        v.validate(make_patched())
        assert sandbox.call_count == 1

    def test_default_sandbox_is_local_python(self) -> None:
        from awcp_instrumentation.application.sandbox.local_python_sandbox import LocalPythonSandbox
        v = PythonSandboxValidator()
        assert isinstance(v._sandbox, LocalPythonSandbox)

    def test_default_collectors_non_empty(self) -> None:
        v = PythonSandboxValidator()
        assert len(v._collectors) >= 1

    def test_custom_collectors_injected(self) -> None:
        collector = MockCollector()
        v = PythonSandboxValidator(collectors=[collector])
        v.validate(make_patched())
        assert collector.call_count == 1

    def test_execution_mode_stored(self) -> None:
        v = PythonSandboxValidator(execution_mode=SandboxExecutionMode.SYNTAX_ONLY)
        assert v._mode == SandboxExecutionMode.SYNTAX_ONLY

    def test_timeout_stored(self) -> None:
        v = PythonSandboxValidator(timeout_seconds=30.0)
        assert v._timeout == 30.0
