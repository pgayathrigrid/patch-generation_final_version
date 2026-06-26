"""Tests for GovernanceGapReporter — the orchestrating concrete class."""
from __future__ import annotations

from typing import List, Optional

import pytest

from awcp_instrumentation.application.gap_reporter import (
    DEFAULT_RISK_CATALOG,
    GapReporter,
    GovernanceGapReport,
    GovernanceGapReporter,
    GovernanceRecommendation,
    GovernanceRisk,
    RiskCatalog,
    RiskSeverity,
)
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.entities.hook_detection_result import HookDetectionResult
from awcp_instrumentation.domain.enums.hook_category import HookCategory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def agent(name: str = "test_agent") -> AgentSource:
    return AgentSource.from_string("x = 1", name=name)


def make_hook(
    category: HookCategory,
    line_number: int | None = None,
) -> GovernanceHook:
    return GovernanceHook(
        category=category,
        name=f"{category.value}_hook",
        description=f"{category.value} hook",
        line_number=line_number,
    )


def make_detection_result(
    present_categories: List[HookCategory] | None = None,
    missing_categories: List[HookCategory] | None = None,
    agent_name: str = "test_agent",
) -> HookDetectionResult:
    present = [make_hook(c, line_number=1) for c in (present_categories or [])]
    missing = [make_hook(c) for c in (missing_categories or [])]
    return HookDetectionResult(agent=agent(agent_name), present_hooks=present, missing_hooks=missing)


ALL_CATEGORIES = list(HookCategory)
NO_CATEGORIES: List[HookCategory] = []


# ---------------------------------------------------------------------------
# Interface contract
# ---------------------------------------------------------------------------

class TestGapReporterInterface:
    def test_is_gap_reporter(self) -> None:
        assert isinstance(GovernanceGapReporter(), GapReporter)

    def test_generate_returns_gap_report(self) -> None:
        result = GovernanceGapReporter().generate(make_detection_result())
        assert isinstance(result, GovernanceGapReport)


# ---------------------------------------------------------------------------
# Fully instrumented agent
# ---------------------------------------------------------------------------

class TestFullyInstrumentedAgent:
    def test_no_gaps_when_all_hooks_present(self) -> None:
        detection = make_detection_result(present_categories=ALL_CATEGORIES)
        report = GovernanceGapReporter().generate(detection)
        assert report.gap_count == 0

    def test_is_fully_instrumented_true(self) -> None:
        detection = make_detection_result(present_categories=ALL_CATEGORIES)
        report = GovernanceGapReporter().generate(detection)
        assert report.is_fully_instrumented is True

    def test_ready_for_patching_false(self) -> None:
        detection = make_detection_result(present_categories=ALL_CATEGORIES)
        report = GovernanceGapReporter().generate(detection)
        assert report.ready_for_patching is False

    def test_overall_risk_is_none(self) -> None:
        detection = make_detection_result(present_categories=ALL_CATEGORIES)
        report = GovernanceGapReporter().generate(detection)
        assert report.overall_risk_level == RiskSeverity.NONE

    def test_summary_mentions_fully_instrumented(self) -> None:
        detection = make_detection_result(present_categories=ALL_CATEGORIES)
        report = GovernanceGapReporter().generate(detection)
        assert "fully instrumented" in report.summary.lower()


# ---------------------------------------------------------------------------
# Agent with all hooks missing
# ---------------------------------------------------------------------------

class TestAllHooksMissing:
    def test_ten_gaps_produced(self) -> None:
        detection = make_detection_result(missing_categories=ALL_CATEGORIES)
        report = GovernanceGapReporter().generate(detection)
        assert report.gap_count == len(ALL_CATEGORIES)

    def test_ready_for_patching_true(self) -> None:
        detection = make_detection_result(missing_categories=ALL_CATEGORIES)
        report = GovernanceGapReporter().generate(detection)
        assert report.ready_for_patching is True

    def test_overall_risk_is_critical(self) -> None:
        detection = make_detection_result(missing_categories=ALL_CATEGORIES)
        report = GovernanceGapReporter().generate(detection)
        # TASK_FAILED, LLM_CALL, TOOL_CALL, BUDGET_EXHAUSTED are CRITICAL
        assert report.overall_risk_level == RiskSeverity.CRITICAL

    def test_all_categories_in_missing(self) -> None:
        detection = make_detection_result(missing_categories=ALL_CATEGORIES)
        report = GovernanceGapReporter().generate(detection)
        assert set(report.missing_categories) == set(HookCategory)

    def test_present_hooks_is_empty(self) -> None:
        detection = make_detection_result(missing_categories=ALL_CATEGORIES)
        report = GovernanceGapReporter().generate(detection)
        assert report.present_hooks == []

    def test_summary_contains_gap_count(self) -> None:
        detection = make_detection_result(missing_categories=ALL_CATEGORIES)
        report = GovernanceGapReporter().generate(detection)
        assert str(len(ALL_CATEGORIES)) in report.summary


# ---------------------------------------------------------------------------
# Partial instrumentation
# ---------------------------------------------------------------------------

