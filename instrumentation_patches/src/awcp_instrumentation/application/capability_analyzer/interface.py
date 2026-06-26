from __future__ import annotations

from abc import ABC, abstractmethod

from awcp_instrumentation.application.capability_analyzer.models import CapabilityAnalysisResult
from awcp_instrumentation.domain.entities.agent_source import AgentSource


class CapabilityAnalyzer(ABC):
    """
    Port (abstract interface) for the Capability Analysis stage.

    Implementations inspect an ``AgentSource`` and return a
    ``CapabilityAnalysisResult`` describing what the agent does and which
    AWCP lifecycle hooks are therefore required.
    """

    @abstractmethod
    def analyze(self, agent: AgentSource) -> CapabilityAnalysisResult:
        """
        Analyse *agent* and return its inferred capabilities.

        Args:
            agent: The ``AgentSource`` to inspect.

        Returns:
            ``CapabilityAnalysisResult`` containing detected capabilities,
            supporting evidence, and the derived set of required hook
            categories.
        """
