"""
Data models for the Validation Report Builder.

``BuiltReport`` is the rich application-layer report object produced by
``ValidationReportBuilder``.  It is consumed by ``ReportFormatter``
implementations to produce string output (JSON, Markdown, etc.).

All sub-types are frozen dataclasses — they are value objects assembled
once by the builder and never mutated thereafter.
``BuiltReport`` itself is a regular (mutable) dataclass because its list
fields are not hashable.

Design note
~~~~~~~~~~~
The models here are intentionally *flat and fully resolved*: every field
is a primitive, string, or another frozen dataclass.  Formatters therefore
need no knowledge of the upstream domain model and can serialize the report
without importing from the domain or sandbox layers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


# ---------------------------------------------------------------------------
# AgentInfo
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AgentInfo:
    """Identity information for the agent that was validated."""

    name: str
    path: Optional[str]


# ---------------------------------------------------------------------------
# ExecutionSummary
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExecutionSummary:
    """
    Snapshot of the sandbox execution context.

    Attributes:
        mode:           ``SandboxExecutionMode`` value string.
        environment:    Name of the ``SandboxEnvironment`` used.
        executed:       Whether code was actually run (False for SYNTAX_ONLY).
        duration_ms:    Wall-clock time in milliseconds (None when not executed).
        exit_code:      Subprocess exit code (None when not executed).
        timed_out:      True when execution was killed by the timeout.
        syntax_valid:   Whether ``ast.parse()`` succeeded.
        stdout_excerpt: First 500 characters of captured stdout.
        stderr_excerpt: First 500 characters of captured stderr.
    """

    mode: str
    environment: str
    executed: bool
    duration_ms: Optional[float]
    exit_code: Optional[int]
    timed_out: bool
    syntax_valid: bool
    stdout_excerpt: str
    stderr_excerpt: str


# ---------------------------------------------------------------------------
# HookResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HookResult:
    """
    Per-hook validation outcome, ready for rendering.

    All fields are strings so formatters remain format-agnostic.
    ``status`` uses the ``ValidationStatus`` value string (e.g. ``"passed"``).
    """

    category: str
    hook_name: str
    status: str
    message: str
    stdout: str
    stderr: str


# ---------------------------------------------------------------------------
# ObservationSummary
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ObservationSummary:
    """
    Summarised ``RuntimeObservation`` from evidence collection.

    Attributes:
        category:       Hook category value string.
        hook_name:      Hook canonical name.
        observed:       Whether the collector detected a signal.
        collector:      ``EvidenceCollector.collector_name``.
        stdout_excerpt: First matching stdout line (empty when none found).
        stderr_excerpt: First matching stderr line (empty when none found).
    """

    category: str
    hook_name: str
    observed: bool
    collector: str
    stdout_excerpt: str
    stderr_excerpt: str


# ---------------------------------------------------------------------------
# ReportError
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReportError:
    """A fatal error from the sandbox stage, ready for rendering."""

    category: str
    error_type: str
    message: str
    traceback: Optional[str] = None


# ---------------------------------------------------------------------------
# ReportWarning
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReportWarning:
    """A non-fatal warning from the sandbox stage, ready for rendering."""

    category: str
    message: str


# ---------------------------------------------------------------------------
# HookRecommendation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HookRecommendation:
    """
    Governance recommendation for a hook that failed validation.

    Drawn from the ``GovernanceGap.recommendation`` of the corresponding
    ``PatchProposal`` in the apply result.  If no matching proposal exists
    (edge case), a generic recommendation is used.

    Attributes:
        category:   Hook category value string.
        hook_name:  Hook canonical name.
        action:     Short description of the required action.
        rationale:  Why this hook is required.
        hint:       Instrumentation hint from the gap report.
        priority:   Numeric priority (lower = higher urgency).
        severity:   Risk severity string (e.g. ``"critical"``).
    """

    category: str
    hook_name: str
    action: str
    rationale: str
    hint: str
    priority: int
    severity: str


# ---------------------------------------------------------------------------
# BuiltReport
# ---------------------------------------------------------------------------

@dataclass
class BuiltReport:
    """
    The fully assembled validation report, ready for formatting.

    This is the primary output of ``ValidationReportBuilder.build()``.
    It is a self-contained snapshot: formatters need only this object and
    no other pipeline stage's outputs.

    Attributes:
        agent:             Identity of the validated agent.
        generated_at:      UTC timestamp of report creation.
        overall_status:    ``ValidationStatus`` value string (``"passed"`` /
                           ``"failed"`` / ``"skipped"``).
        execution_summary: Execution context (mode, environment, duration…).
        hook_results:      Per-hook validation outcomes.
        missing_hooks:     Category value strings of hooks that FAILED
                           validation (still unaddressed after patching).
        observations:      Runtime observations from evidence collectors.
        errors:            Fatal sandbox errors.
        warnings:          Non-fatal sandbox warnings.
        recommendations:   Governance recommendations for failed hooks.
        summary:           One-sentence human-readable result line.
        total_hooks:       Total number of hooks that were validated.
        passed_hooks:      Number of hooks that PASSED.
        failed_hooks:      Number of hooks that FAILED.
        skipped_hooks:     Number of hooks that were SKIPPED.
    """

    agent: AgentInfo
    generated_at: datetime
    overall_status: str

    execution_summary: ExecutionSummary

    hook_results: List[HookResult] = field(default_factory=list)
    missing_hooks: List[str] = field(default_factory=list)
    observations: List[ObservationSummary] = field(default_factory=list)
    errors: List[ReportError] = field(default_factory=list)
    warnings: List[ReportWarning] = field(default_factory=list)
    recommendations: List[HookRecommendation] = field(default_factory=list)

    summary: str = ""

    total_hooks: int = 0
    passed_hooks: int = 0
    failed_hooks: int = 0
    skipped_hooks: int = 0

    @property
    def is_passing(self) -> bool:
        return self.overall_status == "passed"

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)

    @property
    def has_recommendations(self) -> bool:
        return bool(self.recommendations)

    @property
    def has_observations(self) -> bool:
        return bool(self.observations)
