"""Tests for SourcePatchApplier — the concrete Patch Apply Engine."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from awcp_instrumentation.application.applicator.location_resolver import (
    LocationResolutionError,
    LocationResolver,
    ResolvedLocation,
)
from awcp_instrumentation.application.applicator.models import ApplyStatus
from awcp_instrumentation.application.applicator.patch_applier import SourcePatchApplier
from awcp_instrumentation.application.generator.models import (
    InsertionLocation,
    PatchChange,
    PatchGenerationResult,
    PatchMetadata,
    PatchProposal,
    ProposalStatus,
)
from awcp_instrumentation.application.gap_reporter.models import (
    GovernanceGap,
    GovernanceGapReport,
    GovernanceRecommendation,
    GovernanceRisk,
    RiskSeverity,
)
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory


# ---------------------------------------------------------------------------
# Builders / fixtures
# ---------------------------------------------------------------------------

SIMPLE_SOURCE = """\
import os

def run():
    x = 1
    return x
"""


def make_agent(source: str = SIMPLE_SOURCE) -> AgentSource:
    return AgentSource.from_string(source, "test_agent")


def make_hook(category: HookCategory = HookCategory.TASK_STARTED) -> GovernanceHook:
    return GovernanceHook(
        category=category,
        name=f"{category.value}_hook",
        description="test hook",
        signature="hook()",
        line_number=None,
    )


def make_gap(category: HookCategory = HookCategory.TASK_STARTED) -> GovernanceGap:
    risk = GovernanceRisk(
        severity=RiskSeverity.HIGH,
        description="missing",
        impact="bad",
    )
    rec = GovernanceRecommendation(
        action="add hook",
        rationale="governance",
        instrumentation_hint="use logging",
        priority=1,
    )
    hook = make_hook(category)
    return GovernanceGap(hook=hook, risk=risk, recommendation=rec)


def make_metadata() -> PatchMetadata:
    return PatchMetadata(
        model="test-model",
        provider_name="MockProvider",
        prompt_tokens=10,
        completion_tokens=20,
        temperature=0.2,
        generated_at=datetime.utcnow(),
    )


def make_change(
    fragment: str = "logger.info('event')",
    location: InsertionLocation = InsertionLocation.BEFORE_FUNCTION_BODY,
    target_function: str | None = "run",
) -> PatchChange:
    return PatchChange(
        code_fragment=fragment,
        location=location,
        target_function=target_function,
        explanation="test change",
    )


def make_proposal(
    category: HookCategory = HookCategory.TASK_STARTED,
    changes: list[PatchChange] | None = None,
    import_additions: list[str] | None = None,
    status: ProposalStatus = ProposalStatus.SUCCESS,
) -> PatchProposal:
    if changes is None:
        changes = [make_change()]
    return PatchProposal(
        gap=make_gap(category),
        status=status,
        changes=changes,
        import_additions=import_additions or ["import logging"],
        explanation="test",
        confidence=0.9,
        metadata=make_metadata(),
        raw_llm_response="{}",
    )


def make_generation_result(
    proposals: list[PatchProposal] | None = None,
) -> PatchGenerationResult:
    report = MagicMock(spec=GovernanceGapReport)
    report.gaps = []
    return PatchGenerationResult(
        report=report,
        proposals=[make_proposal()] if proposals is None else proposals,
        generated_at=datetime.utcnow(),
    )


APPLIER = SourcePatchApplier()


# ---------------------------------------------------------------------------
# Basic apply — single proposal
# ---------------------------------------------------------------------------

class TestApplySingleProposal:
    def test_returns_apply_result(self) -> None:
        result = APPLIER.apply(make_agent(), make_generation_result())
        assert result is not None

    def test_status_success_on_clean_apply(self) -> None:
        result = APPLIER.apply(make_agent(), make_generation_result())
        assert result.status == ApplyStatus.SUCCESS

    def test_patched_source_populated(self) -> None:
        result = APPLIER.apply(make_agent(), make_generation_result())
        assert result.patched_source is not None

    def test_fragment_in_patched_source(self) -> None:
        result = APPLIER.apply(make_agent(), make_generation_result())
        assert "logger.info('event')" in result.patched_source.patched_source

    def test_import_injected(self) -> None:
        result = APPLIER.apply(make_agent(), make_generation_result())
        assert "import logging" in result.patched_source.patched_source

    def test_original_source_preserved(self) -> None:
        result = APPLIER.apply(make_agent(), make_generation_result())
        assert "def run():" in result.patched_source.patched_source
        assert "import os" in result.patched_source.patched_source

    def test_applied_proposals_recorded(self) -> None:
        result = APPLIER.apply(make_agent(), make_generation_result())
        assert len(result.patched_source.applied_proposals) == 1

    def test_has_changes_true(self) -> None:
        result = APPLIER.apply(make_agent(), make_generation_result())
        assert result.patched_source.has_changes is True

    def test_no_errors_on_success(self) -> None:
        result = APPLIER.apply(make_agent(), make_generation_result())
        assert result.patched_source.error_count == 0

    def test_generation_result_preserved(self) -> None:
        gen = make_generation_result()
        result = APPLIER.apply(make_agent(), gen)
        assert result.generation_result is gen


# ---------------------------------------------------------------------------
# Multiple proposals
# ---------------------------------------------------------------------------

class TestApplyMultipleProposals:
    def test_all_proposals_applied(self) -> None:
        proposals = [
            make_proposal(
                category=HookCategory.TASK_STARTED,
                changes=[make_change("logger.info('obs')", target_function="run")],
                import_additions=["import logging"],
            ),
            make_proposal(
                category=HookCategory.TASK_FAILED,
                changes=[make_change("policy_check()", target_function="run")],
                import_additions=["from governance import policy_check"],
            ),
        ]
        result = APPLIER.apply(make_agent(), make_generation_result(proposals))
        assert result.patched_source.applied_count == 2

    def test_both_fragments_present(self) -> None:
        proposals = [
            make_proposal(
                category=HookCategory.TASK_STARTED,
                changes=[make_change("logger.info('obs')", target_function="run")],
            ),
            make_proposal(
                category=HookCategory.TASK_FAILED,
                changes=[make_change("policy_check()", target_function="run")],
                import_additions=[],
            ),
        ]
        result = APPLIER.apply(make_agent(), make_generation_result(proposals))
        source = result.patched_source.patched_source
        assert "logger.info('obs')" in source
        assert "policy_check()" in source

    def test_imports_deduplicated_across_proposals(self) -> None:
        proposals = [
            make_proposal(
                category=HookCategory.TASK_STARTED,
                changes=[make_change("a()", target_function="run")],
                import_additions=["import logging"],
            ),
            make_proposal(
                category=HookCategory.TASK_FAILED,
                changes=[make_change("b()", target_function="run")],
                import_additions=["import logging"],
            ),
        ]
        result = APPLIER.apply(make_agent(), make_generation_result(proposals))
        source = result.patched_source.patched_source
        assert source.count("import logging") == 1

    def test_existing_import_not_duplicated(self) -> None:
        # "import os" is already in SIMPLE_SOURCE
        proposal = make_proposal(
            import_additions=["import os"],
            changes=[make_change("x = 1", target_function="run")],
        )
        result = APPLIER.apply(make_agent(), make_generation_result([proposal]))
        source = result.patched_source.patched_source
        assert source.count("import os") == 1


# ---------------------------------------------------------------------------
# File-level insertion locations
# ---------------------------------------------------------------------------

class TestInsertionLocations:
    def test_top_of_file_insert(self) -> None:
        change = make_change("# governance header", location=InsertionLocation.TOP_OF_FILE, target_function=None)
        proposal = make_proposal(changes=[change], import_additions=[])
        result = APPLIER.apply(make_agent(), make_generation_result([proposal]))
        lines = result.patched_source.patched_source.splitlines()
        assert lines[0] == "# governance header"

    def test_after_imports_insert(self) -> None:
        change = make_change("CONSTANT = True", location=InsertionLocation.AFTER_IMPORTS, target_function=None)
        proposal = make_proposal(changes=[change], import_additions=[])
        result = APPLIER.apply(make_agent(), make_generation_result([proposal]))
        source = result.patched_source.patched_source
        # CONSTANT must appear after imports
        import_pos = source.index("import os")
        constant_pos = source.index("CONSTANT = True")
        assert constant_pos > import_pos

    def test_around_function_produces_warning(self) -> None:
        change = make_change(
            "try_wrapper()",
            location=InsertionLocation.AROUND_FUNCTION,
            target_function="run",
        )
        proposal = make_proposal(changes=[change], import_additions=[])
        result = APPLIER.apply(make_agent(), make_generation_result([proposal]))
        assert result.patched_source.warning_count > 0

    def test_inline_with_target_function(self) -> None:
        change = make_change(
            "inline_hook()",
            location=InsertionLocation.INLINE,
            target_function="run",
        )
        proposal = make_proposal(changes=[change], import_additions=[])
        result = APPLIER.apply(make_agent(), make_generation_result([proposal]))
        assert "inline_hook()" in result.patched_source.patched_source
        assert result.patched_source.warning_count > 0


# ---------------------------------------------------------------------------
# Error isolation — failed proposals don't abort the run
# ---------------------------------------------------------------------------

class TestErrorIsolation:
    def test_failed_status_proposal_recorded_as_error(self) -> None:
        failed = make_proposal(status=ProposalStatus.FAILED, changes=[])
        result = APPLIER.apply(make_agent(), make_generation_result([failed]))
        assert result.patched_source.error_count >= 1

    def test_failed_proposal_does_not_abort_successful_one(self) -> None:
        good_change = make_change("logger.info('ok')", target_function="run")
        good = make_proposal(
            category=HookCategory.TASK_STARTED,
            changes=[good_change],
            import_additions=[],
        )
        bad = make_proposal(
            category=HookCategory.TASK_FAILED,
            status=ProposalStatus.FAILED,
            changes=[],
        )
        result = APPLIER.apply(make_agent(), make_generation_result([good, bad]))
        assert "logger.info('ok')" in result.patched_source.patched_source
        assert result.patched_source.applied_count == 1

    def test_partial_status_when_some_succeed_some_fail(self) -> None:
        good = make_proposal(
            category=HookCategory.TASK_STARTED,
            changes=[make_change("x = 1", target_function="run")],
            import_additions=[],
        )
        # This proposal is SUCCESS-status but points to a nonexistent function,
        # so the apply engine itself will fail while trying to resolve the location.
        bad_change = make_change(target_function="no_such_function")
        bad = make_proposal(
            category=HookCategory.TASK_FAILED,
            changes=[bad_change],
            import_additions=[],
        )
        result = APPLIER.apply(make_agent(), make_generation_result([good, bad]))
        assert result.status == ApplyStatus.PARTIAL

    def test_location_resolution_error_recorded(self) -> None:
        change = make_change(target_function="nonexistent_fn")
        proposal = make_proposal(changes=[change], import_additions=[])
        result = APPLIER.apply(make_agent(), make_generation_result([proposal]))
        assert result.patched_source.error_count >= 1
        assert result.status in (ApplyStatus.FAILED, ApplyStatus.PARTIAL)

    def test_source_not_corrupted_after_failed_proposal(self) -> None:
        good = make_proposal(
            category=HookCategory.TASK_STARTED,
            changes=[make_change("good_hook()", target_function="run")],
            import_additions=[],
        )
        bad_change = make_change(target_function="nonexistent_fn")
        bad = make_proposal(
            category=HookCategory.TASK_FAILED,
            changes=[bad_change],
            import_additions=[],
        )
        result = APPLIER.apply(make_agent(), make_generation_result([good, bad]))
        source = result.patched_source.patched_source
        # Original structure intact
        assert "def run():" in source
        assert "    x = 1" in source


# ---------------------------------------------------------------------------
# No proposals
# ---------------------------------------------------------------------------

class TestNoProposals:
    def test_no_successful_proposals_returns_failed(self) -> None:
        gen = make_generation_result([
            make_proposal(status=ProposalStatus.FAILED, changes=[])
        ])
        result = APPLIER.apply(make_agent(), gen)
        assert result.status == ApplyStatus.FAILED

    def test_empty_proposals_list(self) -> None:
        gen = make_generation_result([])
        result = APPLIER.apply(make_agent(), gen)
        assert result.patched_source is not None
        assert result.patched_source.patched_source == SIMPLE_SOURCE


# ---------------------------------------------------------------------------
# Dependency injection
# ---------------------------------------------------------------------------

class TestDependencyInjection:
    def test_custom_resolver_used(self) -> None:
        mock_resolver = MagicMock(spec=LocationResolver)
        mock_resolver.resolve.return_value = ResolvedLocation(line_number=1, indent="")

        applier = SourcePatchApplier(location_resolver=mock_resolver)
        gen = make_generation_result()
        applier.apply(make_agent(), gen)
        assert mock_resolver.resolve.called

    def test_resolver_error_captured_not_raised(self) -> None:
        mock_resolver = MagicMock(spec=LocationResolver)
        mock_resolver.resolve.side_effect = LocationResolutionError("boom")

        applier = SourcePatchApplier(location_resolver=mock_resolver)
        result = applier.apply(make_agent(), make_generation_result())
        # Should NOT raise — error is captured
        assert result.patched_source.error_count >= 1

    def test_unexpected_exception_from_resolver_captured(self) -> None:
        mock_resolver = MagicMock(spec=LocationResolver)
        mock_resolver.resolve.side_effect = RuntimeError("unexpected")

        applier = SourcePatchApplier(location_resolver=mock_resolver)
        result = applier.apply(make_agent(), make_generation_result())
        assert result.patched_source.error_count >= 1

    def test_default_dependencies_created_when_none(self) -> None:
        applier = SourcePatchApplier()
        assert applier._resolver is not None
        assert applier._editor is not None
        assert applier._imports is not None
