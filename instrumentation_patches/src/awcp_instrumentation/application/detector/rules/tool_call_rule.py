from __future__ import annotations

import ast
from typing import List

from awcp_instrumentation.application.detector.rules.base_rule import BaseDetectionRule
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory

_HOOK = GovernanceHook(
    category=HookCategory.TOOL_CALL,
    name="awcp_hooks.tool_call",
    description="AWCP lifecycle hook: emitted before and after every external tool invocation",
    signature="awcp_hooks.tool_call(tool_name, tool_input, **context)",
    line_number=None,
)

_KEYWORDS = [
    "awcp_hooks.tool_call", "awcp.tool_call",
    "on_tool_call", "tool_call_hook", "before_tool_call", "after_tool_call",
    "hooks.tool_call", "lifecycle.tool_call",
    "emit_tool_call", "track_tool_call",
    "on_tool_start", "on_tool_end", "tool_invoke",
]


class ToolCallDetectionRule(BaseDetectionRule):
    @property
    def category(self) -> HookCategory:
        return HookCategory.TOOL_CALL

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
