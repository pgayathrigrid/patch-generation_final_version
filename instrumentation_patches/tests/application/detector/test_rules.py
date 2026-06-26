"""Tests for all ten AWCP lifecycle DetectionRule implementations."""

import ast
from typing import List

import pytest

from awcp_instrumentation.application.detector.rules import (
    TaskStartedDetectionRule,
    TaskCompletedDetectionRule,
    TaskFailedDetectionRule,
    LlmCallDetectionRule,
    SynthesizeDetectionRule,
    ToolCallDetectionRule,
    WebSearchDetectionRule,
    TokenUsageDetectionRule,
    BudgetWarnDetectionRule,
    BudgetExhaustedDetectionRule,
)
from awcp_instrumentation.application.detector.interface import DetectionRule
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse(source: str) -> ast.Module:
    return ast.parse(source)


def agent(source: str = "pass") -> AgentSource:
    return AgentSource.from_string(source)


def detect(rule: DetectionRule, source: str) -> List[GovernanceHook]:
    return rule.detect(parse(source), agent(source))


def assert_found(rule: DetectionRule, source: str) -> GovernanceHook:
    results = detect(rule, source)
    assert results, f"{rule.__class__.__name__} should detect a hook in:\n{source}"
    hook = results[0]
    assert hook.line_number is not None, "Detected hook must have a line_number"
    assert hook.category == rule.category
    return hook


def assert_not_found(rule: DetectionRule, source: str) -> None:
    results = detect(rule, source)
    assert not results, (
        f"{rule.__class__.__name__} should NOT detect a hook in:\n{source}\n"
        f"But found: {results}"
    )


# ---------------------------------------------------------------------------
# Shared contract tests — apply to every rule
# ---------------------------------------------------------------------------

ALL_RULES = [
    TaskStartedDetectionRule(),
    TaskCompletedDetectionRule(),
    TaskFailedDetectionRule(),
    LlmCallDetectionRule(),
    SynthesizeDetectionRule(),
    ToolCallDetectionRule(),
    WebSearchDetectionRule(),
    TokenUsageDetectionRule(),
    BudgetWarnDetectionRule(),
    BudgetExhaustedDetectionRule(),
]


class TestDetectionRuleContract:
    @pytest.mark.parametrize("rule", ALL_RULES, ids=lambda r: r.__class__.__name__)
    def test_category_matches_enum(self, rule: DetectionRule) -> None:
        assert isinstance(rule.category, HookCategory)

    @pytest.mark.parametrize("rule", ALL_RULES, ids=lambda r: r.__class__.__name__)
    def test_required_hooks_non_empty(self, rule: DetectionRule) -> None:
        assert len(rule.required_hooks) > 0

    @pytest.mark.parametrize("rule", ALL_RULES, ids=lambda r: r.__class__.__name__)
    def test_required_hooks_have_no_line_number(self, rule: DetectionRule) -> None:
        for hook in rule.required_hooks:
            assert hook.line_number is None, (
                "Required hooks are policy definitions — they must not have line_number set"
            )

    @pytest.mark.parametrize("rule", ALL_RULES, ids=lambda r: r.__class__.__name__)
    def test_required_hooks_category_matches_rule_category(self, rule: DetectionRule) -> None:
        for hook in rule.required_hooks:
            assert hook.category == rule.category

    @pytest.mark.parametrize("rule", ALL_RULES, ids=lambda r: r.__class__.__name__)
    def test_empty_source_returns_no_hooks(self, rule: DetectionRule) -> None:
        assert_not_found(rule, "")

    @pytest.mark.parametrize("rule", ALL_RULES, ids=lambda r: r.__class__.__name__)
    def test_unrelated_source_returns_no_hooks(self, rule: DetectionRule) -> None:
        source = "x = 1\ny = x + 2\nresult = str(y)"
        assert_not_found(rule, source)


# ---------------------------------------------------------------------------
# TaskStartedDetectionRule
# ---------------------------------------------------------------------------

class TestTaskStartedDetectionRule:
    rule = TaskStartedDetectionRule()

    def test_detects_awcp_hooks_task_started(self) -> None:
        assert_found(self.rule, "awcp_hooks.task_started(task_id, agent_name)")

    def test_detects_on_task_start(self) -> None:
        assert_found(self.rule, "on_task_start(task_id)")

    def test_detects_emit_task_started(self) -> None:
        assert_found(self.rule, "emit_task_started(task_id)")

    def test_detects_hooks_task_started(self) -> None:
        assert_found(self.rule, "hooks.task_started(task_id)")

    def test_not_detected_in_plain_code(self) -> None:
        assert_not_found(self.rule, "x = 1\nprint(x)")

    def test_line_number_is_correct(self) -> None:
        hook = assert_found(self.rule, "x = 1\nawcp_hooks.task_started(t)")
        assert hook.line_number == 2

    def test_category(self) -> None:
        assert self.rule.category == HookCategory.TASK_STARTED


