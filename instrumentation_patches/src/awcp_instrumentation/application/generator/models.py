"""
Data models for the LLM Patch Generator stage.

These application-layer types carry patch proposals from generation through
to the Patch Apply stage.  The domain layer is not modified.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from awcp_instrumentation.application.gap_reporter.models import GovernanceGap
from awcp_instrumentation.application.gap_reporter.models import GovernanceGapReport


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class InsertionLocation(str, Enum):
    """
    Conceptual location at which a ``PatchChange`` should be inserted.

    The Patch Apply module translates these values into concrete line offsets
    by inspecting the target source file.
    """

    TOP_OF_FILE = "top_of_file"
    """Absolute start of the file, before any existing content."""

    AFTER_IMPORTS = "after_imports"
    """Immediately after all top-level import statements."""

    BEFORE_FUNCTION_BODY = "before_function_body"
    """First line inside the body of ``target_function``."""

    AROUND_FUNCTION = "around_function"
    """Wrap the entire body of ``target_function`` (e.g. try/except, decorator)."""

    INLINE = "inline"
    """
    Contextual — the LLM has determined the exact location and embedded that
    context in the ``explanation`` field.  The Patch Applier should parse the
    explanation or perform a secondary analysis to locate the insertion point.
    """


class ProposalStatus(str, Enum):
    """Outcome of attempting to generate a patch for one ``GovernanceGap``."""

    SUCCESS = "success"
    """LLM responded and the response was parsed into valid changes."""

    FAILED = "failed"
    """LLM call or response parsing failed; see ``PatchProposal.error``."""

    SKIPPED = "skipped"
    """Gap was intentionally skipped (e.g. agent already patched mid-run)."""


# ---------------------------------------------------------------------------
# Atomic change unit
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PatchChange:
    """
    One atomic code insertion proposed by the LLM.

    Attributes:
        code_fragment:    Syntactically valid Python source to insert.
        location:         Conceptual insertion point consumed by Patch Apply.
        target_function:  Name of the function to modify, when *location*
                          requires one (e.g. ``BEFORE_FUNCTION_BODY``).
                          ``None`` for file-level insertions.
        explanation:      Why the LLM placed this fragment here.
    """

    code_fragment: str
    location: InsertionLocation
    target_function: Optional[str]
    explanation: str


# ---------------------------------------------------------------------------
# Traceability metadata
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PatchMetadata:
    """
    Traceability record for one LLM call.

    Stored inside each ``PatchProposal`` so that the source of every generated
    change can be fully audited.

    Attributes:
        model:            The model identifier used (e.g. ``"claude-sonnet-4-6"``).
        provider_name:    The provider class name (e.g. ``"ClaudeProvider"``).
        prompt_tokens:    Tokens consumed by the prompt.
        completion_tokens: Tokens consumed by the completion.
        temperature:      Sampling temperature used.
        generated_at:     UTC timestamp of the LLM call.
    """

    model: str
    provider_name: str
    prompt_tokens: int
    completion_tokens: int
    temperature: float
    generated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


# ---------------------------------------------------------------------------
# Patch proposal (one per gap)
# ---------------------------------------------------------------------------

@dataclass
class PatchProposal:
    """
    The complete generated patch for one ``GovernanceGap``.

    A ``PatchProposal`` is the unit of work consumed by the Patch Apply
    module.  It contains both the proposed code changes and the metadata
    needed to trace them back to a specific LLM call.

    Attributes:
        gap:              The governance gap this proposal addresses.
        status:           Whether generation succeeded, failed, or was skipped.
        changes:          Ordered list of code insertions to apply.
        import_additions: Import statements to inject at the top of the file.
        explanation:      Human-readable summary of what was generated.
        confidence:       LLM self-reported confidence score (0.0–1.0).
        metadata:         Traceability data for this LLM call.
        raw_llm_response: Full unmodified LLM response for debugging.
        error:            Error message when ``status == FAILED``.
    """

    gap: GovernanceGap
    status: ProposalStatus
    changes: List[PatchChange]
    import_additions: List[str]
    explanation: str
    confidence: float
    metadata: PatchMetadata
    raw_llm_response: str
    error: Optional[str] = None

    @property
    def total_tokens(self) -> int:
        """Total tokens consumed by the LLM call for this proposal."""
        return self.metadata.total_tokens

    @property
    def has_changes(self) -> bool:
        """True when the proposal contains at least one change or import addition."""
        return bool(self.changes) or bool(self.import_additions)

    @property
    def category(self):  # type: ignore[return]  # returns HookCategory
        """Convenience accessor for the gap's hook category."""
        return self.gap.category


# ---------------------------------------------------------------------------
# Aggregated result for one agent
# ---------------------------------------------------------------------------

@dataclass
class PatchGenerationResult:
    """
    All patch proposals generated for one agent.

    This is the output of the LLM Patch Generator stage and the sole input
    to the Patch Apply stage.

    Attributes:
        report:       The ``GovernanceGapReport`` this was generated from.
                      Contains the original agent source and all gaps.
        proposals:    One ``PatchProposal`` per gap, in gap-list order.
        generated_at: UTC timestamp of result creation.
        metadata:     Arbitrary key/value pairs for downstream traceability.
    """

    report: GovernanceGapReport
    proposals: List[PatchProposal]
    generated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, str] = field(default_factory=dict)

    @property
    def successful_proposals(self) -> List[PatchProposal]:
        """Proposals that completed successfully and have changes to apply."""
        return [p for p in self.proposals if p.status == ProposalStatus.SUCCESS]

    @property
    def failed_proposals(self) -> List[PatchProposal]:
        """Proposals that failed to generate due to LLM or parse errors."""
        return [p for p in self.proposals if p.status == ProposalStatus.FAILED]

    @property
    def skipped_proposals(self) -> List[PatchProposal]:
        """Proposals that were intentionally skipped."""
        return [p for p in self.proposals if p.status == ProposalStatus.SKIPPED]

    @property
    def total_tokens(self) -> int:
        """Total LLM tokens consumed across all proposals."""
        return sum(p.total_tokens for p in self.proposals)

    @property
    def has_failures(self) -> bool:
        """True when at least one proposal failed to generate."""
        return bool(self.failed_proposals)

    @property
    def is_complete(self) -> bool:
        """
        True when every gap in the report has a corresponding proposal
        (regardless of whether each proposal succeeded).
        """
        return len(self.proposals) == len(self.report.gaps)

    @property
    def success_rate(self) -> float:
        """Fraction of proposals that succeeded (0.0 when no proposals)."""
        if not self.proposals:
            return 0.0
        return len(self.successful_proposals) / len(self.proposals)