class TestPartialInstrumentation:
    def test_correct_gap_count(self) -> None:
        detection = make_detection_result(
            present_categories=[HookCategory.TASK_STARTED, HookCategory.BUDGET_WARN],
            missing_categories=[
                HookCategory.TASK_FAILED,
                HookCategory.LLM_CALL,
                HookCategory.SYNTHESIZE,
                HookCategory.TOOL_CALL,
                HookCategory.WEB_SEARCH,
                HookCategory.TOKEN_USAGE,
                HookCategory.BUDGET_EXHAUSTED,
                HookCategory.TASK_COMPLETED,
            ],
        )
        report = GovernanceGapReporter().generate(detection)
        assert report.gap_count == 8
        assert report.present_count == 2

    def test_present_hooks_preserved(self) -> None:
        detection = make_detection_result(
            present_categories=[HookCategory.TASK_STARTED],
            missing_categories=[HookCategory.TASK_FAILED],
        )
        report = GovernanceGapReporter().generate(detection)
        assert len(report.present_hooks) == 1
        assert report.present_hooks[0].category == HookCategory.TASK_STARTED

    def test_gap_has_correct_category(self) -> None:
        detection = make_detection_result(missing_categories=[HookCategory.TASK_FAILED])
        report = GovernanceGapReporter().generate(detection)
        assert report.gaps[0].category == HookCategory.TASK_FAILED

    def test_gap_has_risk_from_catalog(self) -> None:
        detection = make_detection_result(missing_categories=[HookCategory.TASK_FAILED])
        report = GovernanceGapReporter().generate(detection)
        gap = report.gaps[0]
        catalog_risk, _ = DEFAULT_RISK_CATALOG[HookCategory.TASK_FAILED]
        assert gap.risk == catalog_risk

    def test_gap_has_recommendation_from_catalog(self) -> None:
        detection = make_detection_result(missing_categories=[HookCategory.TASK_STARTED])
        report = GovernanceGapReporter().generate(detection)
        gap = report.gaps[0]
        _, catalog_rec = DEFAULT_RISK_CATALOG[HookCategory.TASK_STARTED]
        assert gap.recommendation == catalog_rec


# ---------------------------------------------------------------------------
# Gap ordering
# ---------------------------------------------------------------------------

class TestGapOrdering:
    def test_critical_gaps_come_first(self) -> None:
        detection = make_detection_result(
            missing_categories=[
                HookCategory.TOKEN_USAGE,    # MEDIUM
                HookCategory.TASK_FAILED,    # CRITICAL
                HookCategory.TASK_STARTED,   # HIGH
            ]
        )
        report = GovernanceGapReporter().generate(detection)
        severities = [g.severity for g in report.gaps]
        critical_idx = next(i for i, s in enumerate(severities) if s == RiskSeverity.CRITICAL)
        high_idx = next(i for i, s in enumerate(severities) if s == RiskSeverity.HIGH)
        medium_idx = next(i for i, s in enumerate(severities) if s == RiskSeverity.MEDIUM)
        assert critical_idx < high_idx < medium_idx


# ---------------------------------------------------------------------------
# Overall risk computation
# ---------------------------------------------------------------------------

class TestOverallRisk:
    def test_no_gaps_gives_none_risk(self) -> None:
        report = GovernanceGapReporter().generate(
            make_detection_result(present_categories=ALL_CATEGORIES)
        )
        assert report.overall_risk_level == RiskSeverity.NONE

    def test_only_medium_gaps_gives_medium_risk(self) -> None:
        report = GovernanceGapReporter().generate(
            make_detection_result(missing_categories=[HookCategory.TOKEN_USAGE])
        )
        # TOKEN_USAGE is MEDIUM in the default catalog
        assert report.overall_risk_level == RiskSeverity.MEDIUM

    def test_mixed_severity_gives_highest(self) -> None:
        report = GovernanceGapReporter().generate(
            make_detection_result(
                missing_categories=[HookCategory.TASK_STARTED, HookCategory.TASK_FAILED]
            )
        )
        # TASK_FAILED is CRITICAL, TASK_STARTED is HIGH → overall = CRITICAL
        assert report.overall_risk_level == RiskSeverity.CRITICAL


# ---------------------------------------------------------------------------
# Agent metadata
# ---------------------------------------------------------------------------

class TestReportMetadata:
    def test_agent_name_preserved(self) -> None:
        detection = make_detection_result(agent_name="my_bot")
        report = GovernanceGapReporter().generate(detection)
        assert report.agent.agent_name == "my_bot"

    def test_metadata_contains_agent_path(self) -> None:
        detection = make_detection_result()
        report = GovernanceGapReporter().generate(detection)
        assert "agent_path" in report.metadata

    def test_metadata_contains_generated_by(self) -> None:
        detection = make_detection_result()
        report = GovernanceGapReporter().generate(detection)
        assert report.metadata.get("generated_by") == "GovernanceGapReporter"

    def test_summary_contains_agent_name(self) -> None:
        detection = make_detection_result(agent_name="clever_bot")
        report = GovernanceGapReporter().generate(detection)
        assert "clever_bot" in report.summary


