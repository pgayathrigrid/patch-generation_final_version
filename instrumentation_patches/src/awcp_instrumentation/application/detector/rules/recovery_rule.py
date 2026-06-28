from __future__ import annotations

import ast
from typing import List

from awcp_instrumentation.application.detector.rules.base_rule import BaseDetectionRule
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory

_HOOK = GovernanceHook(
    category=HookCategory.RECOVERY,
    name="HookType.SIGNAL_RECEIVED",
    description="AWCP recovery hook: emitted via HookType.SIGNAL_RECEIVED when the agent retries or recovers from failure",
    signature="get_manager().dispatch(HookType.SIGNAL_RECEIVED, agent_id=agent_id, task_id=task_id, attempt=attempt_number, reason=reason)",
    line_number=None,
)

_KEYWORDS = [
    "recovery_hook", "on_recovery", "retry_hook",
    "recover_hook", "on_retry", "retry_attempt",
    "awcp_hooks.recovery",
    "hooks.recovery",
]

# Distinguish from FEATURE_FLAG (which also uses SIGNAL_RECEIVED) by requiring
# attempt= kwarg — the canonical marker for a recovery/retry signal.
_SIGNAL_KEYWORDS = ["dispatch", "signal_received"]
_REQUIRED_KWARG = "attempt"


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
        # Detect SIGNAL_RECEIVED dispatch only when attempt= kwarg is present
        match = self._first_matching_call_with_kwarg(
            self._calls_with_kwarg_names(tree), _SIGNAL_KEYWORDS, _REQUIRED_KWARG
        )
        if match:
            return [self._found(_HOOK, match[1])]
        dec = self._first_matching_decorator(self._decorator_sites(tree), _KEYWORDS)
        if dec:
            return [self._found(_HOOK, dec[1])]
        return []
