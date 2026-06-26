"""
Abstract interface for the Patch Apply Engine.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from awcp_instrumentation.application.applicator.models import ApplyResult
from awcp_instrumentation.application.generator.models import PatchGenerationResult
from awcp_instrumentation.domain.entities.agent_source import AgentSource


class PatchApplier(ABC):
    """
    Port: transforms an AgentSource + PatchGenerationResult into an ApplyResult.

    Responsibilities:
    - Insert import statements without introducing duplicates.
    - Apply each ``PatchChange`` at the correct line and indentation.
    - Preserve original source formatting.
    - Collect apply errors per proposal without aborting the whole run.
    - Return an immutable ``ApplyResult``.

    Must NOT:
    - Generate new patches or call any LLM.
    - Scan repositories or detect governance gaps.
    - Execute Python code.
    """

    @abstractmethod
    def apply(
        self,
        agent: AgentSource,
        generation_result: PatchGenerationResult,
    ) -> ApplyResult:
        """
        Apply all successful proposals from *generation_result* to *agent*.

        Args:
            agent:             The agent source code to be patched.
            generation_result: Output of the LLM Patch Generator containing
                               one ``PatchProposal`` per governance gap.

        Returns:
            An ``ApplyResult`` describing what was applied, warned, or failed.
        """