# ---------------------------------------------------------------------------
# Custom catalog injection
# ---------------------------------------------------------------------------

class TestCustomCatalogInjection:
    def _make_minimal_catalog(self) -> RiskCatalog:
        risk = GovernanceRisk(
            severity=RiskSeverity.LOW,
            description="custom risk",
            impact="minimal",
        )
        rec = GovernanceRecommendation(
            action="custom action",
            rationale="custom rationale",
            instrumentation_hint="custom hint",
            priority=1,
        )
        return {cat: (risk, rec) for cat in HookCategory}

    def test_custom_catalog_risk_is_used(self) -> None:
        catalog = self._make_minimal_catalog()
        reporter = GovernanceGapReporter(catalog=catalog)
        detection = make_detection_result(missing_categories=[HookCategory.TASK_FAILED])
        report = reporter.generate(detection)
        assert report.gaps[0].risk.severity == RiskSeverity.LOW

    def test_custom_catalog_overrides_default(self) -> None:
        catalog = self._make_minimal_catalog()
        reporter = GovernanceGapReporter(catalog=catalog)
        detection = make_detection_result(missing_categories=ALL_CATEGORIES)
        report = reporter.generate(detection)
        assert all(g.severity == RiskSeverity.LOW for g in report.gaps)
        assert report.overall_risk_level == RiskSeverity.LOW

    def test_unknown_category_falls_back_gracefully(self) -> None:
        # Catalog with only one category — others fall back to default handling
        partial_catalog: RiskCatalog = {
            HookCategory.TASK_STARTED: DEFAULT_RISK_CATALOG[HookCategory.TASK_STARTED]
        }
        reporter = GovernanceGapReporter(catalog=partial_catalog)
        detection = make_detection_result(missing_categories=[HookCategory.TASK_FAILED])
        report = reporter.generate(detection)
        assert report.gap_count == 1
        assert report.gaps[0].category == HookCategory.TASK_FAILED


# ---------------------------------------------------------------------------
# required_categories filter (capability-aware gap reporting)
# ---------------------------------------------------------------------------

class TestRequiredCategoriesFilter:
    """Verify that the gap reporter respects the capability-derived required set."""

    def test_only_required_hooks_reported_as_gaps(self) -> None:
        # All hooks missing, but only TASK_STARTED and LLM_CALL are required
        detection = make_detection_result(missing_categories=ALL_CATEGORIES)
        required = frozenset({HookCategory.TASK_STARTED, HookCategory.LLM_CALL})
        report = GovernanceGapReporter().generate(detection, required_categories=required)
        assert report.gap_count == 2
        gap_categories = {g.category for g in report.gaps}
        assert gap_categories == required

    def test_unrequired_missing_hook_not_reported(self) -> None:
        # TOOL_CALL is missing but not required (pure LLM agent)
        detection = make_detection_result(missing_categories=[HookCategory.TOOL_CALL])
        required = frozenset({HookCategory.TASK_STARTED, HookCategory.LLM_CALL})
        report = GovernanceGapReporter().generate(detection, required_categories=required)
        assert report.gap_count == 0

    def test_none_required_categories_reports_all_missing(self) -> None:
        detection = make_detection_result(missing_categories=ALL_CATEGORIES)
        report = GovernanceGapReporter().generate(detection, required_categories=None)
        assert report.gap_count == len(ALL_CATEGORIES)

    def test_empty_required_categories_produces_no_gaps(self) -> None:
        detection = make_detection_result(missing_categories=ALL_CATEGORIES)
        report = GovernanceGapReporter().generate(detection, required_categories=frozenset())
        assert report.gap_count == 0

    def test_required_categories_accepts_set_type(self) -> None:
        # Accepts plain set, not just frozenset
        detection = make_detection_result(missing_categories=[HookCategory.LLM_CALL])
        required = {HookCategory.LLM_CALL}
        report = GovernanceGapReporter().generate(detection, required_categories=required)
        assert report.gap_count == 1

    def test_present_hooks_unaffected_by_filter(self) -> None:
        detection = make_detection_result(
            present_categories=[HookCategory.TASK_STARTED],
            missing_categories=[HookCategory.TOOL_CALL, HookCategory.LLM_CALL],
        )
        required = frozenset({HookCategory.LLM_CALL})
        report = GovernanceGapReporter().generate(detection, required_categories=required)
        # Present hooks always preserved
        assert len(report.present_hooks) == 1
        # Only LLM_CALL gap reported, not TOOL_CALL
        assert report.gap_count == 1
        assert report.gaps[0].category == HookCategory.LLM_CALL

    def test_generate_all_passes_required_categories(self) -> None:
        detections = [
            make_detection_result(missing_categories=[HookCategory.TOOL_CALL]),
            make_detection_result(missing_categories=[HookCategory.LLM_CALL]),
        ]
        required = frozenset({HookCategory.LLM_CALL})
        reports = GovernanceGapReporter().generate_all(detections, required_categories=required)
        assert reports[0].gap_count == 0   # TOOL_CALL not required
        assert reports[1].gap_count == 1   # LLM_CALL is required
