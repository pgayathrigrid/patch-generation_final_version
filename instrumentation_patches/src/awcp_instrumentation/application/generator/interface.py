from __future__ import annotations

from abc import ABC, abstractmethod

from awcp_instrumentation.application.gap_reporter.models import (
    GovernanceGap,
    GovernanceGapReport,
)
from awcp_instrumentation.application.generator.models import (
    PatchGenerationResult,
    PatchProposal,
)
from awcp_instrumentation.domain.entities.agent_source import AgentSource


class PatchGenerator(ABC):
    """
    Port (abstract interface) for the LLM Patch Generator stage.

    Downstream consumers (Patch Apply, tests) depend only on this abstraction.
    The concrete ``LlmPatchGenerator`` is injected at runtime.
    """

    @abstractmethod
    def generate(self, report: GovernanceGapReport) -> PatchGenerationResult:
        """
        Generate patch proposals for every gap in *report*.

        Args:
            report: The ``GovernanceGapReport`` produced by the Gap Reporter.
                    Must have ``ready_for_patching == True`` to produce proposals;
                    a fully-instrumented report yields an empty proposal list.

        Returns:
            A ``PatchGenerationResult`` with one ``PatchProposal`` per gap.
        """

    @abstractmethod
    def generate_for_gap(
        self, gap: GovernanceGap, agent: AgentSource
    ) -> PatchProposal:
        """
        Generate a patch proposal for a single *gap* in *agent*'s source.

        This lower-level method is exposed so callers can regenerate a single
        proposal without re-running the entire gap report.

        Args:
            gap:   The ``GovernanceGap`` to address.
            agent: The ``AgentSource`` whose source code the LLM will instrument.

        Returns:
            A ``PatchProposal`` — always, even on failure (``status == FAILED``).
        """
