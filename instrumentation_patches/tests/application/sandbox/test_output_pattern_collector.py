"""Tests for OutputPatternCollector."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from awcp_instrumentation.application.sandbox.models import ExecutionRecord, RuntimeObservation
from awcp_instrumentation.application.sandbox.output_pattern_collector import (
    OutputPatternCollector,
    _DEFAULT_SIGNALS,
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
    PatchMetadata,
    PatchProposal,
    ProposalStatus,
)
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory

COLLECTOR = OutputPatternCollector()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_record(stdout: str = "", stderr: str = "") -> ExecutionRecord:
    return ExecutionRecord(
        stdout=stdout, stderr=stderr,
        exit_code=0, duration_ms=5.0, timed_out=False,
    )


def make_proposal(category: HookCategory = HookCategory.TASK_STARTED) -> PatchProposal:
    hook = GovernanceHook(
        category=category, name=f"{category.value}_hook",
        description="test", signature=None, line_number=None,
    )
    risk = GovernanceRisk(severity=RiskSeverity.HIGH, description="x", impact="y")
    rec = GovernanceRecommendation(
        action="add", rationale="gov", instrumentation_hint="hint", priority=1
    )
    gap = GovernanceGap(hook=hook, risk=risk, recommendation=rec)
    meta = PatchMetadata(
        model="m", provider_name="p",
        prompt_tokens=1, completion_tokens=1,
        temperature=0.2, generated_at=datetime.utcnow(),
    )
    change = PatchChange(
        code_fragment="hook()",
        location=InsertionLocation.BEFORE_FUNCTION_BODY,
        target_function="run",
        explanation="test",
    )
    return PatchProposal(
        gap=gap, status=ProposalStatus.SUCCESS,
        changes=[change], import_additions=[],
        explanation="test", confidence=0.9,
        metadata=meta, raw_llm_response="{}",
    )


# ---------------------------------------------------------------------------
# collector_name
# ---------------------------------------------------------------------------

class TestCollectorName:
    def test_name_is_output_pattern(self) -> None:
        assert COLLECTOR.collector_name == "output_pattern"


# ---------------------------------------------------------------------------
# collect — signal found in stdout
# ---------------------------------------------------------------------------

class TestCollectStdout:
    def test_task_started_signal_in_stdout(self) -> None:
        record = make_record(stdout="task_started called")
        result = COLLECTOR.collect(record, [make_proposal(HookCategory.TASK_STARTED)])
        assert len(result) == 1
        assert result[0].observed is True

    def test_task_failed_signal_in_stdout(self) -> None:
        record = make_record(stdout="task_failed: error occurred")
        result = COLLECTOR.collect(record, [make_proposal(HookCategory.TASK_FAILED)])
        assert result[0].observed is True

    def test_llm_call_signal_in_stdout(self) -> None:
        record = make_record(stdout="llm_call sent to model")
        result = COLLECTOR.collect(record, [make_proposal(HookCategory.LLM_CALL)])
        assert result[0].observed is True

    def test_tool_call_signal_in_stdout(self) -> None:
        record = make_record(stdout="tool_call: search")
        result = COLLECTOR.collect(record, [make_proposal(HookCategory.TOOL_CALL)])
        assert result[0].observed is True

    def test_token_usage_signal_in_stdout(self) -> None:
        record = make_record(stdout="token_usage: 150 tokens")
        result = COLLECTOR.collect(record, [make_proposal(HookCategory.TOKEN_USAGE)])
        assert result[0].observed is True

    def test_budget_warn_signal_in_stdout(self) -> None:
        record = make_record(stdout="budget_warn: 80% used")
        result = COLLECTOR.collect(record, [make_proposal(HookCategory.BUDGET_WARN)])
        assert result[0].observed is True

    def test_budget_exhausted_signal_in_stdout(self) -> None:
        record = make_record(stdout="budget_exhausted: stopping")
        result = COLLECTOR.collect(record, [make_proposal(HookCategory.BUDGET_EXHAUSTED)])
        assert result[0].observed is True


# ---------------------------------------------------------------------------
# collect — signal found in stderr
# ---------------------------------------------------------------------------

class TestCollectStderr:
    def test_task_started_signal_in_stderr(self) -> None:
        record = make_record(stderr="awcp_hooks.task_started called")
        result = COLLECTOR.collect(record, [make_proposal(HookCategory.TASK_STARTED)])
        assert result[0].observed is True
        assert result[0].stderr_excerpt != ""

    def test_no_signal_returns_observed_false(self) -> None:
        record = make_record(stdout="no relevant output", stderr="no relevant error")
        result = COLLECTOR.collect(record, [make_proposal(HookCategory.TASK_FAILED)])
        assert result[0].observed is False


# ---------------------------------------------------------------------------
# collect — multiple proposals
# ---------------------------------------------------------------------------

class TestCollectMultipleProposals:
    def test_returns_one_observation_per_proposal(self) -> None:
        proposals = [
            make_proposal(HookCategory.TASK_STARTED),
            make_proposal(HookCategory.TASK_FAILED),
        ]
        record = make_record(stdout="task_started ok\ntask_failed error")
        result = COLLECTOR.collect(record, proposals)
        assert len(result) == 2

    def test_empty_proposals_returns_empty(self) -> None:
        result = COLLECTOR.collect(make_record(), [])
        assert result == []


# ---------------------------------------------------------------------------
# collect — observation fields
# ---------------------------------------------------------------------------

class TestObservationFields:
    def test_category_matches_proposal(self) -> None:
        record = make_record(stdout="task_started event")
        result = COLLECTOR.collect(record, [make_proposal(HookCategory.TASK_STARTED)])
        assert result[0].category == HookCategory.TASK_STARTED

    def test_hook_name_matches_proposal(self) -> None:
        record = make_record()
        result = COLLECTOR.collect(record, [make_proposal(HookCategory.TASK_STARTED)])
        assert result[0].hook_name == "task_started_hook"

    def test_signal_patterns_listed(self) -> None:
        result = COLLECTOR.collect(make_record(), [make_proposal(HookCategory.LLM_CALL)])
        assert len(result[0].signal_patterns) > 0

    def test_collector_name_in_observation(self) -> None:
        result = COLLECTOR.collect(make_record(), [make_proposal(HookCategory.TASK_STARTED)])
        assert result[0].collector_name == "output_pattern"

    def test_excerpt_captures_matching_line(self) -> None:
        record = make_record(stdout="awcp_hooks.task_started(t, a) called here")
        result = COLLECTOR.collect(record, [make_proposal(HookCategory.TASK_STARTED)])
        assert "task_started" in result[0].stdout_excerpt


# ---------------------------------------------------------------------------
# Custom signal catalog
# ---------------------------------------------------------------------------

class TestCustomCatalog:
    def test_custom_catalog_used(self) -> None:
        catalog = {HookCategory.TASK_STARTED: ["CUSTOM_SIGNAL"]}
        collector = OutputPatternCollector(signal_catalog=catalog)
        record = make_record(stdout="CUSTOM_SIGNAL detected")
        result = collector.collect(record, [make_proposal(HookCategory.TASK_STARTED)])
        assert result[0].observed is True

    def test_custom_catalog_no_match(self) -> None:
        catalog = {HookCategory.TASK_STARTED: ["CUSTOM_SIGNAL"]}
        collector = OutputPatternCollector(signal_catalog=catalog)
        record = make_record(stdout="task_started: beginning")
        result = collector.collect(record, [make_proposal(HookCategory.TASK_STARTED)])
        assert result[0].observed is False

    def test_empty_catalog_entry_returns_false(self) -> None:
        catalog = {HookCategory.TASK_FAILED: []}
        collector = OutputPatternCollector(signal_catalog=catalog)
        record = make_record(stdout="task_failed: error")
        result = collector.collect(record, [make_proposal(HookCategory.TASK_FAILED)])
        assert result[0].observed is False

    def test_missing_category_in_catalog_returns_false(self) -> None:
        collector = OutputPatternCollector(signal_catalog={})
        record = make_record(stdout="task_started event")
        result = collector.collect(record, [make_proposal(HookCategory.TASK_STARTED)])
        assert result[0].observed is False
