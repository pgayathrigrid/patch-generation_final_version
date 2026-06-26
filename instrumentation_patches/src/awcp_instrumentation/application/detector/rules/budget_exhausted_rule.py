from __future__ import annotations

import ast
from typing import List

from awcp_instrumentation.application.detector.rules.base_rule import BaseDetectionRule
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory

_HOOK = GovernanceHook(
    category=HookCategory.BUDGET_EXHAUSTED,
    name="awcp_hooks.budget_exhausted",
    description="AWCP lifecycle hook: emitted when the agent exhausts its allocated token or cost budget",
    signature="awcp_hooks.budget_exhausted(used_ratio, agent_name, **context)",
    line_number=None,
)

_KEYWORDS = [
    "awcp_hooks.budget_exhausted", "awcp.budget_exhausted",
    "on_budget_exhausted", "budget_exhausted_hook",
    "hooks.budget_exhausted", "lifecycle.budget_exhausted",
    "emit_budget_exhausted", "budget_exhausted",
    "on_budget_exceeded", "budget_exceeded",
]


class BudgetExhaustedDetectionRule(BaseDetectionRule):
    @property
    def category(self) -> HookCategory:
        return HookCategory.BUDGET_EXHAUSTED

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
