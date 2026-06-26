"""Tests for CapabilityHookMapper."""
from __future__ import annotations

import pytest

from awcp_instrumentation.application.capability_analyzer.capability_hook_mapper import (
    CapabilityHookMapper,
)
from awcp_instrumentation.domain.enums.agent_capability import AgentCapability
from awcp_instrumentation.domain.enums.hook_category import HookCategory

_ALWAYS = frozenset(
    {HookCategory.TASK_STARTED, HookCategory.TASK_COMPLETED, HookCategory.TASK_FAILED}
)


class TestAlwaysRequired:
    def test_always_required_hooks_present_for_llm_agent(self):
        hooks = CapabilityHookMapper.required_hooks(frozenset({AgentCapability.LLM_AGENT}))
        assert _ALWAYS.issubset(hooks)

    def test_always_required_hooks_present_for_tool_agent(self):
        hooks = CapabilityHookMapper.required_hooks(frozenset({AgentCapability.TOOL_AGENT}))
        assert _ALWAYS.issubset(hooks)

    def test_always_required_hooks_present_for_search_agent(self):
        hooks = CapabilityHookMapper.required_hooks(frozenset({AgentCapability.SEARCH_AGENT}))
        assert _ALWAYS.issubset(hooks)

    def test_always_required_hooks_present_for_synthesis_agent(self):
        hooks = CapabilityHookMapper.required_hooks(frozenset({AgentCapability.SYNTHESIS_AGENT}))
        assert _ALWAYS.issubset(hooks)


class TestLlmCapabilityHooks:
    def _hooks(self):
        return CapabilityHookMapper.required_hooks(frozenset({AgentCapability.LLM_AGENT}))

    def test_llm_call_required(self):
        assert HookCategory.LLM_CALL in self._hooks()

    def test_token_usage_required(self):
        assert HookCategory.TOKEN_USAGE in self._hooks()

    def test_budget_warn_required(self):
        assert HookCategory.BUDGET_WARN in self._hooks()

    def test_budget_exhausted_required(self):
        assert HookCategory.BUDGET_EXHAUSTED in self._hooks()

    def test_tool_call_not_required_for_pure_llm_agent(self):
        assert HookCategory.TOOL_CALL not in self._hooks()

    def test_web_search_not_required_for_pure_llm_agent(self):
        assert HookCategory.WEB_SEARCH not in self._hooks()

    def test_synthesize_not_required_for_pure_llm_agent(self):
        assert HookCategory.SYNTHESIZE not in self._hooks()


class TestToolCapabilityHooks:
    def _hooks(self):
        return CapabilityHookMapper.required_hooks(frozenset({AgentCapability.TOOL_AGENT}))

    def test_tool_call_required(self):
        assert HookCategory.TOOL_CALL in self._hooks()

    def test_llm_hooks_not_required_for_pure_tool_agent(self):
        assert HookCategory.LLM_CALL not in self._hooks()
        assert HookCategory.TOKEN_USAGE not in self._hooks()
        assert HookCategory.BUDGET_WARN not in self._hooks()
        assert HookCategory.BUDGET_EXHAUSTED not in self._hooks()


class TestSearchCapabilityHooks:
    def _hooks(self):
        return CapabilityHookMapper.required_hooks(frozenset({AgentCapability.SEARCH_AGENT}))

    def test_web_search_required(self):
        assert HookCategory.WEB_SEARCH in self._hooks()

    def test_tool_call_not_required_for_pure_search_agent(self):
        assert HookCategory.TOOL_CALL not in self._hooks()


class TestSynthesisCapabilityHooks:
    def _hooks(self):
        return CapabilityHookMapper.required_hooks(frozenset({AgentCapability.SYNTHESIS_AGENT}))

    def test_synthesize_required(self):
        assert HookCategory.SYNTHESIZE in self._hooks()

    def test_web_search_not_required_for_pure_synthesis_agent(self):
        assert HookCategory.WEB_SEARCH not in self._hooks()


class TestEmptyCapabilities:
    def test_all_hooks_required_when_capabilities_empty(self):
        hooks = CapabilityHookMapper.required_hooks(frozenset())
        assert hooks == frozenset(HookCategory)

    def test_all_hooks_method_returns_all_categories(self):
        assert CapabilityHookMapper.all_hooks() == frozenset(HookCategory)


class TestCombinedCapabilities:
    def test_llm_plus_tool_agent_has_all_their_hooks(self):
        hooks = CapabilityHookMapper.required_hooks(
            frozenset({AgentCapability.LLM_AGENT, AgentCapability.TOOL_AGENT})
        )
        assert HookCategory.LLM_CALL in hooks
        assert HookCategory.TOKEN_USAGE in hooks
        assert HookCategory.TOOL_CALL in hooks
        assert _ALWAYS.issubset(hooks)

    def test_search_plus_synthesis_agent(self):
        hooks = CapabilityHookMapper.required_hooks(
            frozenset({AgentCapability.SEARCH_AGENT, AgentCapability.SYNTHESIS_AGENT})
        )
        assert HookCategory.WEB_SEARCH in hooks
        assert HookCategory.SYNTHESIZE in hooks
        assert HookCategory.LLM_CALL not in hooks
        assert HookCategory.TOOL_CALL not in hooks

    def test_all_capabilities_returns_all_hooks(self):
        hooks = CapabilityHookMapper.required_hooks(frozenset(AgentCapability))
        assert hooks == frozenset(HookCategory)
