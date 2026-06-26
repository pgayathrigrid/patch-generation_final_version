"""Tests for RuleBasedHookDetector — the orchestration layer."""

from typing import List
from unittest.mock import MagicMock

import pytest

from awcp_instrumentation.application.detector import (
    RuleBasedHookDetector,
    DetectionRule,
)
from awcp_instrumentation.application.detector.interface import HookDetector
from awcp_instrumentation.application.scanner.result import RepositoryScanResult
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.entities.hook_detection_result import HookDetectionResult
from awcp_instrumentation.domain.enums.hook_category import HookCategory


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def agent(source: str, name: str = "test_agent") -> AgentSource:
    return AgentSource.from_string(source, name=name)


FULLY_INSTRUMENTED = """\
def run():
    awcp_hooks.task_started(task_id, agent_name)
    awcp_hooks.llm_call(model, prompt_tokens)
    awcp_hooks.token_usage(100, 50, 150)
    awcp_hooks.tool_call(tool_name, args)
    awcp_hooks.web_search(query, results_count)
    awcp_hooks.synthesize(input_count, output_length)
    awcp_hooks.budget_warn(0.8, limit, agent_name)
    awcp_hooks.budget_exhausted(1.0, agent_name)
    awcp_hooks.task_completed(task_id, result)
    awcp_hooks.observability(checkpoint_name, data)
    awcp_hooks.policy_check(policy_name, decision)
    awcp_hooks.approval_request(action, risk_level)
    awcp_hooks.feature_flag(flag_name, enabled)
    awcp_hooks.recovery(attempt_number, reason)
    awcp_hooks.degradation(from_mode, to_mode, reason)

def on_error():
    awcp_hooks.task_failed(task_id, error)
"""

NO_HOOKS = "x = 1\nresult = x + 2\n"


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class TestHookDetectorInterface:
    def test_is_hook_detector(self) -> None:
        assert isinstance(RuleBasedHookDetector(), HookDetector)

    def test_returns_hook_detection_result(self) -> None:
        result = RuleBasedHookDetector().detect(agent(NO_HOOKS))
        assert isinstance(result, HookDetectionResult)


# ---------------------------------------------------------------------------
# Single-agent detection
# ---------------------------------------------------------------------------

class TestDetectSingleAgent:
    def test_fully_instrumented_agent_has_no_missing_hooks(self) -> None:
        result = RuleBasedHookDetector().detect(agent(FULLY_INSTRUMENTED))
        assert result.is_fully_instrumented

    def test_fully_instrumented_agent_has_all_categories_present(self) -> None:
        result = RuleBasedHookDetector().detect(agent(FULLY_INSTRUMENTED))
        present_cats = {h.category for h in result.present_hooks}
        assert present_cats == set(HookCategory)

    def test_no_hooks_agent_has_all_missing(self) -> None:
        result = RuleBasedHookDetector().detect(agent(NO_HOOKS))
        assert not result.is_fully_instrumented
        missing_cats = {h.category for h in result.missing_hooks}
        assert missing_cats == set(HookCategory)

    def test_no_hooks_agent_has_no_present_hooks(self) -> None:
        result = RuleBasedHookDetector().detect(agent(NO_HOOKS))
        assert result.present_hooks == []

    def test_agent_name_preserved_in_result(self) -> None:
        result = RuleBasedHookDetector().detect(agent(NO_HOOKS, name="my_bot"))
        assert result.agent.agent_name == "my_bot"

    def test_present_hooks_have_line_numbers(self) -> None:
        result = RuleBasedHookDetector().detect(agent(FULLY_INSTRUMENTED))
        for hook in result.present_hooks:
            assert hook.line_number is not None

    def test_missing_hooks_have_no_line_numbers(self) -> None:
        result = RuleBasedHookDetector().detect(agent(NO_HOOKS))
        for hook in result.missing_hooks:
            assert hook.line_number is None

    def test_partial_instrumentation(self) -> None:
        source = "awcp_hooks.task_started(task_id, agent_name)"
        result = RuleBasedHookDetector().detect(agent(source))
        present_cats = {h.category for h in result.present_hooks}
        missing_cats = {h.category for h in result.missing_hooks}
        assert HookCategory.TASK_STARTED in present_cats
        assert HookCategory.TASK_FAILED in missing_cats
        assert HookCategory.LLM_CALL in missing_cats

    def test_syntax_error_propagates(self) -> None:
        with pytest.raises(SyntaxError):
            RuleBasedHookDetector().detect(agent("def broken("))


