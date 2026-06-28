from __future__ import annotations

import ast
from typing import List

from awcp_instrumentation.application.detector.rules.base_rule import BaseDetectionRule
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory

_HOOK = GovernanceHook(
    category=HookCategory.FEATURE_FLAG,
    name="HookType.SIGNAL_RECEIVED",
    description="AWCP feature-flag hook: emitted via HookType.SIGNAL_RECEIVED when the agent evaluates a feature flag",
    signature="get_manager().dispatch(HookType.SIGNAL_RECEIVED, agent_id=agent_id, task_id=task_id, flag_name=flag_name, enabled=enabled)",
    line_number=None,
)

_KEYWORDS = [
    "feature_flag_hook", "check_feature_flag",
    "flag_check_hook", "flag_enabled", "flag_evaluated",
    "awcp_hooks.feature_flag",
    "hooks.feature_flag",
]

# Distinguish from RECOVERY (which also uses SIGNAL_RECEIVED) by requiring
# flag_name= kwarg — the canonical marker for a feature-flag signal.
_SIGNAL_KEYWORDS = ["dispatch", "signal_received"]
_REQUIRED_KWARG = "flag_name"


class FeatureFlagDetectionRule(BaseDetectionRule):
    @property
    def category(self) -> HookCategory:
        return HookCategory.FEATURE_FLAG

    @property
    def required_hooks(self) -> List[GovernanceHook]:
        return [_HOOK]

    def detect(self, tree: ast.Module, agent: AgentSource) -> List[GovernanceHook]:
        match = self._first_matching_call(self._call_sites(tree), _KEYWORDS)
        if match:
            return [self._found(_HOOK, match[1])]
        # Detect SIGNAL_RECEIVED dispatch only when flag_name= kwarg is present
        match = self._first_matching_call_with_kwarg(
            self._calls_with_kwarg_names(tree), _SIGNAL_KEYWORDS, _REQUIRED_KWARG
        )
        if match:
            return [self._found(_HOOK, match[1])]
        dec = self._first_matching_decorator(self._decorator_sites(tree), _KEYWORDS)
        if dec:
            return [self._found(_HOOK, dec[1])]
        return []