# ---------------------------------------------------------------------------
# TaskCompletedDetectionRule
# ---------------------------------------------------------------------------

class TestTaskCompletedDetectionRule:
    rule = TaskCompletedDetectionRule()

    def test_detects_awcp_hooks_task_completed(self) -> None:
        assert_found(self.rule, "awcp_hooks.task_completed(task_id, result)")

    def test_detects_on_task_complete(self) -> None:
        assert_found(self.rule, "on_task_complete(task_id)")

    def test_detects_emit_task_completed(self) -> None:
        assert_found(self.rule, "emit_task_completed(task_id)")

    def test_not_detected_in_plain_code(self) -> None:
        assert_not_found(self.rule, "x = compute()")

    def test_line_number_is_correct(self) -> None:
        hook = assert_found(self.rule, "pass\nawcp_hooks.task_completed(t, r)")
        assert hook.line_number == 2

    def test_category(self) -> None:
        assert self.rule.category == HookCategory.TASK_COMPLETED


# ---------------------------------------------------------------------------
# TaskFailedDetectionRule
# ---------------------------------------------------------------------------

class TestTaskFailedDetectionRule:
    rule = TaskFailedDetectionRule()

    def test_detects_awcp_hooks_task_failed(self) -> None:
        assert_found(self.rule, "awcp_hooks.task_failed(task_id, error)")

    def test_detects_on_task_fail(self) -> None:
        assert_found(self.rule, "on_task_fail(task_id, exc)")

    def test_detects_emit_task_failed(self) -> None:
        assert_found(self.rule, "emit_task_failed(task_id)")

    def test_not_detected_in_plain_code(self) -> None:
        assert_not_found(self.rule, "x = compute()")

    def test_line_number_is_correct(self) -> None:
        hook = assert_found(self.rule, "x = 1\nawcp_hooks.task_failed(t, e)")
        assert hook.line_number == 2

    def test_category(self) -> None:
        assert self.rule.category == HookCategory.TASK_FAILED


# ---------------------------------------------------------------------------
# LlmCallDetectionRule
# ---------------------------------------------------------------------------

class TestLlmCallDetectionRule:
    rule = LlmCallDetectionRule()

    def test_detects_awcp_hooks_llm_call(self) -> None:
        assert_found(self.rule, "awcp_hooks.llm_call(model, prompt_tokens)")

    def test_detects_on_llm_call(self) -> None:
        assert_found(self.rule, "on_llm_call(model, prompt)")

    def test_detects_before_llm_call(self) -> None:
        assert_found(self.rule, "before_llm_call(model)")

    def test_detects_on_llm_start(self) -> None:
        assert_found(self.rule, "on_llm_start(model, messages)")

    def test_not_detected_in_plain_code(self) -> None:
        assert_not_found(self.rule, "result = compute(data)")

    def test_line_number_is_correct(self) -> None:
        hook = assert_found(self.rule, "x = 1\nawcp_hooks.llm_call(m, p)")
        assert hook.line_number == 2

    def test_category(self) -> None:
        assert self.rule.category == HookCategory.LLM_CALL


# ---------------------------------------------------------------------------
# SynthesizeDetectionRule
# ---------------------------------------------------------------------------

class TestSynthesizeDetectionRule:
    rule = SynthesizeDetectionRule()

    def test_detects_awcp_hooks_synthesize(self) -> None:
        assert_found(self.rule, "awcp_hooks.synthesize(input_count, output_length)")

    def test_detects_on_synthesize(self) -> None:
        assert_found(self.rule, "on_synthesize(inputs)")

    def test_detects_synthesis_hook(self) -> None:
        assert_found(self.rule, "synthesis_hook(data)")

    def test_not_detected_in_plain_code(self) -> None:
        assert_not_found(self.rule, "x = compute()")

    def test_line_number_is_correct(self) -> None:
        hook = assert_found(self.rule, "pass\nawcp_hooks.synthesize(3, 100)")
        assert hook.line_number == 2

    def test_category(self) -> None:
        assert self.rule.category == HookCategory.SYNTHESIZE


# ---------------------------------------------------------------------------
# ToolCallDetectionRule
# ---------------------------------------------------------------------------

