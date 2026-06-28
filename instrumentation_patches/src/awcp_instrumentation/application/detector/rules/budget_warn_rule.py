from __future__ import annotations

import ast
from typing import List

from awcp_instrumentation.application.detector.rules.base_rule import BaseDetectionRule
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory

_HOOK = GovernanceHook(
    category=HookCategory.BUDGET_WARN,
    name="HookType.BUDGET_WARN",
    description="AWCP lifecycle hook: emitted when token/cost usage approaches the configured threshold",
    signature="get_manager().dispatch(HookType.BUDGET_WARN, agent_id=agent_id, task_id=task_id)",
    line_number=None,
)

_KEYWORDS = [
    "on_budget_warn", "budget_warn_hook", "budget_warning",
    "on_budget_warning", "budget_warn",
    "hooktype.budget_warn",
    "awcp_hooks.budget_warn",
    "hooks.budget_warn", "emit_budget_warn",
]


class BudgetWarnDetectionRule(BaseDetectionRule):
    @property
    def category(self) -> HookCategory:
        return HookCategory.BUDGET_WARN

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
