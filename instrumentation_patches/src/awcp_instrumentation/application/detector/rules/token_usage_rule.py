from __future__ import annotations

import ast
from typing import List

from awcp_instrumentation.application.detector.rules.base_rule import BaseDetectionRule
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory

_HOOK = GovernanceHook(
    category=HookCategory.TOKEN_USAGE,
    name="HookType.TOKEN_USAGE",
    description="AWCP lifecycle hook: reports prompt and completion token counts after each LLM call",
    signature="get_manager().dispatch(HookType.TOKEN_USAGE, agent_id=agent_id, task_id=task_id)",
    line_number=None,
)

_KEYWORDS = [
    "on_token_usage", "token_usage_hook", "track_tokens", "track_token_usage",
    "report_tokens", "token_tracker", "on_tokens",
    "hooktype.token_usage",
    "awcp_hooks.token_usage",
    "hooks.token_usage", "emit_token_usage",
]


class TokenUsageDetectionRule(BaseDetectionRule):
    @property
    def category(self) -> HookCategory:
        return HookCategory.TOKEN_USAGE

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
