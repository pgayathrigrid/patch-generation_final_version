"""Tests for HookPresenceChecker."""
from __future__ import annotations

import pytest

from awcp_instrumentation.application.sandbox.hook_presence import HookPresenceChecker
from awcp_instrumentation.application.generator.models import (
    InsertionLocation,
    PatchChange,
)

CHECKER = HookPresenceChecker()

SOURCE = """\
import os
import logging

logger = logging.getLogger(__name__)

def run():
    logger.info("decision made")
    x = 1
    return x
"""


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


# ---------------------------------------------------------------------------
# is_present — exact match
# ---------------------------------------------------------------------------

class TestIsPresentExact:
    def test_single_line_present(self) -> None:
        assert CHECKER.is_present(SOURCE, make_change('logger.info("decision made")'))

    def test_single_line_absent(self) -> None:
        assert not CHECKER.is_present(SOURCE, make_change("policy_check()"))

    def test_multiline_fragment_present(self) -> None:
        fragment = "logger = logging.getLogger(__name__)\n\ndef run():"
        assert CHECKER.is_present(SOURCE, make_change(fragment, target_function=None))

    def test_empty_fragment_returns_false(self) -> None:
        assert not CHECKER.is_present(SOURCE, make_change(""))

    def test_empty_source_returns_false(self) -> None:
        assert not CHECKER.is_present("", make_change("logger.info('x')"))

    def test_partial_match_returns_true(self) -> None:
        assert CHECKER.is_present(SOURCE, make_change("logger.info"))


# ---------------------------------------------------------------------------
# is_present — normalised match
# ---------------------------------------------------------------------------

class TestIsPresentNormalised:
    def test_extra_spaces_around_fragment(self) -> None:
        # Fragment has extra leading spaces; normalised match should catch it
        fragment = "  logger.info(  'decision made'  )  "
        # Won't exact-match but the checker doesn't normalise inner parens —
        # this tests that whitespace at the outer level is collapsed.
        # The source has logger.info("decision made") — different quotes,
        # so we need a genuinely normalised case.
        fragment = "logger.info(\n    'decision made'\n)"
        # Normalised: "logger.info( 'decision made' )"
        # Not the same as source so this should fail (different quotes, collapsed)
        # — the point is normalisation doesn't change quotes.
        # Use a real normalisation scenario:
        fragment = "x  =  1"
        assert CHECKER.is_present(SOURCE, make_change(fragment))

    def test_newline_collapsed_to_space(self) -> None:
        # "    x = 1" in source; "x =\n1" normalises to "x = 1"
        # Source has "    x = 1", normalised source has "x = 1"
        fragment = "x =\n1"
        assert CHECKER.is_present(SOURCE, make_change(fragment))


# ---------------------------------------------------------------------------
# check_proposal
# ---------------------------------------------------------------------------

class TestCheckProposal:
    def _make_proposal(self, *fragments: str):
        from unittest.mock import MagicMock
        from awcp_instrumentation.application.gap_reporter.models import (
            GovernanceGap, GovernanceRisk, GovernanceRecommendation, RiskSeverity
        )
        from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
        from awcp_instrumentation.domain.enums.hook_category import HookCategory
        from awcp_instrumentation.application.generator.models import (
            PatchProposal, PatchMetadata, ProposalStatus
        )
        from datetime import datetime

        hook = GovernanceHook(
            category=HookCategory.TASK_STARTED, name="obs_hook",
            description="test", signature=None, line_number=None
        )
        risk = GovernanceRisk(
            severity=RiskSeverity.HIGH, description="missing", impact="bad"
        )
        rec = GovernanceRecommendation(
            action="add", rationale="gov", instrumentation_hint="use logging", priority=1
        )
        gap = GovernanceGap(hook=hook, risk=risk, recommendation=rec)
        changes = [make_change(f) for f in fragments]
        return PatchProposal(
            gap=gap,
            status=ProposalStatus.SUCCESS,
            changes=changes,
            import_additions=[],
            explanation="test",
            confidence=0.9,
            metadata=PatchMetadata(
                model="test", provider_name="mock",
                prompt_tokens=10, completion_tokens=10,
                temperature=0.2, generated_at=datetime.utcnow()
            ),
            raw_llm_response="{}",
        )

    def test_returns_dict_per_change(self) -> None:
        proposal = self._make_proposal('logger.info("decision made")')
        result = CHECKER.check_proposal(SOURCE, proposal)
        assert len(result) == 1

    def test_present_change_is_true(self) -> None:
        proposal = self._make_proposal('logger.info("decision made")')
        result = CHECKER.check_proposal(SOURCE, proposal)
        assert list(result.values())[0] is True

    def test_absent_change_is_false(self) -> None:
        proposal = self._make_proposal("policy_check()")
        result = CHECKER.check_proposal(SOURCE, proposal)
        assert list(result.values())[0] is False

    def test_multiple_changes_mixed(self) -> None:
        proposal = self._make_proposal('logger.info("decision made")', "policy_check()")
        result = CHECKER.check_proposal(SOURCE, proposal)
        vals = list(result.values())
        assert True in vals
        assert False in vals


# ---------------------------------------------------------------------------
# all_present
# ---------------------------------------------------------------------------

class TestAllPresent:
    def _proposal_with(self, *fragments: str):
        from tests.application.sandbox.test_hook_presence import TestCheckProposal
        return TestCheckProposal()._make_proposal(*fragments)

    def test_true_when_all_present(self) -> None:
        p = self._proposal_with('logger.info("decision made")', "x = 1")
        assert CHECKER.all_present(SOURCE, p) is True

    def test_false_when_one_missing(self) -> None:
        p = self._proposal_with('logger.info("decision made")', "missing_fn()")
        assert CHECKER.all_present(SOURCE, p) is False

    def test_true_when_no_changes(self) -> None:
        p = self._proposal_with()
        # no changes → trivially all present
        assert CHECKER.all_present(SOURCE, p) is True


# ---------------------------------------------------------------------------
# missing_changes
# ---------------------------------------------------------------------------

class TestMissingChanges:
    def _proposal_with(self, *fragments: str):
        return TestCheckProposal()._make_proposal(*fragments)

    def test_no_missing_when_all_present(self) -> None:
        p = self._proposal_with('logger.info("decision made")')
        result = CHECKER.missing_changes(SOURCE, [p])
        assert len(result) == 1
        proposal, missing = result[0]
        assert proposal is p
        assert missing == []

    def test_returns_missing_change(self) -> None:
        p = self._proposal_with("missing_fn()")
        result = CHECKER.missing_changes(SOURCE, [p])
        _, missing = result[0]
        assert len(missing) == 1

    def test_multiple_proposals(self) -> None:
        p1 = self._proposal_with('logger.info("decision made")')
        p2 = self._proposal_with("missing_fn()")
        result = CHECKER.missing_changes(SOURCE, [p1, p2])
        pairs = {id(prop): missing for prop, missing in result}
        assert pairs[id(p1)] == []
        assert len(pairs[id(p2)]) == 1
