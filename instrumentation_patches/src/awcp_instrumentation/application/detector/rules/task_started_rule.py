from __future__ import annotations

import ast
from typing import List

from awcp_instrumentation.application.detector.rules.base_rule import BaseDetectionRule
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory

_HOOK = GovernanceHook(
    category=HookCategory.TASK_STARTED,
    name="awcp_hooks.task_started",
    description="AWCP lifecycle hook: emitted when an agent task begins execution",
    signature="awcp_hooks.task_started(task_id, agent_name, **context)",
    line_number=None,
)

_KEYWORDS = [
    "task_started", "task_start", "on_task_start", "on_task_started",
    "awcp_hooks.task_started", "awcp.task_started",
    "emit_task_started", "hook.task_start",
    "hooks.task_started", "lifecycle.task_started",
]


class TaskStartedDetectionRule(BaseDetectionRule):
    @property
    def category(self) -> HookCategory:
        return HookCategory.TASK_STARTED

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