# ---------------------------------------------------------------------------
# Batch detection via detect_all
# ---------------------------------------------------------------------------

class TestDetectAll:
    def _make_scan_result(self, agents: List[AgentSource]) -> RepositoryScanResult:
        from pathlib import Path
        return RepositoryScanResult(target=Path("."), agents=agents)

    def test_returns_one_result_per_agent(self) -> None:
        scan = self._make_scan_result([agent(NO_HOOKS, "a"), agent(NO_HOOKS, "b")])
        results = RuleBasedHookDetector().detect_all(scan)
        assert len(results) == 2

    def test_empty_scan_returns_empty_list(self) -> None:
        scan = self._make_scan_result([])
        results = RuleBasedHookDetector().detect_all(scan)
        assert results == []

    def test_skips_unparseable_agents(self) -> None:
        good = agent("awcp_hooks.task_started(t, a)", "good")
        bad = agent("def broken(", "bad")
        scan = self._make_scan_result([good, bad])
        results = RuleBasedHookDetector().detect_all(scan)
        assert len(results) == 1
        assert results[0].agent.agent_name == "good"

    def test_mixed_agents_produce_correct_results(self) -> None:
        fully = agent(FULLY_INSTRUMENTED, "full")
        empty = agent(NO_HOOKS, "empty")
        scan = self._make_scan_result([fully, empty])
        results = RuleBasedHookDetector().detect_all(scan)

        by_name = {r.agent.agent_name: r for r in results}
        assert by_name["full"].is_fully_instrumented
        assert not by_name["empty"].is_fully_instrumented


# ---------------------------------------------------------------------------
# Custom rule injection (Open/Closed)
# ---------------------------------------------------------------------------

class TestCustomRuleInjection:
    def _make_stub_rule(self, category: HookCategory, will_detect: bool) -> DetectionRule:
        hook = GovernanceHook(
            category=category,
            name="stub_hook",
            description="stub",
        )
        found_hook = GovernanceHook(
            category=category,
            name="stub_hook",
            description="stub",
            line_number=1,
        )
        rule = MagicMock(spec=DetectionRule)
        rule.category = category
        rule.required_hooks = [hook]
        rule.detect.return_value = [found_hook] if will_detect else []
        return rule

    def test_custom_rule_is_used(self) -> None:
        stub = self._make_stub_rule(HookCategory.TASK_STARTED, will_detect=True)
        detector = RuleBasedHookDetector(rules=[stub])
        result = detector.detect(agent(NO_HOOKS))

        assert len(result.present_hooks) == 1
        assert result.present_hooks[0].category == HookCategory.TASK_STARTED

    def test_custom_rule_missing_adds_to_missing(self) -> None:
        stub = self._make_stub_rule(HookCategory.TASK_FAILED, will_detect=False)
        detector = RuleBasedHookDetector(rules=[stub])
        result = detector.detect(agent(NO_HOOKS))

        assert len(result.missing_hooks) == 1
        assert result.missing_hooks[0].category == HookCategory.TASK_FAILED

    def test_empty_rules_list_detects_nothing(self) -> None:
        detector = RuleBasedHookDetector(rules=[])
        result = detector.detect(agent(FULLY_INSTRUMENTED))
        assert result.present_hooks == []
        assert result.missing_hooks == []

    def test_multiple_custom_rules_aggregated(self) -> None:
        started_rule = self._make_stub_rule(HookCategory.TASK_STARTED, will_detect=True)
        failed_rule = self._make_stub_rule(HookCategory.TASK_FAILED, will_detect=False)
        detector = RuleBasedHookDetector(rules=[started_rule, failed_rule])
        result = detector.detect(agent(NO_HOOKS))

        assert len(result.present_hooks) == 1
        assert len(result.missing_hooks) == 1
