"""
Concrete implementation: PythonSandboxValidator.

Orchestrates the full sandbox validation pipeline:

    1. Syntax check   — ``ast.parse()``
    2. Presence check — ``HookPresenceChecker`` (static analysis)
    3. Execution      — ``SandboxEnvironment.execute()`` (when mode allows)
    4. Evidence       — ``List[EvidenceCollector]`` (runtime observations)
    5. Assembly       — builds domain ``ValidationReport`` + ``SandboxValidationResult``

All five phases are driven by injected dependencies so that each can be
replaced or mocked independently in tests.

Pass / fail logic
-----------------
A hook's ``ValidationStatus`` is determined by the following priority order:

1. FAILED  — source has a syntax error (``ast.parse()`` raised)
2. FAILED  — the hook's code fragment is missing from the patched source
             (``HookPresenceChecker`` found no match)
3. FAILED  — execution ran and returned a non-zero exit code or timed out
4. PASSED  — all of the above checks passed
5. SKIPPED — the hook's proposal was not in ``applied_proposals`` at all
             (it was applied by the apply engine; this path only occurs for
             proposals that appear in the generation result but not in the
             applied list — handled by the caller before reaching here)

Runtime observations from ``EvidenceCollector`` are stored as supporting
evidence only.  They do NOT downgrade a PASSED hook to FAILED, because
pattern matching has inherent false-negative risk (a hook that doesn't print
output is still present and non-crashing).
"""
from __future__ import annotations

import ast
from datetime import datetime
from typing import List, Optional

from awcp_instrumentation.application.applicator.models import PatchedSource
from awcp_instrumentation.application.generator.models import PatchProposal
from awcp_instrumentation.application.sandbox.evidence_collector import EvidenceCollector
from awcp_instrumentation.application.sandbox.hook_presence import HookPresenceChecker
from awcp_instrumentation.application.sandbox.interface import SandboxValidator
from awcp_instrumentation.application.sandbox.local_python_sandbox import LocalPythonSandbox
from awcp_instrumentation.application.sandbox.models import (
    ExecutionRecord,
    RuntimeObservation,
    SandboxExecutionMode,
    SandboxValidationResult,
    ValidationError,
    ValidationEvidence,
    ValidationWarning,
)
from awcp_instrumentation.application.sandbox.output_pattern_collector import (
    OutputPatternCollector,
)
from awcp_instrumentation.application.sandbox.sandbox_environment import SandboxEnvironment
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.entities.validation_report import (
    HookValidationResult,
    ValidationReport,
)
from awcp_instrumentation.domain.enums.hook_category import HookCategory
from awcp_instrumentation.domain.enums.validation_status import ValidationStatus


