"""
Data models for the Patch Apply Engine.

These application-layer types carry the result of applying patch proposals
to agent source code.  The domain layer is not modified.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from awcp_instrumentation.application.generator.models import (
    PatchGenerationResult,
    PatchProposal,
)
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.enums.hook_category import HookCategory


# ---------------------------------------------------------------------------
# ApplyStatus
# ---------------------------------------------------------------------------

class ApplyStatus(str, Enum):
    """Overall outcome of applying all proposals from a generation result."""

    SUCCESS = "success"
    """All applicable proposals were applied without errors (warnings are allowed)."""

    PARTIAL = "partial"
    """Some proposals were applied successfully; at least one produced an error."""

    FAILED = "failed"
    """No proposals could be applied, or a fatal engine error occurred."""


# ---------------------------------------------------------------------------
# ApplyWarning
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ApplyWarning:
    """
    A non-fatal issue encountered while applying a patch proposal.

    Warnings do not stop the apply process.  Common causes:
    - An ``InsertionLocation`` required a fallback (e.g. ``AROUND_FUNCTION``
      fell back to ``BEFORE_FUNCTION_BODY``).
    - An import was skipped because it already existed in the source.

    Attributes:
        category: The governance hook category associated with this warning.
        message:  Human-readable description of what happened and why.
    """

    category: HookCategory
    message: str


# ---------------------------------------------------------------------------
# ApplyError
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ApplyError:
    """
    A fatal issue that prevented a proposal from being applied.

    The source is left in the state it was before this proposal was attempted.
    All other proposals continue to be applied.

    Attributes:
        category:           The governance category that could not be applied.
        message:            Human-readable description of the failure.
        original_exception: String representation of the underlying exception,
                            if one was raised.
    """

    category: HookCategory
    message: str
    original_exception: Optional[str] = None


# ---------------------------------------------------------------------------
# PatchedSource
# ---------------------------------------------------------------------------

@dataclass
class PatchedSource:
    """
    The immutable result of applying patch proposals to an agent's source code.

    This is the primary output consumed by the Sandbox Validation module.
    It carries both the transformed source code and a full audit record of
    what was applied, warned, or failed.

    Attributes:
        original_agent:     The unmodified ``AgentSource`` that was patched.
        patched_source:     The transformed Python source code after all
                            successful proposals were applied.
        applied_proposals:  Proposals that were successfully applied to the
                            source.  The Sandbox validates these.
        warnings:           Non-fatal issues recorded during the apply process.
        errors:             Proposals that could not be applied.
    """

    original_agent: AgentSource
    patched_source: str
    applied_proposals: List[PatchProposal]
    warnings: List[ApplyWarning]
    errors: List[ApplyError]

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def has_changes(self) -> bool:
        """True when the patched source differs from the original."""
        return self.patched_source != self.original_agent.source_code

    @property
    def applied_count(self) -> int:
        """Number of proposals successfully applied."""
        return len(self.applied_proposals)

    @property
    def error_count(self) -> int:
        """Number of proposals that failed to apply."""
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        """Number of non-fatal warnings raised during apply."""
        return len(self.warnings)

    @property
    def as_agent_source(self) -> AgentSource:
        """
        Wrap the patched source in an ``AgentSource``.

        Preserves the original path and agent name so downstream stages
        (Sandbox, Validation Report) can identify which agent was instrumented.
        """
        return AgentSource(
            path=self.original_agent.path,
            source_code=self.patched_source,
            agent_name=self.original_agent.agent_name,
        )

    @property
    def diff(self) -> str:
        """
        Unified diff between the original and patched source.

        Useful for human review, audit logs, and PR descriptions.
        Returns an empty string when no changes were made.
        """
        if not self.has_changes:
            return ""
        original_lines = self.original_agent.source_code.splitlines(keepends=True)
        patched_lines = self.patched_source.splitlines(keepends=True)
        agent_name = self.original_agent.agent_name or "agent"
        return "".join(
            difflib.unified_diff(
                original_lines,
                patched_lines,
                fromfile=f"{agent_name} (original)",
                tofile=f"{agent_name} (patched)",
            )
        )


# ---------------------------------------------------------------------------
# ApplyResult
# ---------------------------------------------------------------------------

@dataclass
class ApplyResult:
    """
    Top-level output of the Patch Apply Engine.

    Carries the patched source alongside the full generation context so that
    downstream stages have everything they need without reaching back into
    earlier pipeline stages.

    Attributes:
        generation_result: The ``PatchGenerationResult`` that was applied.
                           Contains the original gap report and all proposals.
        patched_source:    The apply outcome.  ``None`` only when no successful
                           proposals were available to apply and the source was
                           not touched.
        status:            Overall success/partial/failed status.
        generated_at:      UTC timestamp of result creation.
        metadata:          Arbitrary key/value pairs for traceability.
    """

    generation_result: PatchGenerationResult
    patched_source: Optional[PatchedSource]
    status: ApplyStatus
    generated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, str] = field(default_factory=dict)

    @property
    def is_successful(self) -> bool:
        """True when status is SUCCESS."""
        return self.status == ApplyStatus.SUCCESS

    @property
    def has_warnings(self) -> bool:
        """True when the patched source has at least one warning."""
        return bool(self.patched_source and self.patched_source.warnings)

    @property
    def has_errors(self) -> bool:
        """True when the patched source has at least one apply error."""
        return bool(self.patched_source and self.patched_source.errors)
