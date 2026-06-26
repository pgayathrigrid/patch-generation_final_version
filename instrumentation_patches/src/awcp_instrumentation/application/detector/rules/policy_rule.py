from __future__ import annotations

import ast
from typing import List

from awcp_instrumentation.application.detector.rules.base_rule import BaseDetectionRule
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory

_HOOK = GovernanceHook(
    category=HookCategory.POLICY,
    name="awcp_hooks.policy_check",
    description="AWCP policy hook: emitted when the agent evaluates a governance policy gate",
    signature="awcp_hooks.policy_check(policy_name, decision, **context)",
    line_number=None,
)

_KEYWORDS = [
    "awcp_hooks.policy_check", "awcp.policy_check",
    "policy_gate", "check_policy", "gate_check",
    "policy_hook", "policy_evaluated", "policy_eval",
    "hooks.policy_check", "lifecycle.policy",
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
        dec = self._first_matching_decorator(self._decorator_sites(tree), _KEYWORDS)
        if dec:
            return [self._found(_HOOK, dec[1])]
        return []
