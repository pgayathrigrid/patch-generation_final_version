"""Tests for PromptBuilder."""

import pytest

from awcp_instrumentation.application.gap_reporter.models import (
    GovernanceGap,
    GovernanceRecommendation,
    GovernanceRisk,
    RiskSeverity,
)
from awcp_instrumentation.application.generator.prompt_builder import PromptBuilder
from awcp_instrumentation.application.generator.llm_interface import LlmRequest
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_gap(category: HookCategory = HookCategory.TASK_STARTED) -> GovernanceGap:
    hook = GovernanceHook(
        category=category,
        name="log_decision",
        description="Logs significant agent decisions",
    )
    risk = GovernanceRisk(severity=RiskSeverity.HIGH, description="no logs", impact="blind")
    rec = GovernanceRecommendation(
        action="Add structured logging",
        rationale="Required for auditability",
        instrumentation_hint="Insert log_decision() at decision points",
        priority=1,
    )
    return GovernanceGap(hook=hook, risk=risk, recommendation=rec)


def make_agent(source: str = "def run():\n    pass") -> AgentSource:
    return AgentSource.from_string(source, name="my_agent")


# ---------------------------------------------------------------------------
# LlmRequest structure
# ---------------------------------------------------------------------------

class TestPromptBuilderOutput:
    def test_returns_llm_request(self) -> None:
        request = PromptBuilder().build(make_gap(), make_agent())
        assert isinstance(request, LlmRequest)

    def test_system_prompt_is_non_empty(self) -> None:
        request = PromptBuilder().build(make_gap(), make_agent())
        assert len(request.system_prompt) > 100

    def test_user_prompt_is_non_empty(self) -> None:
        request = PromptBuilder().build(make_gap(), make_agent())
        assert len(request.prompt) > 50

    def test_default_max_tokens(self) -> None:
        request = PromptBuilder().build(make_gap(), make_agent())
        assert request.max_tokens == 2048

    def test_default_temperature(self) -> None:
        request = PromptBuilder().build(make_gap(), make_agent())
        assert request.temperature == 0.2

    def test_default_model_is_none(self) -> None:
        request = PromptBuilder().build(make_gap(), make_agent())
        assert request.model is None

    def test_custom_max_tokens(self) -> None:
        request = PromptBuilder(max_tokens=512).build(make_gap(), make_agent())
        assert request.max_tokens == 512

    def test_custom_temperature(self) -> None:
        request = PromptBuilder(temperature=0.7).build(make_gap(), make_agent())
        assert request.temperature == 0.7

    def test_custom_model_in_request(self) -> None:
        request = PromptBuilder(model="claude-sonnet-4-6").build(make_gap(), make_agent())
        assert request.model == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# User prompt content
# ---------------------------------------------------------------------------

class TestUserPromptContent:
    def _build(self, gap=None, agent=None) -> str:
        return PromptBuilder().build(
            gap or make_gap(),
            agent or make_agent()
        ).prompt

    def test_contains_source_code(self) -> None:
        agent = make_agent("def run():\n    return 42\n")
        prompt = self._build(agent=agent)
        assert "def run():" in prompt
        assert "return 42" in prompt

    def test_contains_category(self) -> None:
        prompt = self._build(make_gap(HookCategory.TASK_FAILED))
        assert "task_failed" in prompt.lower()

    def test_contains_hook_name(self) -> None:
        prompt = self._build()
        assert "log_decision" in prompt

    def test_contains_hook_description(self) -> None:
        prompt = self._build()
        assert "Logs significant agent decisions" in prompt

    def test_contains_action(self) -> None:
        prompt = self._build()
        assert "Add structured logging" in prompt

    def test_contains_instrumentation_hint(self) -> None:
        prompt = self._build()
        assert "Insert log_decision() at decision points" in prompt

    def test_contains_rationale(self) -> None:
        prompt = self._build()
        assert "Required for auditability" in prompt

    @pytest.mark.parametrize("category", list(HookCategory))
    def test_category_name_in_prompt(self, category: HookCategory) -> None:
        prompt = self._build(make_gap(category))
        assert category.value in prompt


# ---------------------------------------------------------------------------
# System prompt content
# ---------------------------------------------------------------------------

class TestSystemPromptContent:
    def _system(self) -> str:
        return PromptBuilder().build(make_gap(), make_agent()).system_prompt

    def test_mentions_json(self) -> None:
        assert "JSON" in self._system()

    def test_mentions_insertion_locations(self) -> None:
        system = self._system()
        assert "after_imports" in system
        assert "before_function_body" in system

    def test_instructs_not_to_add_unrelated_code(self) -> None:
        system = self._system()
        assert "ONLY" in system or "only" in system

    def test_instructs_no_markdown_in_response(self) -> None:
        system = self._system()
        assert "markdown" in system.lower() or "JSON" in system
