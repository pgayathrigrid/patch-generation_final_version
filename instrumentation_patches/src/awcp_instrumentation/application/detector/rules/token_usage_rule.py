from __future__ import annotations

import ast
from typing import List

from awcp_instrumentation.application.detector.rules.base_rule import BaseDetectionRule
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory

_HOOK = GovernanceHook(
    category=HookCategory.TOKEN_USAGE,
    name="awcp_hooks.token_usage",
    description="AWCP lifecycle hook: reports prompt and completion token counts after each LLM call",
    signature="awcp_hooks.token_usage(prompt_tokens, completion_tokens, total_tokens, **context)",
    line_number=None,
)

_KEYWORDS = [
    "awcp_hooks.token_usage", "awcp.token_usage",
    "on_token_usage", "token_usage_hook", "track_tokens", "track_token_usage",
    "hooks.token_usage", "lifecycle.token_usage",
    "emit_token_usage", "report_tokens",
    "token_tracker", "on_tokens",
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
        dec = self._first_matching_decorator(self._decorator_sites(tree), _KEYWORDS)
        if dec:
            return [self._found(_HOOK, dec[1])]
        return []
