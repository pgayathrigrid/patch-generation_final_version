from __future__ import annotations

import ast
from typing import List

from awcp_instrumentation.application.detector.rules.base_rule import BaseDetectionRule
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory

_HOOK = GovernanceHook(
    category=HookCategory.TASK_FAILED,
    name="HookType.TASK_FAILED",
    description="AWCP lifecycle hook: emitted when an agent task terminates with an error",
    signature="get_manager().dispatch(HookType.TASK_FAILED, agent_id=agent_id, task_id=task_id, error=str(error))",
    line_number=None,
)

_KEYWORDS = [
    "task_failed", "task_fail", "on_task_fail", "on_task_failed",
    "hooktype.task_failed",
    "awcp_hooks.task_failed",
    "emit_task_failed", "hooks.task_failed",
]


class TaskFailedDetectionRule(BaseDetectionRule):
    @property
    def category(self) -> HookCategory:
        return HookCategory.TASK_FAILED

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
