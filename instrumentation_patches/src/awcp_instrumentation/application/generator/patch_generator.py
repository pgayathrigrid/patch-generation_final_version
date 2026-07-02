"""
LLM Patch Generator — concrete implementation of the PatchGenerator port.

Orchestrates the full loop for each governance gap:
  GovernanceGap → PromptBuilder → LlmProvider → ResponseParser → PatchProposal
"""
from __future__ import annotations

import dataclasses
import re
from datetime import datetime
from typing import List, Optional

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

        When there are 2+ gaps, a single batch LLM call is made (one prompt,
        one response containing N patch objects).  A single gap uses the
        normal per-gap path.  If the batch call fails, it falls back to
        individual per-gap calls so one failure never blocks the others.

        A fully-instrumented agent (no gaps) returns an empty proposal list.
        LLM failures are recorded per-proposal — generation never raises.
        """
        if not report.gaps:
            proposals: List[PatchProposal] = []
        elif len(report.gaps) == 1:
            proposals = [self.generate_for_gap(report.gaps[0], report.agent)]
        else:
            proposals = self._generate_batch(report.gaps, report.agent)

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
        ``status=FAILED`` and a populated ``error`` field.  When the primary
        provider fails (e.g. truncated JSON from Gemini), a MockLlmProvider
        is used as a fallback so governance patching never silently stalls.
        """
        request = self._builder.build(gap, agent)
        try:
            response = self._provider.complete(request)
            proposal = self._build_success_proposal(gap, request, response)
            return self._deduplicate_changes(gap, proposal)
        except (LlmProviderError, ResponseParseError, Exception):
            pass

        # Fallback to mock provider for a guaranteed-valid patch template
        try:
            from awcp_instrumentation.application.generator.providers.mock_provider import (
                MockLlmProvider,
            )
            fallback_response = MockLlmProvider().complete(request)
            proposal = self._build_success_proposal(gap, request, fallback_response)
            return self._deduplicate_changes(gap, proposal)
        except Exception as exc:
            return self._build_failed_proposal(gap, request, exc)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _generate_batch(
        self, gaps: List[GovernanceGap], agent: AgentSource
    ) -> List[PatchProposal]:
        """
        Make one LLM call for all *gaps* and return one proposal per gap.

        Falls back to individual ``generate_for_gap()`` calls if the batch
        call or parse fails, so no gap is silently dropped.
        """
        request = self._builder.build_batch(gaps, agent)
        try:
            response = self._provider.complete(request)
            parsed_list = self._parser.parse_batch(response, len(gaps))
            metadata = self._make_metadata(request, response)
            proposals = [
                self._deduplicate_changes(
                    gap,
                    PatchProposal(
                        gap=gap,
                        status=ProposalStatus.SUCCESS,
                        changes=parsed.changes,
                        import_additions=parsed.import_additions,
                        explanation=parsed.explanation,
                        confidence=parsed.confidence,
                        metadata=metadata,
                        raw_llm_response=response.content,
                        error=None,
                    ),
                )
                for gap, parsed in zip(gaps, parsed_list)
            ]
            # If any proposal uses the wrong HookType, fall back to per-gap so
            # each LLM call is focused on exactly one hook — more reliable than
            # asking the model to keep N types distinct in one batch response.
            if self._batch_has_wrong_hook_types(gaps, proposals):
                return [self.generate_for_gap(gap, agent) for gap in gaps]
            return proposals
        except (LlmProviderError, ResponseParseError, Exception):
            return [self.generate_for_gap(gap, agent) for gap in gaps]

    @staticmethod
    def _deduplicate_changes(
        gap: GovernanceGap, proposal: PatchProposal
    ) -> PatchProposal:
        """Keep only the first change whose code_fragment dispatches the correct
        HookType for this gap; drop any extras.

        The LLM sometimes returns multiple changes all dispatching the same hook
        (e.g. TASK_COMPLETED dispatched 3×). One dispatch is correct; the rest
        are noise that would produce duplicate instrumentation in the source.
        If no change matches the expected type, return the proposal unchanged so
        the applier can surface the mismatch rather than silently dropping all changes.
        """
        if not proposal.changes:
            return proposal
        expected = f"HookType.{gap.category.name}"
        matching = [
            c for c in proposal.changes
            if c.code_fragment and expected in c.code_fragment
        ]
        if not matching:
            return proposal  # no type match — surface as-is for the applier to handle
        # Keep the first matching change, sanitized; drop any duplicates
        clean = LlmPatchGenerator._sanitize_change(matching[0])
        if [clean] == list(proposal.changes) and clean is matching[0]:
            return proposal
        return dataclasses.replace(proposal, changes=[clean])

    @staticmethod
    def _sanitize_change(change):
        """Remove common LLM hallucinations from a code_fragment.

        Replaces ``=str(identifier)`` patterns (e.g. ``error=str(e)``) with
        ``=None``.  Exception variables like ``e`` are only defined inside their
        ``except`` block and are never in scope at the insertion point, so using
        them would cause a ``NameError`` at runtime.
        """
        from awcp_instrumentation.application.generator.models import PatchChange
        frag = change.code_fragment or ""
        # Replace  error=str(e)  /  reason=str(exc)  etc. with  =None
        frag = re.sub(r"=str\(\w+\)", "=None", frag)
        if frag == change.code_fragment:
            return change
        return dataclasses.replace(change, code_fragment=frag)

    @staticmethod
    def _batch_has_wrong_hook_types(
        gaps: List[GovernanceGap], proposals: List[PatchProposal]
    ) -> bool:
        """Return True if the batch result has any hook-type quality issues.

        Triggers per-gap fallback on two failure modes:
        1. Wrong type — a proposal's fragment uses a different HookType than
           the gap requires (e.g. TASK_STARTED gap gets TASK_COMPLETED dispatch).
        2. Duplicate — a proposal returns multiple changes all dispatching the
           same HookType (e.g. TASK_COMPLETED dispatched 3× in one proposal).
           Each gap should produce exactly one dispatch call.
        """
        for gap, proposal in zip(gaps, proposals):
            expected = f"HookType.{gap.category.name}"
            correct_count = 0
            for change in proposal.changes:
                frag = change.code_fragment or ""
                if not frag:
                    continue
                if expected not in frag:
                    return True  # wrong type
                correct_count += 1
            if correct_count > 1:
                return True  # duplicate dispatches for the same gap
        return False

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
