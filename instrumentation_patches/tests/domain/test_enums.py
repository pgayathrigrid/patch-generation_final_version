"""Tests for domain enums."""

import pytest

from awcp_instrumentation.domain.enums import HookCategory, ValidationStatus


class TestHookCategory:
    def test_all_sixteen_categories_exist(self) -> None:
        expected = {
            "task_started", "task_completed", "task_failed",
            "llm_call", "synthesize", "tool_call", "web_search",
            "token_usage", "budget_warn", "budget_exhausted",
            "observability", "policy", "approval",
            "feature_flag", "recovery", "degradation",
        }
        assert {c.value for c in HookCategory} == expected

    def test_string_comparison(self) -> None:
        assert HookCategory.TASK_STARTED == "task_started"

    def test_enum_from_string(self) -> None:
        assert HookCategory("llm_call") is HookCategory.LLM_CALL

    def test_budget_categories(self) -> None:
        assert HookCategory.BUDGET_WARN == "budget_warn"
        assert HookCategory.BUDGET_EXHAUSTED == "budget_exhausted"


class TestValidationStatus:
    def test_all_statuses_exist(self) -> None:
        values = {s.value for s in ValidationStatus}
        assert values == {"passed", "failed", "skipped", "pending"}

    def test_string_comparison(self) -> None:
        assert ValidationStatus.PASSED == "passed"
