from __future__ import annotations

import ast
from typing import List

from awcp_instrumentation.application.detector.rules.base_rule import BaseDetectionRule
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory

_HOOK = GovernanceHook(
    category=HookCategory.TASK_COMPLETED,
    name="awcp_hooks.task_completed",
    description="AWCP lifecycle hook: emitted when an agent task finishes successfully",
    signature="awcp_hooks.task_completed(task_id, result, **context)",
    line_number=None,
)

_KEYWORDS = [
    "task_completed", "task_complete", "on_task_complete", "on_task_completed",
    "awcp_hooks.task_completed", "awcp.task_completed",
    "emit_task_completed", "hook.task_complete",
    "hooks.task_completed", "lifecycle.task_completed",
]


class TaskCompletedDetectionRule(BaseDetectionRule):
    @property
    def category(self) -> HookCategory:
        return HookCategory.TASK_COMPLETED

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
