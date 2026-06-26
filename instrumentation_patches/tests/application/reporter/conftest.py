"""
Shared fixtures for reporter tests.

Builds a realistic SandboxValidationResult covering the common scenarios:
  - fully_passing_result   : all hooks PASSED, execution succeeded
  - partial_failure_result : one hook PASSED, one FAILED (missing fragment)
  - syntax_error_result    : source has syntax error, no execution
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from awcp_instrumentation.application.applicator.models import PatchedSource
from awcp_instrumentation.application.gap_reporter.models import (
    GovernanceGap,
    GovernanceRecommendation,
    GovernanceRisk,
    RiskSeverity,
)
from awcp_instrumentation.application.generator.models import (
    InsertionLocation,
    PatchChange,
    PatchMetadata,
    PatchProposal,
    ProposalStatus,
)
from awcp_instrumentation.application.sandbox.models import (
    ExecutionRecord,
    RuntimeObservation,
    SandboxExecutionMode,
    SandboxValidationResult,
    ValidationError,
    ValidationEvidence,
    ValidationWarning,
)
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.entities.validation_report import (
    HookValidationResult,
    ValidationReport,
)
from awcp_instrumentation.domain.enums.hook_category import HookCategory
from awcp_instrumentation.domain.enums.validation_status import ValidationStatus


# ---------------------------------------------------------------------------
# Low-level builders
# ---------------------------------------------------------------------------

def _hook(category: HookCategory) -> GovernanceHook:
    return GovernanceHook(
        category=category,
        name=f"{category.value}_hook",
        description="test",
        signature=f"{category.value}_fn()",
        line_number=None,
    )


def _gap(category: HookCategory) -> GovernanceGap:
    return GovernanceGap(
        hook=_hook(category),
        risk=GovernanceRisk(
            severity=RiskSeverity.HIGH,
            description=f"{category.value} risk",
            impact="governance breach",
        ),
        recommendation=GovernanceRecommendation(
            action=f"Add {category.value} hook",
            rationale="Required by AWCP governance policy",
            instrumentation_hint=f"Use awcp_hooks.{category.value}() at entry point",
            priority=1,
        ),
    )


def _proposal(category: HookCategory, fragment: str = "hook()") -> PatchProposal:
    return PatchProposal(
        gap=_gap(category),
        status=ProposalStatus.SUCCESS,
        changes=[
            PatchChange(
                code_fragment=fragment,
                location=InsertionLocation.BEFORE_FUNCTION_BODY,
                target_function="run",
                explanation="test",
            )
        ],
        import_additions=["import awcp_hooks"],
        explanation="test",
        confidence=0.9,
        metadata=PatchMetadata(
            model="test", provider_name="mock",
            prompt_tokens=10, completion_tokens=10,
            temperature=0.2, generated_at=datetime.utcnow(),
        ),
        raw_llm_response="{}",
    )


def _patched_source(
    source: str = "import os\ndef run():\n    awcp_hooks.task_started(t, a)\n    pass\n",
    proposals: list[PatchProposal] | None = None,
) -> PatchedSource:
    agent = AgentSource.from_string(source, "test_agent")
    return PatchedSource(
        original_agent=agent,
        patched_source=source,
        applied_proposals=proposals or [],
        warnings=[],
        errors=[],
    )


def _evidence(
    executed: bool = True,
    syntax_valid: bool = True,
    exit_code: int = 0,
    timed_out: bool = False,
    stdout: str = "awcp_hooks.task_started called",
    stderr: str = "",
    observations: list[RuntimeObservation] | None = None,
) -> ValidationEvidence:
    return ValidationEvidence(
        execution_mode=SandboxExecutionMode.FULL_EXECUTION,
        environment_name="local_python",
        executed=executed,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code if executed else None,
        duration_ms=42.0 if executed else None,
        timed_out=timed_out,
        syntax_valid=syntax_valid,
        observations=observations or [],
    )


def _observation(
    category: HookCategory = HookCategory.TASK_STARTED,
    observed: bool = True,
) -> RuntimeObservation:
    return RuntimeObservation(
        category=category,
        hook_name=f"{category.value}_hook",
        observed=observed,
        stdout_excerpt="awcp_hooks.task_started called" if observed else "",
        stderr_excerpt="",
        signal_patterns=["task_started", "awcp_hooks"],
        collector_name="output_pattern",
    )


# ---------------------------------------------------------------------------
# Composite fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def task_started_proposal() -> PatchProposal:
    return _proposal(HookCategory.TASK_STARTED, "awcp_hooks.task_started(task_id, agent_name)")


@pytest.fixture
def task_failed_proposal() -> PatchProposal:
    return _proposal(HookCategory.TASK_FAILED, "awcp_hooks.task_failed(task_id, error)")


@pytest.fixture
def fully_passing_result(task_started_proposal: PatchProposal) -> SandboxValidationResult:
    """All hooks PASSED, execution succeeded."""
    hook_result = HookValidationResult(
        hook=task_started_proposal.gap.hook,
        status=ValidationStatus.PASSED,
        message="Task-started hook validated successfully.",
        stdout="awcp_hooks.task_started called",
        stderr="",
    )
    report = ValidationReport(
        agent_name="test_agent",
        overall_status=ValidationStatus.PASSED,
        hook_results=[hook_result],
        generated_at=datetime.utcnow(),
        duration_seconds=0.042,
    )
    obs = _observation(HookCategory.TASK_STARTED, observed=True)
    return SandboxValidationResult(
        patched_source_ref=_patched_source(proposals=[task_started_proposal]),
        report=report,
        evidence=_evidence(observations=[obs]),
        errors=[],
        warnings=[],
        generated_at=datetime.utcnow(),
    )


@pytest.fixture
def partial_failure_result(
    task_started_proposal: PatchProposal,
    task_failed_proposal: PatchProposal,
) -> SandboxValidationResult:
    """TASK_STARTED PASSED, TASK_FAILED FAILED (missing fragment)."""
    r1 = HookValidationResult(
        hook=task_started_proposal.gap.hook,
        status=ValidationStatus.PASSED,
        message="Task-started hook validated successfully.",
    )
    r2 = HookValidationResult(
        hook=task_failed_proposal.gap.hook,
        status=ValidationStatus.FAILED,
        message="Task-failed hook code fragment not found in patched source.",
    )
    report = ValidationReport(
        agent_name="test_agent",
        overall_status=ValidationStatus.FAILED,
        hook_results=[r1, r2],
        generated_at=datetime.utcnow(),
    )
    err = ValidationError(
        category=HookCategory.TASK_FAILED,
        error_type="MissingFragment",
        message="awcp_hooks.task_failed() not found",
    )
    warn = ValidationWarning(
        category=HookCategory.TASK_STARTED,
        message="Execution mode downgraded.",
    )
    obs = _observation(HookCategory.TASK_STARTED, observed=True)
    return SandboxValidationResult(
        patched_source_ref=_patched_source(proposals=[task_started_proposal, task_failed_proposal]),
        report=report,
        evidence=_evidence(observations=[obs]),
        errors=[err],
        warnings=[warn],
        generated_at=datetime.utcnow(),
    )


@pytest.fixture
def syntax_error_result(task_started_proposal: PatchProposal) -> SandboxValidationResult:
    """Syntax error in patched source; no execution."""
    hook_result = HookValidationResult(
        hook=task_started_proposal.gap.hook,
        status=ValidationStatus.FAILED,
        message="SyntaxError: invalid syntax",
    )
    report = ValidationReport(
        agent_name="test_agent",
        overall_status=ValidationStatus.FAILED,
        hook_results=[hook_result],
        generated_at=datetime.utcnow(),
    )
    err = ValidationError(
        category=HookCategory.TASK_STARTED,
        error_type="SyntaxError",
        message="invalid syntax (<string>, line 1)",
        line_number=1,
    )
    return SandboxValidationResult(
        patched_source_ref=_patched_source(proposals=[task_started_proposal]),
        report=report,
        evidence=_evidence(executed=False, syntax_valid=False, stdout="", stderr=""),
        errors=[err],
        warnings=[],
        generated_at=datetime.utcnow(),
    )
