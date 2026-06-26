"""
Data models for the Sandbox Validation Engine.

These application-layer types carry the results of sandbox execution and
evidence collection.  They are distinct from the domain-layer
``ValidationReport`` / ``HookValidationResult`` entities: the domain types
carry the authoritative per-hook outcome (PASSED / FAILED / SKIPPED), while
the models here carry the raw execution artefacts and evidence observations
that the validator used to produce those outcomes.

``SandboxValidationResult`` is the single type consumed by the downstream
Validation Report module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from awcp_instrumentation.application.applicator.models import PatchedSource
from awcp_instrumentation.domain.entities.validation_report import ValidationReport
from awcp_instrumentation.domain.enums.hook_category import HookCategory
from awcp_instrumentation.domain.enums.validation_status import ValidationStatus


# ---------------------------------------------------------------------------
# SandboxExecutionMode
# ---------------------------------------------------------------------------

class SandboxExecutionMode(str, Enum):
    """
    Controls how deeply the sandbox validates patched source.

    Values are ordered from cheapest to most thorough:

    SYNTAX_ONLY
        Parse the source with ``ast.parse()``.  No subprocess is spawned.
        Fastest; suitable for CI environments that forbid subprocess calls.

    IMPORT_CHECK
        Syntax check + ``compile()`` the source to byte-code.  Catches
        ``SyntaxError`` and certain ``NameError`` variants without executing
        any user code.  No subprocess.

    FULL_EXECUTION
        Syntax check + compile + run the patched source in a ``SandboxEnvironment``
        (typically a subprocess).  Captures stdout/stderr and exit code.
        Enables ``EvidenceCollector`` observations.  Default mode.
    """

    SYNTAX_ONLY = "syntax_only"
    IMPORT_CHECK = "import_check"
    FULL_EXECUTION = "full_execution"


# ---------------------------------------------------------------------------
# ExecutionRecord
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExecutionRecord:
    """
    Raw artefacts returned by ``SandboxEnvironment.execute()``.

    This is the shared contract between all sandbox implementations and the
    ``PythonSandboxValidator``.  It is environment-agnostic: a subprocess
    implementation and a remote CodeAct implementation both produce the same
    type.

    Attributes:
        stdout:      Captured standard output.
        stderr:      Captured standard error (includes Python ``logging`` output
                     when the handler writes to stderr, which is the default).
        exit_code:   Process exit code (0 = success).
        duration_ms: Wall-clock execution time in milliseconds.
        timed_out:   True when execution was terminated by the timeout.
        metadata:    Extensible bag for environment-specific data.  A
                     ``LocalPythonSandbox`` leaves this empty.  A future
                     ``CodeActSandbox`` might store trace IDs, span lists, or
                     metric snapshots here for use by specialised
                     ``EvidenceCollector`` implementations.
    """

    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float
    timed_out: bool
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        """True when exit code is 0 and execution did not time out."""
        return self.exit_code == 0 and not self.timed_out

    @property
    def combined_output(self) -> str:
        """Stdout and stderr concatenated; useful for pattern searches."""
        return self.stdout + "\n" + self.stderr


# ---------------------------------------------------------------------------
# ValidationError
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValidationError:
    """
    A fatal per-hook or engine-level error recorded during sandbox validation.

    Attributes:
        category:     The governance hook category associated with this error.
        error_type:   Short classification string: ``"SyntaxError"``,
                      ``"ImportError"``, ``"RuntimeError"``, ``"TimeoutError"``.
        message:      Human-readable description of what went wrong.
        traceback:    Captured traceback text, when available.
        line_number:  Source line where the error was detected, when known.
    """

    category: HookCategory
    error_type: str
    message: str
    traceback: Optional[str] = None
    line_number: Optional[int] = None


# ---------------------------------------------------------------------------
# ValidationWarning
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValidationWarning:
    """
    A non-fatal issue observed during sandbox validation.

    Warnings do not change a hook's pass/fail status but are surfaced in the
    final report for human review.

    Attributes:
        category: The governance hook category this warning relates to.
        message:  Human-readable description of the issue.
    """

    category: HookCategory
    message: str


# ---------------------------------------------------------------------------
# RuntimeObservation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RuntimeObservation:
    """
    Evidence that a specific governance hook did (or did not) run at execution
    time.

    Produced by an ``EvidenceCollector`` after inspecting an ``ExecutionRecord``.

    Attributes:
        category:        The governance hook category being observed.
        hook_name:       The hook's canonical name.
        observed:        True when the collector found a signal for this hook.
        stdout_excerpt:  Relevant slice of stdout (empty string if none found).
        stderr_excerpt:  Relevant slice of stderr (empty string if none found).
        signal_patterns: The patterns that were searched for.
        collector_name:  Name of the ``EvidenceCollector`` that produced this
                         observation — for traceability when multiple collectors
                         are composed.
    """

    category: HookCategory
    hook_name: str
    observed: bool
    stdout_excerpt: str
    stderr_excerpt: str
    signal_patterns: List[str]
    collector_name: str


# ---------------------------------------------------------------------------
# ValidationEvidence
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValidationEvidence:
    """
    All raw artefacts captured during the validation of one patched agent.

    Consumed by the Validation Report module for inclusion in audit logs and
    human-readable summaries.

    Attributes:
        execution_mode:   The ``SandboxExecutionMode`` used.
        environment_name: Name of the ``SandboxEnvironment`` that executed the
                          code (e.g. ``"local_python"``).
        executed:         False when execution was skipped (SYNTAX_ONLY mode or
                          syntax error prevented execution).
        stdout:           Full captured stdout (empty when not executed).
        stderr:           Full captured stderr (empty when not executed).
        exit_code:        Exit code from the sandbox (None when not executed).
        duration_ms:      Wall-clock execution time (None when not executed).
        timed_out:        True when execution was killed by the timeout.
        syntax_valid:     Whether ``ast.parse()`` succeeded.
        observations:     Per-hook ``RuntimeObservation`` objects from all
                          ``EvidenceCollector`` instances.
    """

    execution_mode: SandboxExecutionMode
    environment_name: str
    executed: bool
    stdout: str
    stderr: str
    exit_code: Optional[int]
    duration_ms: Optional[float]
    timed_out: bool
    syntax_valid: bool
    observations: List[RuntimeObservation] = field(default_factory=list)

    @property
    def had_runtime_error(self) -> bool:
        """True when execution ran and returned a non-zero exit code."""
        return self.executed and self.exit_code is not None and self.exit_code != 0

    @property
    def combined_output(self) -> str:
        """Stdout + stderr for downstream text searches."""
        return self.stdout + "\n" + self.stderr


# ---------------------------------------------------------------------------
# SandboxValidationResult
# ---------------------------------------------------------------------------

@dataclass
class SandboxValidationResult:
    """
    Top-level output of the Sandbox Validation Engine.

    The Validation Report module consumes **only** this type.  It contains
    everything needed to produce the final report without reaching back into
    earlier pipeline stages.

    Attributes:
        patched_source_ref: The ``PatchedSource`` that was validated.
                            Provides a back-reference to the apply stage for
                            full pipeline traceability.
        report:             Domain-layer ``ValidationReport`` with per-hook
                            PASSED / FAILED / SKIPPED outcomes.  This is the
                            authoritative result.
        evidence:           Raw execution artefacts (stdout, stderr, observations).
        errors:             Engine-level or per-hook fatal errors.
        warnings:           Non-fatal issues recorded during validation.
        generated_at:       UTC timestamp of result creation.
    """

    patched_source_ref: PatchedSource
    report: ValidationReport
    evidence: ValidationEvidence
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationWarning] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.utcnow)

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def is_valid(self) -> bool:
        """True when the overall validation status is PASSED."""
        return self.report.overall_status == ValidationStatus.PASSED

    @property
    def passed_count(self) -> int:
        return len(self.report.passed)

    @property
    def failed_count(self) -> int:
        return len(self.report.failed)

    @property
    def skipped_count(self) -> int:
        return len(self.report.skipped)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)
