from __future__ import annotations

import ast
from abc import ABC, abstractmethod
from typing import List

from awcp_instrumentation.application.scanner.result import RepositoryScanResult
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.entities.hook_detection_result import HookDetectionResult
from awcp_instrumentation.domain.enums.hook_category import HookCategory


class DetectionRule(ABC):
    """
    Contract for a single-category governance hook detection rule.

    Each concrete implementation is responsible for exactly one
    ``HookCategory``.  It declares what hooks policy requires and implements
    AST analysis to find which of those hooks are present in a given agent.
    """

    @property
    @abstractmethod
    def category(self) -> HookCategory:
        """The governance category this rule is responsible for."""

    @property
    @abstractmethod
    def required_hooks(self) -> List[GovernanceHook]:
        """
        Policy-mandated hooks for this category (``line_number`` is always
        ``None`` here — these are definitions, not detections).
        """

    @abstractmethod
    def detect(self, tree: ast.Module, agent: AgentSource) -> List[GovernanceHook]:
        """
        Analyse *tree* and return any required hooks that are present.

        Each returned hook must have ``line_number`` set to where in the
        source the hook was found.  Return an empty list when none are found.
        """


class HookDetector(ABC):
    """
    Port (abstract interface) for the Governance Hook Detection stage.

    Downstream stages depend only on this abstraction.
    """

    @abstractmethod
    def detect(self, agent: AgentSource) -> HookDetectionResult:
        """
        Detect governance hooks in a single agent.

        Args:
            agent: The ``AgentSource`` to analyse.

        Returns:
            A ``HookDetectionResult`` with ``present_hooks`` and
            ``missing_hooks`` populated.

        Raises:
            SyntaxError: If *agent.source_code* is not valid Python.
        """

    @abstractmethod
    def detect_all(self, scan_result: RepositoryScanResult) -> List[HookDetectionResult]:
        """
        Detect governance hooks for every agent in *scan_result*.

        Agents whose source cannot be parsed are silently skipped.

        Args:
            scan_result: Output from the Repository Scanner stage.

        Returns:
            One ``HookDetectionResult`` per successfully parsed agent.
        """
