"""
Data models for the Capability Analysis stage.

``CapabilityAnalysisResult`` is the primary output — a frozen snapshot of
what capabilities were inferred from an agent's source code, the evidence
that triggered each capability, and the derived set of required AWCP hook
categories.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List

from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.enums.agent_capability import AgentCapability
from awcp_instrumentation.domain.enums.hook_category import HookCategory


@dataclass(frozen=True)
class CapabilityAnalysisResult:
    """
    Output of the Capability Analysis stage for a single agent.

    Attributes:
        agent:                   The agent that was analysed.
        capabilities:            Inferred ``AgentCapability`` values as a
                                 frozenset (empty when none detected).
        evidence:                Mapping from each detected capability to the
                                 list of AST signals that triggered it (import
                                 names, call-site strings, decorator names).
                                 Useful for explaining why a capability was
                                 inferred and for debugging false positives.
        required_hook_categories: The AWCP hook categories that are required
                                 for this agent given its detected capabilities.
                                 The gap reporter will only flag hooks in this
                                 set as missing.
    """

    agent: AgentSource
    capabilities: FrozenSet[AgentCapability]
    evidence: Dict[AgentCapability, List[str]]
    required_hook_categories: FrozenSet[HookCategory]

    @property
    def has_llm(self) -> bool:
        return AgentCapability.LLM_AGENT in self.capabilities

    @property
    def has_tools(self) -> bool:
        return AgentCapability.TOOL_AGENT in self.capabilities

    @property
    def has_search(self) -> bool:
        return AgentCapability.SEARCH_AGENT in self.capabilities

    @property
    def has_synthesis(self) -> bool:
        return AgentCapability.SYNTHESIS_AGENT in self.capabilities

    @property
    def capability_names(self) -> List[str]:
        return sorted(c.value for c in self.capabilities)

    @property
    def required_hook_names(self) -> List[str]:
        return sorted(h.value for h in self.required_hook_categories)
