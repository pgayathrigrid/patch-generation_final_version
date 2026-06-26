from __future__ import annotations
"""Tests for domain entities."""

from pathlib import Path

import pytest

from awcp_instrumentation.domain.entities import (
    AgentSource,
    GovernanceHook,
    HookDetectionResult,
    HookValidationResult,
    InstrumentationPatch,
    ValidationReport,
)
from awcp_instrumentation.domain.enums import HookCategory, ValidationStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_hook(
    category: HookCategory = HookCategory.TASK_STARTED,
    name: str = "log_decision",
    line_number: int | None = None,
) -> GovernanceHook:
    return GovernanceHook(
        category=category,
        name=name,
        description="Test hook",
        line_number=line_number,
    )


def make_agent(source: str = "print('hello')") -> AgentSource:
    return AgentSource.from_string(source, name="test_agent")


# ---------------------------------------------------------------------------
# AgentSource
# ---------------------------------------------------------------------------

class TestAgentSource:
    def test_from_string_sets_name(self) -> None:
        agent = AgentSource.from_string("x = 1", name="my_agent")
        assert agent.agent_name == "my_agent"

    def test_default_name_from_path(self) -> None:
        agent = AgentSource(path=Path("agents/my_bot.py"), source_code="pass")
        assert agent.agent_name == "my_bot"

    def test_from_path(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.py"
        f.write_text("x = 42")
        agent = AgentSource.from_path(f)
        assert agent.source_code == "x = 42"
        assert agent.agent_name == "sample"


# ---------------------------------------------------------------------------
# GovernanceHook
# ---------------------------------------------------------------------------

class TestGovernanceHook:
    def test_is_present_when_line_number_set(self) -> None:
        hook = make_hook(line_number=10)
        assert hook.is_present() is True

    def test_is_not_present_when_no_line_number(self) -> None:
        hook = make_hook(line_number=None)
        assert hook.is_present() is False

    def test_frozen(self) -> None:
        hook = make_hook()
        with pytest.raises(Exception):
            hook.name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# HookDetectionResult
# ---------------------------------------------------------------------------

class TestHookDetectionResult:
    def test_fully_instrumented_when_no_missing(self) -> None:
        result = HookDetectionResult(
            agent=make_agent(),
            present_hooks=[make_hook()],
            missing_hooks=[],
        )
        assert result.is_fully_instrumented is True

    def test_not_fully_instrumented_when_missing_hooks(self) -> None:
        result = HookDetectionResult(
            agent=make_agent(),
            present_hooks=[],
            missing_hooks=[make_hook()],
        )
        assert result.is_fully_instrumented is False

    def test_missing_categories_deduplicated(self) -> None:
        h1 = make_hook(HookCategory.TASK_STARTED, "log_a")
        h2 = make_hook(HookCategory.TASK_STARTED, "log_b")
        result = HookDetectionResult(agent=make_agent(), missing_hooks=[h1, h2])
        assert result.missing_categories == [HookCategory.TASK_STARTED]


# ---------------------------------------------------------------------------
# InstrumentationPatch
# ---------------------------------------------------------------------------

class TestInstrumentationPatch:
    def test_hook_count(self) -> None:
        patch = InstrumentationPatch(
            original_agent=make_agent(),
            patched_source="# patched",
            inserted_hooks=[make_hook(), make_hook(name="other")],
        )
        assert patch.hook_count == 2

    def test_is_empty_when_no_hooks(self) -> None:
        patch = InstrumentationPatch(
            original_agent=make_agent(),
            patched_source="# same",
            inserted_hooks=[],
        )
        assert patch.is_empty is True


# ---------------------------------------------------------------------------
# ValidationReport
# ---------------------------------------------------------------------------

class TestValidationReport:
    def _make_report(self) -> ValidationReport:
        hooks = [
            HookValidationResult(
                hook=make_hook(HookCategory.TASK_STARTED),
                status=ValidationStatus.PASSED,
            ),
            HookValidationResult(
                hook=make_hook(HookCategory.TASK_FAILED, "check_policy"),
                status=ValidationStatus.FAILED,
                message="policy not triggered",
            ),
            HookValidationResult(
                hook=make_hook(HookCategory.LLM_CALL, "request_approval"),
                status=ValidationStatus.SKIPPED,
            ),
        ]
        return ValidationReport(
            agent_name="test_agent",
            overall_status=ValidationStatus.FAILED,
            hook_results=hooks,
        )

    def test_passed_count(self) -> None:
        report = self._make_report()
        assert len(report.passed) == 1

    def test_failed_count(self) -> None:
        report = self._make_report()
        assert len(report.failed) == 1

    def test_skipped_count(self) -> None:
        report = self._make_report()
        assert len(report.skipped) == 1

    def test_summary_contains_agent_name(self) -> None:
        report = self._make_report()
        assert "test_agent" in report.summary

    def test_hooks_by_category(self) -> None:
        report = self._make_report()
        by_cat = report.hooks_by_category()
        assert HookCategory.TASK_STARTED in by_cat
        assert HookCategory.TASK_FAILED in by_cat
