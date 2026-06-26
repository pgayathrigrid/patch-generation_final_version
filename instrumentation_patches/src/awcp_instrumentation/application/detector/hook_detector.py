from __future__ import annotations

import ast
from typing import List, Optional

from awcp_instrumentation.application.detector.interface import DetectionRule, HookDetector
from awcp_instrumentation.application.detector.rules import (
    TaskStartedDetectionRule,
    TaskCompletedDetectionRule,
    TaskFailedDetectionRule,
    LlmCallDetectionRule,
    SynthesizeDetectionRule,
    ToolCallDetectionRule,
    WebSearchDetectionRule,
    TokenUsageDetectionRule,
    BudgetWarnDetectionRule,
    BudgetExhaustedDetectionRule,
    ObservabilityDetectionRule,
    PolicyDetectionRule,
    ApprovalDetectionRule,
    FeatureFlagDetectionRule,
    RecoveryDetectionRule,
    DegradationDetectionRule,
)
from awcp_instrumentation.application.scanner.result import RepositoryScanResult
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.entities.hook_detection_result import HookDetectionResult


def _default_rules() -> List[DetectionRule]:
    return [
        TaskStartedDetectionRule(),
        TaskCompletedDetectionRule(),
        TaskFailedDetectionRule(),
        LlmCallDetectionRule(),
        SynthesizeDetectionRule(),
        ToolCallDetectionRule(),
        WebSearchDetectionRule(),
        TokenUsageDetectionRule(),
        BudgetWarnDetectionRule(),
        BudgetExhaustedDetectionRule(),
        ObservabilityDetectionRule(),
        PolicyDetectionRule(),
        ApprovalDetectionRule(),
        FeatureFlagDetectionRule(),
        RecoveryDetectionRule(),
        DegradationDetectionRule(),
    ]


class RuleBasedHookDetector(HookDetector):
    """
    Orchestrates all ``DetectionRule`` instances against a parsed AST.

    Each rule is asked independently whether its category's hook is
    present.  The orchestrator aggregates the answers into a single
    ``HookDetectionResult`` per agent.

    Args:
        rules: Detection rules to apply.  Defaults to all ten AWCP lifecycle
               rules when ``None``.  Inject custom or additional rules to
               extend coverage without subclassing.
    """

    def __init__(self, rules: Optional[List[DetectionRule]] = None) -> None:
        self._rules: List[DetectionRule] = rules if rules is not None else _default_rules()

    # ------------------------------------------------------------------
    # Public API (implements HookDetector port)
    # ------------------------------------------------------------------

    def detect(self, agent: AgentSource) -> HookDetectionResult:
        """
        Detect governance hooks in a single agent.

        Args:
            agent: The ``AgentSource`` to analyse.

        Returns:
            ``HookDetectionResult`` with populated ``present_hooks`` and
            ``missing_hooks``.

        Raises:
            SyntaxError: If ``agent.source_code`` is not valid Python.
        """
        tree = ast.parse(agent.source_code, filename=str(agent.path))
        return self._run_rules(tree, agent)

    def detect_all(self, scan_result: RepositoryScanResult) -> List[HookDetectionResult]:
        """
        Detect hooks for all agents in *scan_result*.

        Agents with unparseable source are silently skipped so that one
        broken file never blocks the rest of the repository.
        """
        results: List[HookDetectionResult] = []
        for agent in scan_result.agents:
            try:
                results.append(self.detect(agent))
            except SyntaxError:
                pass
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_rules(self, tree: ast.Module, agent: AgentSource) -> HookDetectionResult:
        present: List[GovernanceHook] = []
        missing: List[GovernanceHook] = []

        for rule in self._rules:
            found = rule.detect(tree, agent)
            if found:
                present.extend(found)
            else:
                missing.extend(rule.required_hooks)

        return HookDetectionResult(
            agent=agent,
            present_hooks=present,
            missing_hooks=missing,
        )
