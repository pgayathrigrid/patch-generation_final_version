"""
Concrete report builder: ValidationReportBuilder.

Assembles a ``BuiltReport`` from a ``SandboxValidationResult`` by extracting
and flattening information from every layer of the pipeline result:

    SandboxValidationResult
        ├── patched_source_ref (PatchedSource)
        │       ├── original_agent          → AgentInfo
        │       └── applied_proposals       → HookRecommendation (for failed hooks)
        ├── report (ValidationReport)       → HookResult, counts
        ├── evidence (ValidationEvidence)   → ExecutionSummary, ObservationSummary
        ├── errors                          → ReportError
        └── warnings                        → ReportWarning

Recommendation extraction
~~~~~~~~~~~~~~~~~~~~~~~~~
For every hook whose ``HookValidationResult.status`` is FAILED, the builder
searches ``applied_proposals`` for a proposal whose ``gap.hook.category``
matches.  If found, the ``GovernanceGap.recommendation`` and
``GovernanceGap.risk`` are used to build a ``HookRecommendation``.  When no
matching proposal is found (edge case), a generic placeholder is inserted so
the failed hook always has a recommendation entry.

Missing hooks
~~~~~~~~~~~~~
``BuiltReport.missing_hooks`` lists the category value strings of every hook
that is FAILED in the ``ValidationReport`` — hooks that are still effectively
unaddressed from a governance perspective after the patching attempt.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from awcp_instrumentation.application.generator.models import PatchProposal
from awcp_instrumentation.application.reporter.interface import ReportBuilder
from awcp_instrumentation.application.reporter.models import (
    AgentInfo,
    BuiltReport,
    ExecutionSummary,
    HookRecommendation,
    HookResult,
    ObservationSummary,
    ReportError,
    ReportWarning,
)
from awcp_instrumentation.application.sandbox.models import SandboxValidationResult
from awcp_instrumentation.domain.enums.validation_status import ValidationStatus

# Maximum characters to include in stdout/stderr excerpts.
_EXCERPT_LIMIT = 500


class ValidationReportBuilder(ReportBuilder):
    """
    Builds a ``BuiltReport`` from a ``SandboxValidationResult``.

    Stateless: ``build()`` can be called multiple times safely.
    """

    def build(self, result: SandboxValidationResult) -> BuiltReport:
        """Assemble and return a ``BuiltReport``."""
        agent = self._build_agent_info(result)
        execution_summary = self._build_execution_summary(result)
        hook_results = self._build_hook_results(result)
        missing_hooks = self._build_missing_hooks(result)
        observations = self._build_observations(result)
        errors = self._build_errors(result)
        warnings = self._build_warnings(result)
        recommendations = self._build_recommendations(result)

        passed = len(result.report.passed)
        failed = len(result.report.failed)
        skipped = len(result.report.skipped)
        total = len(result.report.hook_results)
        summary = self._build_summary(
            overall_status=result.report.overall_status.value,
            passed=passed,
            failed=failed,
            skipped=skipped,
            total=total,
            execution_summary=execution_summary,
        )

        return BuiltReport(
            agent=agent,
            generated_at=result.generated_at,
            overall_status=result.report.overall_status.value,
            execution_summary=execution_summary,
            hook_results=hook_results,
            missing_hooks=missing_hooks,
            observations=observations,
            errors=errors,
            warnings=warnings,
            recommendations=recommendations,
            summary=summary,
            total_hooks=total,
            passed_hooks=passed,
            failed_hooks=failed,
            skipped_hooks=skipped,
        )

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    @staticmethod
    def _build_agent_info(result: SandboxValidationResult) -> AgentInfo:
        agent = result.patched_source_ref.original_agent
        path = str(agent.path) if agent.path else None
        return AgentInfo(name=agent.agent_name or "unknown", path=path)

    @staticmethod
    def _build_execution_summary(result: SandboxValidationResult) -> ExecutionSummary:
        ev = result.evidence
        return ExecutionSummary(
            mode=ev.execution_mode.value,
            environment=ev.environment_name,
            executed=ev.executed,
            duration_ms=ev.duration_ms,
            exit_code=ev.exit_code,
            timed_out=ev.timed_out,
            syntax_valid=ev.syntax_valid,
            stdout_excerpt=ev.stdout[:_EXCERPT_LIMIT],
            stderr_excerpt=ev.stderr[:_EXCERPT_LIMIT],
        )

    @staticmethod
    def _build_hook_results(result: SandboxValidationResult) -> List[HookResult]:
        return [
            HookResult(
                category=r.hook.category.value,
                hook_name=r.hook.name,
                status=r.status.value,
                message=r.message,
                stdout=r.stdout,
                stderr=r.stderr,
            )
            for r in result.report.hook_results
        ]

    @staticmethod
    def _build_missing_hooks(result: SandboxValidationResult) -> List[str]:
        return [
            r.hook.category.value
            for r in result.report.hook_results
            if r.status == ValidationStatus.FAILED
        ]

    @staticmethod
    def _build_observations(result: SandboxValidationResult) -> List[ObservationSummary]:
        return [
            ObservationSummary(
                category=obs.category.value,
                hook_name=obs.hook_name,
                observed=obs.observed,
                collector=obs.collector_name,
                stdout_excerpt=obs.stdout_excerpt,
                stderr_excerpt=obs.stderr_excerpt,
            )
            for obs in result.evidence.observations
        ]

    @staticmethod
    def _build_errors(result: SandboxValidationResult) -> List[ReportError]:
        return [
            ReportError(
                category=e.category.value,
                error_type=e.error_type,
                message=e.message,
                traceback=e.traceback,
            )
            for e in result.errors
        ]

    @staticmethod
    def _build_warnings(result: SandboxValidationResult) -> List[ReportWarning]:
        return [
            ReportWarning(category=w.category.value, message=w.message)
            for w in result.warnings
        ]

    @staticmethod
    def _build_recommendations(result: SandboxValidationResult) -> List[HookRecommendation]:
        failed_results = [
            r for r in result.report.hook_results
            if r.status == ValidationStatus.FAILED
        ]
        if not failed_results:
            return []

        # Build a lookup: category → proposal
        proposal_by_category: Dict[str, PatchProposal] = {}
        for proposal in result.patched_source_ref.applied_proposals:
            proposal_by_category[proposal.category.value] = proposal

        recommendations: List[HookRecommendation] = []
        for hook_result in failed_results:
            cat_value = hook_result.hook.category.value
            proposal = proposal_by_category.get(cat_value)

            if proposal:
                rec = proposal.gap.recommendation
                risk = proposal.gap.risk
                recommendations.append(
                    HookRecommendation(
                        category=cat_value,
                        hook_name=hook_result.hook.name,
                        action=rec.action,
                        rationale=rec.rationale,
                        hint=rec.instrumentation_hint,
                        priority=rec.priority,
                        severity=risk.severity.value,
                    )
                )
            else:
                # Fallback: no proposal found for this failed hook
                recommendations.append(
                    HookRecommendation(
                        category=cat_value,
                        hook_name=hook_result.hook.name,
                        action=f"Add {cat_value} governance hook.",
                        rationale="Hook failed sandbox validation.",
                        hint="Review and re-apply the instrumentation patch.",
                        priority=1,
                        severity="high",
                    )
                )

        return sorted(recommendations, key=lambda r: (r.priority, r.category))

    @staticmethod
    def _build_summary(
        overall_status: str,
        passed: int,
        failed: int,
        skipped: int,
        total: int,
        execution_summary: ExecutionSummary,
    ) -> str:
        status_upper = overall_status.upper()
        parts = [f"Validation {status_upper}: {passed}/{total} hooks passed"]
        if failed:
            parts.append(f"{failed} failed")
        if skipped:
            parts.append(f"{skipped} skipped")
        if execution_summary.executed and execution_summary.duration_ms is not None:
            parts.append(f"Runtime: {execution_summary.duration_ms:.0f}ms")
        if execution_summary.timed_out:
            parts.append("TIMED OUT")
        return " | ".join(parts)
