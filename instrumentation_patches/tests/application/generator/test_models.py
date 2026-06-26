"""Tests for PatchGenerator data models."""

from datetime import datetime

import pytest

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
from awcp_instrumentation.application.gap_reporter.models import GovernanceGapReport
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_gap(category: HookCategory = HookCategory.TASK_STARTED) -> GovernanceGap:
    hook = GovernanceHook(category=category, name=f"{category.value}_hook", description="test")
    risk = GovernanceRisk(severity=RiskSeverity.HIGH, description="risk", impact="impact")
    rec = GovernanceRecommendation(
        action="add hook", rationale="required",
        instrumentation_hint="insert call", priority=1
    )
    return GovernanceGap(hook=hook, risk=risk, recommendation=rec)


def make_metadata() -> PatchMetadata:
    return PatchMetadata(
        model="test-model", provider_name="TestProvider",
        prompt_tokens=50, completion_tokens=30, temperature=0.2
    )


def make_change(location: InsertionLocation = InsertionLocation.AFTER_IMPORTS) -> PatchChange:
    return PatchChange(
        code_fragment="import logging",
        location=location,
        target_function=None,
        explanation="add logging import"
    )


def make_proposal(
    status: ProposalStatus = ProposalStatus.SUCCESS,
    category: HookCategory = HookCategory.TASK_STARTED,
) -> PatchProposal:
    return PatchProposal(
        gap=make_gap(category),
        status=status,
        changes=[make_change()],
        import_additions=["import logging"],
        explanation="added logging",
        confidence=0.9,
        metadata=make_metadata(),
        raw_llm_response='{"mock": true}',
    )


def make_report(gaps_count: int = 2) -> GovernanceGapReport:
    agent = AgentSource.from_string("x = 1", name="test_agent")
    gaps = [make_gap(cat) for cat in list(HookCategory)[:gaps_count]]
    return GovernanceGapReport(
        agent=agent,
        present_hooks=[],
        gaps=gaps,
        overall_risk_level=RiskSeverity.HIGH,
        summary="test",
    )


# ---------------------------------------------------------------------------
# InsertionLocation
# ---------------------------------------------------------------------------

class TestInsertionLocation:
    def test_all_five_values_exist(self) -> None:
        values = {loc.value for loc in InsertionLocation}
        assert values == {
            "top_of_file",
            "after_imports",
            "before_function_body",
            "around_function",
            "inline",
        }

    def test_string_comparison(self) -> None:
        assert InsertionLocation.AFTER_IMPORTS == "after_imports"

    def test_from_string(self) -> None:
        assert InsertionLocation("inline") is InsertionLocation.INLINE


# ---------------------------------------------------------------------------
# ProposalStatus
# ---------------------------------------------------------------------------

class TestProposalStatus:
    def test_three_values_exist(self) -> None:
        values = {s.value for s in ProposalStatus}
        assert values == {"success", "failed", "skipped"}


# ---------------------------------------------------------------------------
# PatchChange
# ---------------------------------------------------------------------------

class TestPatchChange:
    def test_is_frozen(self) -> None:
        change = make_change()
        with pytest.raises(Exception):
            change.code_fragment = "other"  # type: ignore[misc]

    def test_target_function_can_be_none(self) -> None:
        change = PatchChange(
            code_fragment="pass",
            location=InsertionLocation.TOP_OF_FILE,
            target_function=None,
            explanation="top-level"
        )
        assert change.target_function is None

    def test_target_function_with_name(self) -> None:
        change = PatchChange(
            code_fragment="log_decision()",
            location=InsertionLocation.BEFORE_FUNCTION_BODY,
            target_function="run",
            explanation="entry point"
        )
        assert change.target_function == "run"


# ---------------------------------------------------------------------------
# PatchMetadata
# ---------------------------------------------------------------------------

class TestPatchMetadata:
    def test_is_frozen(self) -> None:
        meta = make_metadata()
        with pytest.raises(Exception):
            meta.model = "other"  # type: ignore[misc]

    def test_total_tokens(self) -> None:
        meta = PatchMetadata(
            model="m", provider_name="p",
            prompt_tokens=100, completion_tokens=50, temperature=0.2
        )
        assert meta.total_tokens == 150

    def test_generated_at_defaults_to_now(self) -> None:
        before = datetime.utcnow()
        meta = make_metadata()
        after = datetime.utcnow()
        assert before <= meta.generated_at <= after


