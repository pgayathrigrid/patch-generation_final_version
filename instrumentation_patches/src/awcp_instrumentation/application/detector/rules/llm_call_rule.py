from __future__ import annotations

import ast
from typing import List

from awcp_instrumentation.application.detector.rules.base_rule import BaseDetectionRule
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory

_HOOK = GovernanceHook(
    category=HookCategory.LLM_CALL,
    name="awcp_hooks.llm_call",
    description="AWCP lifecycle hook: emitted before and after every LLM inference call",
    signature="awcp_hooks.llm_call(model, prompt_tokens, **context)",
    line_number=None,
)

_KEYWORDS = [
    "awcp_hooks.llm_call", "awcp.llm_call",
    "on_llm_call", "llm_call_hook", "before_llm_call", "after_llm_call",
    "hooks.llm_call", "lifecycle.llm_call",
    "emit_llm_call", "track_llm_call",
    "on_llm_start", "on_llm_end",
]


class LlmCallDetectionRule(BaseDetectionRule):
    @property
    def category(self) -> HookCategory:
        return HookCategory.LLM_CALL

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
