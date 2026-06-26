from __future__ import annotations
"""Tests for GovernanceGapReport models and RiskSeverity ordering."""

from datetime import datetime
from pathlib import Path

import pytest

from awcp_instrumentation.application.gap_reporter.models import (
    GovernanceGap,
    GovernanceGapReport,
    GovernanceRecommendation,
    GovernanceRisk,
    RiskSeverity,
    severity_rank,
)
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_risk(severity: RiskSeverity = RiskSeverity.HIGH) -> GovernanceRisk:
    return GovernanceRisk(severity=severity, description="desc", impact="impact")


def make_recommendation(priority: int = 1) -> GovernanceRecommendation:
    return GovernanceRecommendation(
        action="add hook",
        rationale="required",
        instrumentation_hint="insert call",
        priority=priority,
    )


def make_hook(category: HookCategory = HookCategory.TASK_STARTED) -> GovernanceHook:
    return GovernanceHook(category=category, name="test_hook", description="test")


def make_gap(
    category: HookCategory = HookCategory.TASK_STARTED,
    severity: RiskSeverity = RiskSeverity.HIGH,
    priority: int = 1,
) -> GovernanceGap:
    return GovernanceGap(
        hook=make_hook(category),
        risk=make_risk(severity),
        recommendation=make_recommendation(priority),
    )


def make_report(
    gaps: list | None = None,
    present_hooks: list | None = None,
    overall_risk: RiskSeverity = RiskSeverity.HIGH,
) -> GovernanceGapReport:
    agent = AgentSource.from_string("x = 1", name="test_agent")
    return GovernanceGapReport(
        agent=agent,
        present_hooks=present_hooks or [],
        gaps=gaps or [],
        overall_risk_level=overall_risk,
        summary="test summary",
    )


# ---------------------------------------------------------------------------
# RiskSeverity
# ---------------------------------------------------------------------------

class TestRiskSeverity:
    def test_all_five_levels_exist(self) -> None:
        values = {s.value for s in RiskSeverity}
        assert values == {"none", "low", "medium", "high", "critical"}

    def test_string_comparison(self) -> None:
        assert RiskSeverity.CRITICAL == "critical"
        assert RiskSeverity.NONE == "none"

    def test_from_string(self) -> None:
        assert RiskSeverity("high") is RiskSeverity.HIGH


class TestSeverityRank:
    def test_none_is_lowest(self) -> None:
        assert severity_rank(RiskSeverity.NONE) == 0

    def test_critical_is_highest(self) -> None:
        assert severity_rank(RiskSeverity.CRITICAL) > severity_rank(RiskSeverity.HIGH)
        assert severity_rank(RiskSeverity.HIGH) > severity_rank(RiskSeverity.MEDIUM)
        assert severity_rank(RiskSeverity.MEDIUM) > severity_rank(RiskSeverity.LOW)
        assert severity_rank(RiskSeverity.LOW) > severity_rank(RiskSeverity.NONE)

    def test_can_sort_severities(self) -> None:
        levels = [RiskSeverity.HIGH, RiskSeverity.CRITICAL, RiskSeverity.LOW, RiskSeverity.NONE]
        sorted_levels = sorted(levels, key=severity_rank)
        assert sorted_levels == [
            RiskSeverity.NONE,
            RiskSeverity.LOW,
            RiskSeverity.HIGH,
            RiskSeverity.CRITICAL,
        ]

    def test_max_by_rank(self) -> None:
        gaps = [
            make_gap(severity=RiskSeverity.MEDIUM),
            make_gap(severity=RiskSeverity.CRITICAL),
            make_gap(severity=RiskSeverity.LOW),
        ]
        worst = max(gaps, key=lambda g: severity_rank(g.severity))
        assert worst.severity == RiskSeverity.CRITICAL


# ---------------------------------------------------------------------------
# GovernanceRisk
# ---------------------------------------------------------------------------

class TestGovernanceRisk:
    def test_is_frozen(self) -> None:
        risk = make_risk()
        with pytest.raises(Exception):
            risk.severity = RiskSeverity.LOW  # type: ignore[misc]

    def test_fields_accessible(self) -> None:
        risk = GovernanceRisk(
            severity=RiskSeverity.CRITICAL,
            description="very bad",
            impact="everything breaks",
        )
        assert risk.severity == RiskSeverity.CRITICAL
        assert risk.description == "very bad"
        assert risk.impact == "everything breaks"


# ---------------------------------------------------------------------------
# GovernanceRecommendation
# ---------------------------------------------------------------------------

class TestGovernanceRecommendation:
    def test_is_frozen(self) -> None:
        rec = make_recommendation()
        with pytest.raises(Exception):
            rec.priority = 99  # type: ignore[misc]

    def test_instrumentation_hint_is_natural_language(self) -> None:
        rec = GovernanceRecommendation(
            action="Add logging",
            rationale="Required",
            instrumentation_hint="Insert a log call before each action",
            priority=1,
        )
        # Hint must not contain Python code markers
        assert "def " not in rec.instrumentation_hint
        assert "import " not in rec.instrumentation_hint


# ---------------------------------------------------------------------------
# GovernanceGap
# ---------------------------------------------------------------------------