# ---------------------------------------------------------------------------
# PatchProposal
# ---------------------------------------------------------------------------

class TestPatchProposal:
    def test_total_tokens_delegates_to_metadata(self) -> None:
        proposal = make_proposal()
        assert proposal.total_tokens == proposal.metadata.total_tokens

    def test_has_changes_true_with_code_changes(self) -> None:
        proposal = make_proposal()
        assert proposal.has_changes is True

    def test_has_changes_true_with_only_imports(self) -> None:
        proposal = PatchProposal(
            gap=make_gap(), status=ProposalStatus.SUCCESS,
            changes=[], import_additions=["import logging"],
            explanation="", confidence=0.5,
            metadata=make_metadata(), raw_llm_response=""
        )
        assert proposal.has_changes is True

    def test_has_changes_false_when_empty(self) -> None:
        proposal = PatchProposal(
            gap=make_gap(), status=ProposalStatus.FAILED,
            changes=[], import_additions=[],
            explanation="", confidence=0.0,
            metadata=make_metadata(), raw_llm_response="",
            error="LLM timed out"
        )
        assert proposal.has_changes is False

    def test_error_defaults_to_none(self) -> None:
        proposal = make_proposal()
        assert proposal.error is None

    def test_category_property(self) -> None:
        proposal = make_proposal(category=HookCategory.TASK_FAILED)
        assert proposal.category == HookCategory.TASK_FAILED

    def test_failed_proposal_has_error(self) -> None:
        proposal = make_proposal(status=ProposalStatus.FAILED)
        proposal.error = "provider error"
        assert proposal.error == "provider error"


# ---------------------------------------------------------------------------
# PatchGenerationResult
# ---------------------------------------------------------------------------

class TestPatchGenerationResult:
    def _make_result(self) -> PatchGenerationResult:
        report = make_report(gaps_count=3)
        proposals = [
            make_proposal(ProposalStatus.SUCCESS, HookCategory.TASK_STARTED),
            make_proposal(ProposalStatus.FAILED, HookCategory.TASK_FAILED),
            make_proposal(ProposalStatus.SKIPPED, HookCategory.LLM_CALL),
        ]
        return PatchGenerationResult(report=report, proposals=proposals)

    def test_successful_proposals(self) -> None:
        result = self._make_result()
        assert len(result.successful_proposals) == 1

    def test_failed_proposals(self) -> None:
        result = self._make_result()
        assert len(result.failed_proposals) == 1

    def test_skipped_proposals(self) -> None:
        result = self._make_result()
        assert len(result.skipped_proposals) == 1

    def test_has_failures_true(self) -> None:
        result = self._make_result()
        assert result.has_failures is True

    def test_is_complete_when_counts_match(self) -> None:
        result = self._make_result()
        # 3 gaps in report, 3 proposals
        assert result.is_complete is True

    def test_is_not_complete_when_missing_proposals(self) -> None:
        report = make_report(gaps_count=3)
        proposals = [make_proposal()]  # only 1 of 3
        result = PatchGenerationResult(report=report, proposals=proposals)
        assert result.is_complete is False

    def test_total_tokens(self) -> None:
        result = self._make_result()
        expected = sum(p.total_tokens for p in result.proposals)
        assert result.total_tokens == expected

    def test_success_rate_all_success(self) -> None:
        report = make_report(gaps_count=2)
        proposals = [make_proposal(), make_proposal()]
        result = PatchGenerationResult(report=report, proposals=proposals)
        assert result.success_rate == 1.0

    def test_success_rate_half(self) -> None:
        report = make_report(gaps_count=2)
        proposals = [
            make_proposal(ProposalStatus.SUCCESS),
            make_proposal(ProposalStatus.FAILED),
        ]
        result = PatchGenerationResult(report=report, proposals=proposals)
        assert result.success_rate == 0.5

    def test_success_rate_empty(self) -> None:
        report = make_report(gaps_count=0)
        result = PatchGenerationResult(report=report, proposals=[])
        assert result.success_rate == 0.0

    def test_generated_at_defaults_to_now(self) -> None:
        before = datetime.utcnow()
        result = self._make_result()
        after = datetime.utcnow()
        assert before <= result.generated_at <= after

    def test_metadata_defaults_to_empty_dict(self) -> None:
        result = self._make_result()
        assert isinstance(result.metadata, dict)
