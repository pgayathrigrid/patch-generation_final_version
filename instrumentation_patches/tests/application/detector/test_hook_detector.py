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
from awcp.agent_hooks import get_manager
from awcp.agent_hooks.types import HookType

def run():
    get_manager().dispatch(HookType.TASK_STARTED, agent_id=agent_id, task_id=task_id)
    get_manager().dispatch(HookType.LLM_CALL, agent_id=agent_id, task_id=task_id, model=model)
    get_manager().dispatch(HookType.TOKEN_USAGE, agent_id=agent_id, task_id=task_id)
    get_manager().dispatch(HookType.TOOL_CALL, agent_id=agent_id, task_id=task_id, tool_name=tool_name, action=action)
    get_manager().dispatch(HookType.WEB_SEARCH, agent_id=agent_id, task_id=task_id, query=query)
    get_manager().dispatch(HookType.SYNTHESIZE, agent_id=agent_id, task_id=task_id)
    get_manager().dispatch(HookType.BUDGET_WARN, agent_id=agent_id, task_id=task_id)
    get_manager().dispatch(HookType.BUDGET_EXHAUSTED, agent_id=agent_id, task_id=task_id)
    get_manager().dispatch(HookType.TASK_COMPLETED, agent_id=agent_id, task_id=task_id)
    get_manager().dispatch(HookType.STEP, agent_id=agent_id, task_id=task_id, checkpoint=checkpoint_name)
    get_manager().dispatch(HookType.GATE_EVALUATED, agent_id=agent_id, task_id=task_id, action=action, decision=decision, scope=action, write=True, mode='policy')
    get_manager().dispatch(HookType.APPROVAL_REQUIRED, agent_id=agent_id, task_id=task_id, action=action, risk=risk_level)
    get_manager().dispatch(HookType.SIGNAL_RECEIVED, agent_id=agent_id, task_id=task_id, flag_name=flag_name, enabled=enabled)

def on_error():
    get_manager().dispatch(HookType.TASK_FAILED, agent_id=agent_id, task_id=task_id, error=str(error))
    get_manager().dispatch(HookType.SIGNAL_RECEIVED, agent_id=agent_id, task_id=task_id, attempt=attempt_number, reason=reason)
    get_manager().dispatch(HookType.AUTONOMY_DEGRADED, agent_id=agent_id, task_id=task_id, from_mode=from_mode, to_mode=to_mode)
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
        source = "get_manager().dispatch(HookType.TASK_STARTED, agent_id=agent_id, task_id=task_id)"
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
        good = agent("get_manager().dispatch(HookType.TASK_STARTED, agent_id=agent_id, task_id=task_id)", "good")
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
