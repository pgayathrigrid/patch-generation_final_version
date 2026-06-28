from __future__ import annotations

import ast
from typing import List

from awcp_instrumentation.application.detector.rules.base_rule import BaseDetectionRule
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory

_HOOK = GovernanceHook(
    category=HookCategory.DEGRADATION,
    name="HookType.AUTONOMY_DEGRADED",
    description="AWCP degradation hook: emitted when the agent's autonomy mode is stepped down by the control plane",
    signature="get_manager().dispatch(HookType.AUTONOMY_DEGRADED, agent_id=agent_id, task_id=task_id, from_mode=from_mode, to_mode=to_mode)",
    line_number=None,
)

_KEYWORDS = [
    "autonomy_degraded", "degradation_hook", "on_degradation",
    "degrade_hook", "autonomy_step_down", "degrade_autonomy",
    "hooktype.autonomy_degraded",
    "awcp_hooks.degradation",
    "hooks.degradation",
]


class DegradationDetectionRule(BaseDetectionRule):
    @property
    def category(self) -> HookCategory:
        return HookCategory.DEGRADATION

    @property
    def required_hooks(self) -> List[GovernanceHook]:
        return [_HOOK]

    def detect(self, tree: ast.Module, agent: AgentSource) -> List[GovernanceHook]:
        match = self._first_matching_call(self._call_sites(tree), _KEYWORDS)
        if match:
            return [self._found(_HOOK, match[1])]
        match = self._first_matching_call(self._attribute_accesses(tree), _KEYWORDS)
        if match:
            return [self._found(_HOOK, match[1])]
        dec = self._first_matching_decorator(self._decorator_sites(tree), _KEYWORDS)
        if dec:
            return [self._found(_HOOK, dec[1])]
        return []