class PythonSandboxValidator(SandboxValidator):
    """
    Validates patched Python source through syntax, static, and runtime checks.

    Args:
        execution_mode:   Controls how deeply the validator runs.
                          Default: ``FULL_EXECUTION``.
        timeout_seconds:  Maximum subprocess run time.  Default: 10.0 s.
        sandbox:          ``SandboxEnvironment`` to use for execution.
                          Default: ``LocalPythonSandbox()``.
        collectors:       ``EvidenceCollector`` instances to run after execution.
                          Default: ``[OutputPatternCollector()]``.
        presence_checker: ``HookPresenceChecker`` for static fragment detection.
                          Default: new ``HookPresenceChecker()``.
    """

    def __init__(
        self,
        execution_mode: SandboxExecutionMode = SandboxExecutionMode.FULL_EXECUTION,
        timeout_seconds: float = 10.0,
        sandbox: Optional[SandboxEnvironment] = None,
        collectors: Optional[List[EvidenceCollector]] = None,
        presence_checker: Optional[HookPresenceChecker] = None,
    ) -> None:
        self._mode = execution_mode
        self._timeout = timeout_seconds
        self._sandbox: SandboxEnvironment = sandbox or LocalPythonSandbox()
        self._collectors: List[EvidenceCollector] = (
            collectors if collectors is not None else [OutputPatternCollector()]
        )
        self._presence = presence_checker or HookPresenceChecker()

    # ------------------------------------------------------------------
    # SandboxValidator interface
    # ------------------------------------------------------------------

    def validate(self, patched: PatchedSource) -> SandboxValidationResult:
        """
        Validate *patched* and return a ``SandboxValidationResult``.
        """
        source = patched.patched_source
        agent_name = patched.original_agent.agent_name or "unknown_agent"
        applied = patched.applied_proposals

        errors: List[ValidationError] = []
        warnings: List[ValidationWarning] = []

        # ── Phase 1: syntax check ────────────────────────────────────────
        syntax_valid, syntax_error = self._check_syntax(source)

        if not syntax_valid and syntax_error:
            # Syntax failure: mark all hooks FAILED, skip execution entirely.
            hook_results = self._all_failed(applied, syntax_error.message)
            errors.append(syntax_error)
            evidence = self._make_evidence(
                executed=False,
                syntax_valid=False,
                record=None,
                observations=[],
            )
            report = self._build_report(agent_name, hook_results)
            return SandboxValidationResult(
                patched_source_ref=patched,
                report=report,
                evidence=evidence,
                errors=errors,
                warnings=warnings,
                generated_at=datetime.utcnow(),
            )

        # ── Phase 2: static presence check ──────────────────────────────
        presence_errors = self._check_presence(source, applied)
        errors.extend(presence_errors)

        # Track which proposals passed the presence check
        failed_categories = {e.category for e in presence_errors}

        # ── Phase 3: execution (if mode allows) ──────────────────────────
        record: Optional[ExecutionRecord] = None
        executed = False
        runtime_failed_categories: set[HookCategory] = set()

        if self._mode == SandboxExecutionMode.FULL_EXECUTION and syntax_valid:
            record = self._sandbox.execute(source, agent_name, self._timeout)
            executed = True

            if not record.succeeded:
                # Runtime failure: mark all presence-passing hooks FAILED
                error_type = "TimeoutError" if record.timed_out else "RuntimeError"
                msg = (
                    "Execution timed out."
                    if record.timed_out
                    else f"Subprocess exited with code {record.exit_code}."
                )
                if record.stderr:
                    msg += f" Stderr: {record.stderr[:500]}"

                for proposal in applied:
                    cat = proposal.category
                    if cat not in failed_categories:
                        # Only record runtime failure for hooks that were present
                        runtime_failed_categories.add(cat)
                        errors.append(
                            ValidationError(
                                category=cat,
                                error_type=error_type,
                                message=msg,
                                traceback=record.stderr or None,
                            )
                        )

        elif self._mode == SandboxExecutionMode.IMPORT_CHECK and syntax_valid:
            # Compile-only check — catches NameErrors and similar without executing
            compile_error = self._check_compile(source, applied)
            if compile_error:
                errors.append(compile_error)
                failed_categories.add(compile_error.category)

        # ── Phase 4: evidence collection ────────────────────────────────
        observations: List[RuntimeObservation] = []
        if record is not None and applied:
            for collector in self._collectors:
                try:
                    obs = collector.collect(record, applied)
                    observations.extend(obs)
                except Exception as exc:  # noqa: BLE001
                    warnings.append(
                        ValidationWarning(
                            category=HookCategory.TASK_STARTED,
                            message=f"Evidence collector '{collector.collector_name}' failed: {exc}",
                        )
                    )

        # ── Phase 5: assemble per-hook results ───────────────────────────
        all_failed_categories = failed_categories | runtime_failed_categories
        hook_results = self._build_hook_results(
            source=source,
            applied=applied,
            failed_categories=all_failed_categories,
            record=record,
        )

        # ── Phase 6: assemble output ─────────────────────────────────────
        evidence = self._make_evidence(
            executed=executed,
            syntax_valid=syntax_valid,
            record=record,
            observations=observations,
        )
        report = self._build_report(agent_name, hook_results)

        return SandboxValidationResult(
            patched_source_ref=patched,
            report=report,
            evidence=evidence,
            errors=errors,
            warnings=warnings,
            generated_at=datetime.utcnow(),
        )

    # ------------------------------------------------------------------
    # Phase helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_syntax(
        source: str,
    ) -> tuple[bool, Optional[ValidationError]]:
        """Return (is_valid, error_or_None)."""
        try:
            ast.parse(source)
            return True, None
        except SyntaxError as exc:
            return False, ValidationError(
                category=HookCategory.TASK_STARTED,
                error_type="SyntaxError",
                message=str(exc),
                line_number=exc.lineno,
            )

    def _check_presence(
        self,
        source: str,
        applied: List[PatchProposal],
    ) -> List[ValidationError]:
        """Return a ``ValidationError`` for every missing code fragment."""
        errors: List[ValidationError] = []
        for proposal, missing_changes in self._presence.missing_changes(source, applied):
            for change in missing_changes:
                errors.append(
                    ValidationError(
                        category=proposal.category,
                        error_type="MissingFragment",
                        message=(
                            f"Code fragment not found in patched source for "
                            f"{proposal.category.value} hook. "
                            f"Expected: {change.code_fragment[:80]!r}"
                        ),
                    )
                )
        return errors

    @staticmethod
    def _check_compile(
        source: str,
        applied: List[PatchProposal],
    ) -> Optional[ValidationError]:
        """Attempt compile(); return a ``ValidationError`` on failure."""
        try:
            compile(source, "<sandbox_import_check>", "exec")
            return None
        except Exception as exc:  # noqa: BLE001
            category = applied[0].category if applied else HookCategory.TASK_STARTED
            return ValidationError(
                category=category,
                error_type="ImportError",
                message=str(exc),
            )

    def _build_hook_results(
        self,
        source: str,
        applied: List[PatchProposal],
        failed_categories: set[HookCategory],
        record: Optional[ExecutionRecord],
    ) -> List[HookValidationResult]:
        """Build one ``HookValidationResult`` per applied proposal."""
        results: List[HookValidationResult] = []

        for proposal in applied:
            cat = proposal.category
            hook = proposal.gap.hook
            stdout = record.stdout if record else ""
            stderr = record.stderr if record else ""

            if cat in failed_categories:
                status = ValidationStatus.FAILED
                message = self._failure_message(cat, source, proposal, record)
            else:
                status = ValidationStatus.PASSED
                message = f"{cat.value.capitalize()} hook validated successfully."

            results.append(
                HookValidationResult(
                    hook=hook,
                    status=status,
                    message=message,
                    stdout=stdout,
                    stderr=stderr,
                )
            )

        return results

    def _failure_message(
        self,
        category: HookCategory,
        source: str,
        proposal: PatchProposal,
        record: Optional[ExecutionRecord],
    ) -> str:
        """Compose a human-readable failure message."""
        if not self._presence.all_present(source, proposal):
            return (
                f"{category.value.capitalize()} hook code fragment not found in patched source."
            )
        if record and record.timed_out:
            return f"{category.value.capitalize()} hook present but execution timed out."
        if record and record.exit_code != 0:
            return (
                f"{category.value.capitalize()} hook present but subprocess "
                f"exited with code {record.exit_code}."
            )
        return f"{category.value.capitalize()} hook validation failed."

    def _all_failed(
        self, applied: List[PatchProposal], reason: str
    ) -> List[HookValidationResult]:
        """Mark all applied proposals FAILED with the given reason."""
        return [
            HookValidationResult(
                hook=p.gap.hook,
                status=ValidationStatus.FAILED,
                message=reason,
            )
            for p in applied
        ]

    def _make_evidence(
        self,
        executed: bool,
        syntax_valid: bool,
        record: Optional[ExecutionRecord],
        observations: List[RuntimeObservation],
    ) -> ValidationEvidence:
        return ValidationEvidence(
            execution_mode=self._mode,
            environment_name=self._sandbox.environment_name,
            executed=executed,
            stdout=record.stdout if record else "",
            stderr=record.stderr if record else "",
            exit_code=record.exit_code if record else None,
            duration_ms=record.duration_ms if record else None,
            timed_out=record.timed_out if record else False,
            syntax_valid=syntax_valid,
            observations=observations,
        )

    @staticmethod
    def _build_report(
        agent_name: str,
        hook_results: List[HookValidationResult],
    ) -> ValidationReport:
        if not hook_results:
            overall = ValidationStatus.SKIPPED
        elif all(r.status == ValidationStatus.PASSED for r in hook_results):
            overall = ValidationStatus.PASSED
        elif any(r.status == ValidationStatus.FAILED for r in hook_results):
            overall = ValidationStatus.FAILED
        else:
            overall = ValidationStatus.SKIPPED

        return ValidationReport(
            agent_name=agent_name,
            overall_status=overall,
            hook_results=hook_results,
            generated_at=datetime.utcnow(),
        )
