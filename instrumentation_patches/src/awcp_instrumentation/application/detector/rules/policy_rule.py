from __future__ import annotations

import ast
from typing import List

from awcp_instrumentation.application.detector.rules.base_rule import BaseDetectionRule
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory

_HOOK = GovernanceHook(
    category=HookCategory.POLICY,
    name="HookType.GATE_EVALUATED",
    description="AWCP policy hook: emitted when the agent passes through the OPA governance gate",
    signature="get_manager().dispatch(HookType.GATE_EVALUATED, agent_id=agent_id, task_id=task_id, action=action, decision=decision, scope=action, write=True, mode='policy')",
    line_number=None,
)

_KEYWORDS = [
    "policy_gate", "check_policy", "gate_check",
    "policy_hook", "policy_evaluated", "policy_eval",
    "hooktype.gate_evaluated",
    "awcp_hooks.policy_check",
    "hooks.policy_check",
]


class PolicyDetectionRule(BaseDetectionRule):
    @property
    def category(self) -> HookCategory:
        return HookCategory.POLICY

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
