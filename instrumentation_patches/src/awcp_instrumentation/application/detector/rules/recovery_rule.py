from __future__ import annotations

import ast
from typing import List

from awcp_instrumentation.application.detector.rules.base_rule import BaseDetectionRule
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory

_HOOK = GovernanceHook(
    category=HookCategory.RECOVERY,
    name="awcp_hooks.recovery",
    description="AWCP recovery hook: emitted when the agent attempts to recover from a failure or initiates a retry",
    signature="awcp_hooks.recovery(attempt_number, reason, **context)",
    line_number=None,
)

_KEYWORDS = [
    "awcp_hooks.recovery", "awcp.recovery",
    "recovery_hook", "on_recovery", "retry_hook",
    "recover_hook", "on_retry", "retry_attempt",
    "hooks.recovery", "lifecycle.recovery",
]


class RecoveryDetectionRule(BaseDetectionRule):
    @property
    def category(self) -> HookCategory:
        return HookCategory.RECOVERY

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