class TestToolCallDetectionRule:
    rule = ToolCallDetectionRule()

    def test_detects_awcp_hooks_tool_call(self) -> None:
        assert_found(self.rule, "awcp_hooks.tool_call(tool_name, args)")

    def test_detects_on_tool_call(self) -> None:
        assert_found(self.rule, "on_tool_call(tool_name)")

    def test_detects_on_tool_start(self) -> None:
        assert_found(self.rule, "on_tool_start(tool)")

    def test_not_detected_in_plain_code(self) -> None:
        assert_not_found(self.rule, "x = compute()")

    def test_line_number_is_correct(self) -> None:
        hook = assert_found(self.rule, "x = 1\nawcp_hooks.tool_call(t, a)")
        assert hook.line_number == 2

    def test_category(self) -> None:
        assert self.rule.category == HookCategory.TOOL_CALL


# ---------------------------------------------------------------------------
# WebSearchDetectionRule
# ---------------------------------------------------------------------------

class TestWebSearchDetectionRule:
    rule = WebSearchDetectionRule()

    def test_detects_awcp_hooks_web_search(self) -> None:
        assert_found(self.rule, "awcp_hooks.web_search(query, results_count)")

    def test_detects_on_web_search(self) -> None:
        assert_found(self.rule, "on_web_search(query)")

    def test_detects_search_hook(self) -> None:
        assert_found(self.rule, "search_hook(query)")

    def test_not_detected_in_plain_code(self) -> None:
        assert_not_found(self.rule, "x = compute()")

    def test_line_number_is_correct(self) -> None:
        hook = assert_found(self.rule, "x = 1\nawcp_hooks.web_search(q, 5)")
        assert hook.line_number == 2

    def test_category(self) -> None:
        assert self.rule.category == HookCategory.WEB_SEARCH


# ---------------------------------------------------------------------------
# TokenUsageDetectionRule
# ---------------------------------------------------------------------------

class TestTokenUsageDetectionRule:
    rule = TokenUsageDetectionRule()

    def test_detects_awcp_hooks_token_usage(self) -> None:
        assert_found(self.rule, "awcp_hooks.token_usage(100, 50, 150)")

    def test_detects_track_tokens(self) -> None:
        assert_found(self.rule, "track_tokens(prompt=100, completion=50)")

    def test_detects_token_tracker(self) -> None:
        assert_found(self.rule, "token_tracker(usage)")

    def test_not_detected_in_plain_code(self) -> None:
        assert_not_found(self.rule, "x = compute()")

    def test_line_number_is_correct(self) -> None:
        hook = assert_found(self.rule, "x = 1\nawcp_hooks.token_usage(100, 50, 150)")
        assert hook.line_number == 2

    def test_category(self) -> None:
        assert self.rule.category == HookCategory.TOKEN_USAGE


# ---------------------------------------------------------------------------
# BudgetWarnDetectionRule
# ---------------------------------------------------------------------------

class TestBudgetWarnDetectionRule:
    rule = BudgetWarnDetectionRule()

    def test_detects_awcp_hooks_budget_warn(self) -> None:
        assert_found(self.rule, "awcp_hooks.budget_warn(0.8, limit, agent_name)")

    def test_detects_on_budget_warn(self) -> None:
        assert_found(self.rule, "on_budget_warn(ratio)")

    def test_detects_budget_warning(self) -> None:
        assert_found(self.rule, "budget_warning(used_ratio)")

    def test_not_detected_in_plain_code(self) -> None:
        assert_not_found(self.rule, "x = compute()")

    def test_line_number_is_correct(self) -> None:
        hook = assert_found(self.rule, "x = 1\nawcp_hooks.budget_warn(0.8, 1000, 'a')")
        assert hook.line_number == 2

    def test_category(self) -> None:
        assert self.rule.category == HookCategory.BUDGET_WARN


# ---------------------------------------------------------------------------
# BudgetExhaustedDetectionRule
# ---------------------------------------------------------------------------

class TestBudgetExhaustedDetectionRule:
    rule = BudgetExhaustedDetectionRule()

    def test_detects_awcp_hooks_budget_exhausted(self) -> None:
        assert_found(self.rule, "awcp_hooks.budget_exhausted(1.0, agent_name)")

    def test_detects_on_budget_exhausted(self) -> None:
        assert_found(self.rule, "on_budget_exhausted(ratio)")

    def test_detects_budget_exceeded(self) -> None:
        assert_found(self.rule, "budget_exceeded(used)")

    def test_detects_emit_budget_exhausted(self) -> None:
        assert_found(self.rule, "emit_budget_exhausted(agent)")

    def test_not_detected_in_plain_code(self) -> None:
        assert_not_found(self.rule, "x = compute()")

    def test_line_number_is_correct(self) -> None:
        hook = assert_found(self.rule, "x = 1\nawcp_hooks.budget_exhausted(1.0, 'a')")
        assert hook.line_number == 2

    def test_category(self) -> None:
        assert self.rule.category == HookCategory.BUDGET_EXHAUSTED
