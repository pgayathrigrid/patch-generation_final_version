"""Tests for the default risk catalog — completeness and shape."""

import pytest

from awcp_instrumentation.application.gap_reporter.risk_catalog import DEFAULT_RISK_CATALOG
from awcp_instrumentation.application.gap_reporter.models import (
    GovernanceRecommendation,
    GovernanceRisk,
    RiskSeverity,
)
from awcp_instrumentation.domain.enums.hook_category import HookCategory


class TestDefaultRiskCatalogCompleteness:
    def test_all_ten_categories_covered(self) -> None:
        assert set(DEFAULT_RISK_CATALOG.keys()) == set(HookCategory)

    @pytest.mark.parametrize("category", list(HookCategory))
    def test_each_entry_has_risk_and_recommendation(self, category: HookCategory) -> None:
        entry = DEFAULT_RISK_CATALOG[category]
        assert len(entry) == 2
        risk, recommendation = entry
        assert isinstance(risk, GovernanceRisk)
        assert isinstance(recommendation, GovernanceRecommendation)


class TestDefaultRiskCatalogContent:
    @pytest.mark.parametrize("category", list(HookCategory))
    def test_risk_description_is_non_empty(self, category: HookCategory) -> None:
        risk, _ = DEFAULT_RISK_CATALOG[category]
        assert risk.description.strip()

    @pytest.mark.parametrize("category", list(HookCategory))
    def test_risk_impact_is_non_empty(self, category: HookCategory) -> None:
        risk, _ = DEFAULT_RISK_CATALOG[category]
        assert risk.impact.strip()

    @pytest.mark.parametrize("category", list(HookCategory))
    def test_recommendation_action_is_non_empty(self, category: HookCategory) -> None:
        _, rec = DEFAULT_RISK_CATALOG[category]
        assert rec.action.strip()

    @pytest.mark.parametrize("category", list(HookCategory))
    def test_recommendation_rationale_is_non_empty(self, category: HookCategory) -> None:
        _, rec = DEFAULT_RISK_CATALOG[category]
        assert rec.rationale.strip()

    @pytest.mark.parametrize("category", list(HookCategory))
    def test_instrumentation_hint_is_non_empty(self, category: HookCategory) -> None:
        _, rec = DEFAULT_RISK_CATALOG[category]
        assert rec.instrumentation_hint.strip()

    @pytest.mark.parametrize("category", list(HookCategory))
    def test_instrumentation_hint_contains_no_def_or_class(self, category: HookCategory) -> None:
        _, rec = DEFAULT_RISK_CATALOG[category]
        hint = rec.instrumentation_hint
        assert "def " not in hint, f"{category}: hint should not contain 'def'"
        assert "class " not in hint, f"{category}: hint should not contain 'class'"

    @pytest.mark.parametrize("category", list(HookCategory))
    def test_priority_is_positive_integer(self, category: HookCategory) -> None:
        _, rec = DEFAULT_RISK_CATALOG[category]
        assert isinstance(rec.priority, int)
        assert rec.priority >= 1

    def test_task_failed_has_critical_severity(self) -> None:
        risk, _ = DEFAULT_RISK_CATALOG[HookCategory.TASK_FAILED]
        assert risk.severity == RiskSeverity.CRITICAL

    def test_llm_call_has_critical_severity(self) -> None:
        risk, _ = DEFAULT_RISK_CATALOG[HookCategory.LLM_CALL]
        assert risk.severity == RiskSeverity.CRITICAL

    def test_tool_call_has_critical_severity(self) -> None:
        risk, _ = DEFAULT_RISK_CATALOG[HookCategory.TOOL_CALL]
        assert risk.severity == RiskSeverity.CRITICAL

    def test_budget_exhausted_has_critical_severity(self) -> None:
        risk, _ = DEFAULT_RISK_CATALOG[HookCategory.BUDGET_EXHAUSTED]
        assert risk.severity == RiskSeverity.CRITICAL

    def test_task_started_has_high_severity(self) -> None:
        risk, _ = DEFAULT_RISK_CATALOG[HookCategory.TASK_STARTED]
        assert risk.severity == RiskSeverity.HIGH

    def test_token_usage_is_not_critical(self) -> None:
        risk, _ = DEFAULT_RISK_CATALOG[HookCategory.TOKEN_USAGE]
        assert risk.severity not in (RiskSeverity.CRITICAL,)

    def test_all_severities_are_valid_enum_values(self) -> None:
        for cat in HookCategory:
            risk, _ = DEFAULT_RISK_CATALOG[cat]
            assert isinstance(risk.severity, RiskSeverity)
