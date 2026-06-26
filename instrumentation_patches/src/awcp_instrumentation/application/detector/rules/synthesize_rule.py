from __future__ import annotations

import ast
from typing import List

from awcp_instrumentation.application.detector.rules.base_rule import BaseDetectionRule
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory

_HOOK = GovernanceHook(
    category=HookCategory.SYNTHESIZE,
    name="awcp_hooks.synthesize",
    description="AWCP lifecycle hook: emitted when the agent synthesises a final answer",
    signature="awcp_hooks.synthesize(input_count, output_length, **context)",
    line_number=None,
)

_KEYWORDS = [
    "awcp_hooks.synthesize", "awcp.synthesize",
    "on_synthesize", "synthesize_hook", "before_synthesize", "after_synthesize",
    "hooks.synthesize", "lifecycle.synthesize",
    "emit_synthesize", "track_synthesize",
    "synthesis_hook", "on_synthesis",
]


class SynthesizeDetectionRule(BaseDetectionRule):
    @property
    def category(self) -> HookCategory:
        return HookCategory.SYNTHESIZE

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
