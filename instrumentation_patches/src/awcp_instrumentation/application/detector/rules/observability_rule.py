from __future__ import annotations

import ast
from typing import List

from awcp_instrumentation.application.detector.rules.base_rule import BaseDetectionRule
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory

_HOOK = GovernanceHook(
    category=HookCategory.OBSERVABILITY,
    name="awcp_hooks.observability",
    description="AWCP observability hook: emitted at key checkpoints to expose intermediate agent state",
    signature="awcp_hooks.observability(checkpoint_name, data, **context)",
    line_number=None,
)

_KEYWORDS = [
    "awcp_hooks.observability", "awcp.observability",
    "emit_checkpoint", "log_checkpoint", "record_observation",
    "checkpoint_hook", "observe_hook", "observability_hook",
    "hooks.observability", "lifecycle.observability",
]


class ObservabilityDetectionRule(BaseDetectionRule):
    @property
    def category(self) -> HookCategory:
        return HookCategory.OBSERVABILITY

    @property
    def required_hooks(self) -> List[GovernanceHook]:
        return [_HOOK]

    def detect(self, tree: ast.Module, agent: AgentSource) -> List[GovernanceHook]:
        match = self._first_matching_call(self._call_sites(tree), _KEYWORDS)
        if match:
            return [self._found(_HOOK, match[1])]
        dec = self._first_matching_decorator(self._decorator_sites(tree), _KEYWORDS)
        if dec:
            return [self._found(_HOOK, dec[1])]
        return []
