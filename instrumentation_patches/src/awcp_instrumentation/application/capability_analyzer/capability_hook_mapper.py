"""
Maps a frozenset of ``AgentCapability`` values to the required AWCP hook
categories for that agent.

Design principles:
- TASK_STARTED, TASK_COMPLETED, TASK_FAILED are *always* required.
- Each additional capability unlocks its own hook subset.
- If no capabilities are detected at all, every hook category is required
  (safe fallback — instrumentation-complete is better than silently under-
  instrumented when analysis cannot determine what the agent does).
"""
from __future__ import annotations

from typing import FrozenSet

from awcp_instrumentation.domain.enums.agent_capability import AgentCapability
from awcp_instrumentation.domain.enums.hook_category import HookCategory

_ALWAYS_REQUIRED: FrozenSet[HookCategory] = frozenset(
    {
        HookCategory.TASK_STARTED,
        HookCategory.TASK_COMPLETED,
        HookCategory.TASK_FAILED,
    }
)

_CAPABILITY_HOOKS: dict[AgentCapability, FrozenSet[HookCategory]] = {
    AgentCapability.LLM_AGENT: frozenset(
        {
            HookCategory.LLM_CALL,
            HookCategory.TOKEN_USAGE,
            HookCategory.BUDGET_WARN,
            HookCategory.BUDGET_EXHAUSTED,
        }
    ),
    AgentCapability.TOOL_AGENT: frozenset({HookCategory.TOOL_CALL}),
    AgentCapability.SEARCH_AGENT: frozenset({HookCategory.WEB_SEARCH}),
    AgentCapability.SYNTHESIS_AGENT: frozenset({HookCategory.SYNTHESIZE}),
    AgentCapability.OBSERVABLE_AGENT: frozenset({HookCategory.OBSERVABILITY}),
    AgentCapability.POLICY_AGENT: frozenset({HookCategory.POLICY}),
    AgentCapability.APPROVAL_AGENT: frozenset({HookCategory.APPROVAL}),
    AgentCapability.FEATURE_FLAG_AGENT: frozenset({HookCategory.FEATURE_FLAG}),
    AgentCapability.RECOVERY_AGENT: frozenset({HookCategory.RECOVERY}),
    AgentCapability.DEGRADATION_AGENT: frozenset({HookCategory.DEGRADATION}),
}


class CapabilityHookMapper:
    """
    Pure-function utility that maps a set of inferred capabilities to the
    minimal required AWCP hook category set.

    There is no state — all methods are static.  Inject (or mock) at the
    call site if you need to swap the mapping in tests.
    """

    @staticmethod
    def required_hooks(
        capabilities: FrozenSet[AgentCapability],
    ) -> FrozenSet[HookCategory]:
        """
        Return the frozenset of ``HookCategory`` values that are required for
        an agent with the given *capabilities*.

        If *capabilities* is empty (analysis could not determine what the
        agent does), all hook categories are returned so that the gap
        reporter flags everything and avoids silent under-instrumentation.
        """
        if not capabilities:
            return frozenset(HookCategory)

        result: set[HookCategory] = set(_ALWAYS_REQUIRED)
        for cap in capabilities:
            result.update(_CAPABILITY_HOOKS.get(cap, frozenset()))
        return frozenset(result)

    @staticmethod
    def all_hooks() -> FrozenSet[HookCategory]:
        """Convenience: return every defined AWCP hook category."""
        return frozenset(HookCategory)