class TestGovernanceGap:
    def test_is_frozen(self) -> None:
        gap = make_gap()
        with pytest.raises(Exception):
            gap.risk = make_risk(RiskSeverity.LOW)  # type: ignore[misc]

    def test_category_convenience_property(self) -> None:
        gap = make_gap(category=HookCategory.TASK_FAILED)
        assert gap.category == HookCategory.TASK_FAILED

    def test_severity_convenience_property(self) -> None:
        gap = make_gap(severity=RiskSeverity.CRITICAL)
        assert gap.severity == RiskSeverity.CRITICAL

    def test_hook_line_number_is_none(self) -> None:
        gap = make_gap()
        # Missing hooks must not have a line number — they were not found.
        assert gap.hook.line_number is None


# ---------------------------------------------------------------------------
# GovernanceGapReport — structural tests
# ---------------------------------------------------------------------------

class TestGovernanceGapReport:
    def test_is_fully_instrumented_when_no_gaps(self) -> None:
        report = make_report(gaps=[], overall_risk=RiskSeverity.NONE)
        assert report.is_fully_instrumented is True

    def test_not_fully_instrumented_when_gaps_exist(self) -> None:
        report = make_report(gaps=[make_gap()])
        assert report.is_fully_instrumented is False

    def test_ready_for_patching_when_gaps_exist(self) -> None:
        report = make_report(gaps=[make_gap()])
        assert report.ready_for_patching is True

    def test_not_ready_for_patching_when_no_gaps(self) -> None:
        report = make_report(gaps=[])
        assert report.ready_for_patching is False

    def test_gap_count(self) -> None:
        report = make_report(gaps=[make_gap(), make_gap(HookCategory.TASK_FAILED)])
        assert report.gap_count == 2

    def test_present_count(self) -> None:
        hooks = [make_hook(HookCategory.TASK_STARTED), make_hook(HookCategory.BUDGET_WARN)]
        report = make_report(present_hooks=hooks)
        assert report.present_count == 2

    def test_generated_at_defaults_to_now(self) -> None:
        before = datetime.utcnow()
        report = make_report()
        after = datetime.utcnow()
        assert before <= report.generated_at <= after

    def test_metadata_defaults_to_empty_dict(self) -> None:
        report = make_report()
        assert report.metadata == {}


# ---------------------------------------------------------------------------
# GovernanceGapReport — computed properties
# ---------------------------------------------------------------------------

class TestGovernanceGapReportComputedProperties:
    def _make_mixed_report(self) -> GovernanceGapReport:
        gaps = [
            make_gap(HookCategory.TASK_FAILED, RiskSeverity.CRITICAL, priority=1),
            make_gap(HookCategory.LLM_CALL, RiskSeverity.CRITICAL, priority=1),
            make_gap(HookCategory.TASK_STARTED, RiskSeverity.HIGH, priority=2),
            make_gap(HookCategory.TOKEN_USAGE, RiskSeverity.MEDIUM, priority=3),
        ]
        present = [
            make_hook(HookCategory.BUDGET_WARN),
            make_hook(HookCategory.TOOL_CALL),
        ]
        return make_report(gaps=gaps, present_hooks=present, overall_risk=RiskSeverity.CRITICAL)

    def test_critical_gaps(self) -> None:
        report = self._make_mixed_report()
        assert len(report.critical_gaps) == 2
        assert all(g.severity == RiskSeverity.CRITICAL for g in report.critical_gaps)

    def test_high_gaps(self) -> None:
        report = self._make_mixed_report()
        assert len(report.high_gaps) == 1
        assert report.high_gaps[0].category == HookCategory.TASK_STARTED

    def test_gaps_by_severity(self) -> None:
        report = self._make_mixed_report()
        by_sev = report.gaps_by_severity
        assert len(by_sev[RiskSeverity.CRITICAL]) == 2
        assert len(by_sev[RiskSeverity.HIGH]) == 1
        assert len(by_sev[RiskSeverity.MEDIUM]) == 1
        assert RiskSeverity.LOW not in by_sev

    def test_missing_categories(self) -> None:
        report = self._make_mixed_report()
        missing = set(report.missing_categories)
        assert HookCategory.TASK_FAILED in missing
        assert HookCategory.TASK_STARTED in missing

    def test_present_categories(self) -> None:
        report = self._make_mixed_report()
        present = set(report.present_categories)
        assert HookCategory.BUDGET_WARN in present
        assert HookCategory.TOOL_CALL in present

    def test_gaps_ordered_by_priority(self) -> None:
        gaps = [
            make_gap(HookCategory.TOKEN_USAGE, RiskSeverity.MEDIUM, priority=3),
            make_gap(HookCategory.TASK_FAILED, RiskSeverity.CRITICAL, priority=1),
            make_gap(HookCategory.TASK_STARTED, RiskSeverity.HIGH, priority=2),
        ]
        report = make_report(gaps=gaps)
        ordered = report.gaps_ordered_by_priority
        priorities = [g.recommendation.priority for g in ordered]
        assert priorities == sorted(priorities)

    def test_gap_for_category_found(self) -> None:
        report = self._make_mixed_report()
        gap = report.gap_for_category(HookCategory.TASK_FAILED)
        assert gap is not None
        assert gap.category == HookCategory.TASK_FAILED

    def test_gap_for_category_not_found(self) -> None:
        report = self._make_mixed_report()
        gap = report.gap_for_category(HookCategory.BUDGET_EXHAUSTED)
        assert gap is None
