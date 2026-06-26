"""
LLM Patch Generator — concrete implementation of the PatchGenerator port.

Orchestrates the full loop for each governance gap:
  GovernanceGap → PromptBuilder → LlmProvider → ResponseParser → PatchProposal
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from awcp_instrumentation.application.gap_reporter.models import (
    GovernanceGap,
    GovernanceGapReport,
)
from awcp_instrumentation.application.generator.interface import PatchGenerator
from awcp_instrumentation.application.generator.llm_interface import (
    LlmProvider,
    LlmProviderError,
    LlmRequest,
    LlmResponse,
)
from awcp_instrumentation.application.generator.models import (
    PatchGenerationResult,
    PatchMetadata,
    PatchProposal,
    ProposalStatus,
)
from awcp_instrumentation.application.generator.prompt_builder import PromptBuilder
from awcp_instrumentation.application.generator.response_parser import (
    ResponseParseError,
    ResponseParser,
)
from awcp_instrumentation.domain.entities.agent_source import AgentSource


class LlmPatchGenerator(PatchGenerator):
    """
    Generates instrumentation patch proposals using an injected LLM provider.

    For each ``GovernanceGap`` in the supplied ``GovernanceGapReport``:

    1. ``PromptBuilder`` constructs an ``LlmRequest`` from the gap and the
       agent's source code.
    2. The ``LlmProvider`` sends the request to the configured model.
    3. ``ResponseParser`` converts the response into ``PatchChange`` objects.
    4. A ``PatchProposal`` is assembled and added to the result.

    LLM or parse failures are captured per-proposal (``status == FAILED``) so
    that one broken gap never aborts the entire generation run.

    Args:
        llm_provider:   The LLM provider to call.  Injected — never hardcoded.
        prompt_builder: Optional custom ``PromptBuilder``.  Defaults to one
                        with sensible parameters when ``None``.
        response_parser: Optional custom ``ResponseParser``.
        temperature:    Sampling temperature.  Passed to ``PromptBuilder`` when
                        no custom builder is supplied.
        max_tokens:     Max completion tokens.  Same handling as *temperature*.
        model:          Model override passed to the request.  ``None`` uses
                        the provider's ``default_model``.
    """

    def __init__(
        self,
        llm_provider: LlmProvider,
        prompt_builder: Optional[PromptBuilder] = None,
        response_parser: Optional[ResponseParser] = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        model: Optional[str] = None,
    ) -> None:
        self._provider = llm_provider
        self._builder = prompt_builder or PromptBuilder(
            max_tokens=max_tokens,
            temperature=temperature,
            model=model,
        )
        self._parser = response_parser or ResponseParser()

    # ------------------------------------------------------------------
    # Public API (implements PatchGenerator port)
    # ------------------------------------------------------------------

    def generate(self, report: GovernanceGapReport) -> PatchGenerationResult:
        """
        Generate proposals for every gap in *report*.

        A fully-instrumented agent (no gaps) returns an empty proposal list.
        LLM failures are recorded per-proposal — generation never raises.
        """
        proposals = [
            self.generate_for_gap(gap, report.agent)
            for gap in report.gaps
        ]
        return PatchGenerationResult(
            report=report,
            proposals=proposals,
            metadata={
                "agent_path": str(report.agent.path),
                "provider": self._provider.provider_name,
                "model": self._provider.default_model,
                "gap_count": str(len(report.gaps)),
            },
        )

    def generate_for_gap(
        self, gap: GovernanceGap, agent: AgentSource
    ) -> PatchProposal:
        """
        Generate a single proposal for *gap* in *agent*'s source code.

        Always returns a ``PatchProposal`` — on failure the proposal carries
        ``status=FAILED`` and a populated ``error`` field.
        """
        request = self._builder.build(gap, agent)
        try:
            response = self._provider.complete(request)
            return self._build_success_proposal(gap, request, response)
        except (LlmProviderError, ResponseParseError, Exception) as exc:
            return self._build_failed_proposal(gap, request, exc)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_success_proposal(
        self,
        gap: GovernanceGap,
        request: LlmRequest,
        response: LlmResponse,
    ) -> PatchProposal:
        parsed = self._parser.parse(response)
        metadata = self._make_metadata(request, response)
        return PatchProposal(
            gap=gap,
            status=ProposalStatus.SUCCESS,
            changes=parsed.changes,
            import_additions=parsed.import_additions,
            explanation=parsed.explanation,
            confidence=parsed.confidence,
            metadata=metadata,
            raw_llm_response=response.content,
            error=None,
        )

    def _build_failed_proposal(
        self,
        gap: GovernanceGap,
        request: LlmRequest,
        exc: Exception,
    ) -> PatchProposal:
        metadata = PatchMetadata(
            model=request.model or self._provider.default_model,
            provider_name=self._provider.provider_name,
            prompt_tokens=0,
            completion_tokens=0,
            temperature=request.temperature,
            generated_at=datetime.utcnow(),
        )
        return PatchProposal(
            gap=gap,
            status=ProposalStatus.FAILED,
            changes=[],
            import_additions=[],
            explanation="",
            confidence=0.0,
            metadata=metadata,
            raw_llm_response="",
            error=str(exc),
        )

    def _make_metadata(
        self, request: LlmRequest, response: LlmResponse
    ) -> PatchMetadata:
        return PatchMetadata(
            model=response.model,
            provider_name=self._provider.provider_name,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            temperature=request.temperature,
        )
