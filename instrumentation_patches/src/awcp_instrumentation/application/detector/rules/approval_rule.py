from __future__ import annotations

import ast
from typing import List

from awcp_instrumentation.application.detector.rules.base_rule import BaseDetectionRule
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory

_HOOK = GovernanceHook(
    category=HookCategory.APPROVAL,
    name="HookType.APPROVAL_REQUIRED",
    description="AWCP approval hook: emitted when the agent requests human approval for a high-risk action",
    signature="get_manager().dispatch(HookType.APPROVAL_REQUIRED, agent_id=agent_id, task_id=task_id, action=action, risk=risk_level)",
    line_number=None,
)

_KEYWORDS = [
    "request_approval", "needs_approval", "approval_hook",
    "human_approval", "require_approval", "approval_required",
    "hooktype.approval_required",
    "awcp_hooks.approval_request",
    "hooks.approval",
]


class ApprovalDetectionRule(BaseDetectionRule):
    @property
    def category(self) -> HookCategory:
        return HookCategory.APPROVAL

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
