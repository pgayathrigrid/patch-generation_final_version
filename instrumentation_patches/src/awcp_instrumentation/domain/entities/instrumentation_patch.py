from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook


@dataclass
class InstrumentationPatch:
    """
    A generated patch that adds missing governance hooks to an agent.

    Attributes:
        original_agent:  The unmodified agent source.
        patched_source:  Full Python source after instrumentation.
        inserted_hooks:  The hooks that were added by this patch.
        patch_diff:      Unified diff string for auditing / review.
    """

    original_agent: AgentSource
    patched_source: str
    inserted_hooks: List[GovernanceHook] = field(default_factory=list)
    patch_diff: str = field(default="")

    @property
    def hook_count(self) -> int:
        """Number of hooks added by this patch."""
        return len(self.inserted_hooks)

    @property
    def is_empty(self) -> bool:
        """True when no hooks were needed (agent was already fully instrumented)."""
        return self.hook_count == 0
