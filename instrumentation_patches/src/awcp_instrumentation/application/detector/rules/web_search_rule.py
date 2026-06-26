from __future__ import annotations

import ast
from typing import List

from awcp_instrumentation.application.detector.rules.base_rule import BaseDetectionRule
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory

_HOOK = GovernanceHook(
    category=HookCategory.WEB_SEARCH,
    name="awcp_hooks.web_search",
    description="AWCP lifecycle hook: emitted when the agent performs a web or retrieval search",
    signature="awcp_hooks.web_search(query, results_count, **context)",
    line_number=None,
)

_KEYWORDS = [
    "awcp_hooks.web_search", "awcp.web_search",
    "on_web_search", "web_search_hook", "before_web_search", "after_web_search",
    "hooks.web_search", "lifecycle.web_search",
    "emit_web_search", "track_web_search",
    "on_search", "search_hook",
]


class WebSearchDetectionRule(BaseDetectionRule):
    @property
    def category(self) -> HookCategory:
        return HookCategory.WEB_SEARCH

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
