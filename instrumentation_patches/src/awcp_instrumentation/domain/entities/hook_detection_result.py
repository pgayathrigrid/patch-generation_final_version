from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory


@dataclass
class HookDetectionResult:
    """
    Output of the hook detector for a single agent.

    Attributes:
        agent:          The agent that was analysed.
        present_hooks:  Hooks already found in the agent source.
        missing_hooks:  Hooks required by policy but absent from the agent.
    """

    agent: AgentSource
    present_hooks: List[GovernanceHook] = field(default_factory=list)
    missing_hooks: List[GovernanceHook] = field(default_factory=list)

    @property
    def is_fully_instrumented(self) -> bool:
        """True when no governance hooks are missing."""
        return len(self.missing_hooks) == 0

    @property
    def missing_categories(self) -> List[HookCategory]:
        """Distinct hook categories that are missing."""
        return list({h.category for h in self.missing_hooks})

    @property
    def present_categories(self) -> List[HookCategory]:
        """Distinct hook categories already present."""
        return list({h.category for h in self.present_hooks})
