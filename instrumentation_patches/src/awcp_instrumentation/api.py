"""
Public API for the AWCP Instrumentation engine.

Usage::

    from awcp_instrumentation import run_instrumentation, InstrumentationResult

    result = run_instrumentation("/path/to/agent/repo")
    for agent in result.agents:
        print(agent.agent_name, agent.validation_status)

Pipeline::

    FilesystemScanner
        → AstCapabilityAnalyzer       (infers what each agent does)
        → RuleBasedHookDetector       (detects existing AWCP hooks)
        → GovernanceGapReporter       (reports gaps scoped to required hooks)
        → LlmPatchGenerator           (generates targeted patch proposals)
        → SourcePatchApplier          (applies proposals to source text)
        → PythonSandboxValidator      (validates patched code in subprocess)
        → ValidationReportBuilder     (assembles the final report)

No external services are required.  Inject a real ``LlmProvider`` for live
patch generation; the default ``MockLlmProvider`` requires no network access.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from awcp_instrumentation.application.applicator.patch_applier import SourcePatchApplier
from awcp_instrumentation.application.capability_analyzer.ast_capability_analyzer import (
    AstCapabilityAnalyzer,
)
from awcp_instrumentation.application.capability_analyzer.models import CapabilityAnalysisResult
from awcp_instrumentation.application.detector.hook_detector import RuleBasedHookDetector
from awcp_instrumentation.application.gap_reporter.gap_reporter import GovernanceGapReporter
from awcp_instrumentation.application.generator.patch_generator import LlmPatchGenerator
from awcp_instrumentation.application.generator.providers.mock_provider import MockLlmProvider
from awcp_instrumentation.application.reporter.builder import ValidationReportBuilder
from awcp_instrumentation.application.reporter.models import (
    AgentInfo,
    BuiltReport,
    ExecutionSummary,
)
from awcp_instrumentation.application.sandbox.output_pattern_collector import (
    OutputPatternCollector,
)
from awcp_instrumentation.application.sandbox.python_sandbox_validator import (
    PythonSandboxValidator,
)
from awcp_instrumentation.application.scanner.filesystem_scanner import FilesystemScanner

try:
    # When running as part of AWCP, use its fully-configured OTel tracer so that
    # the instrumentation pipeline stages appear in the shared Tempo trace.
    from awcp.observability.setup import get_tracer as _awcp_get_tracer

    def get_tracer():  # type: ignore[misc]
        return _awcp_get_tracer("awcp.instrumentation")

except Exception:  # pragma: no cover
    from contextlib import contextmanager
    from typing import Generator, Any as _Any

    class _NoOpSpan:
        def set_attribute(self, k: str, v: _Any) -> None: pass
        def record_exception(self, e: Exception) -> None: pass
        def __enter__(self) -> "_NoOpSpan": return self
        def __exit__(self, *_: _Any) -> None: pass

    class _NoOpTracer:
        @contextmanager
        def start_as_current_span(self, name: str, **_kw: _Any) -> Generator[_NoOpSpan, None, None]:
            yield _NoOpSpan()

    def get_tracer() -> _NoOpTracer:  # type: ignore[misc]
        return _NoOpTracer()


# Hook categories whose absence blocks AWCP quarantine exit.
# Derived from onboarding.decide_status(): only OBSERVABILITY, FEATURE_FLAG,
# and POLICY gates are evaluated before an agent is allowed to leave quarantine.
_QUARANTINE_BLOCKING_CATEGORIES: frozenset = frozenset(
    {"observability", "feature_flag", "policy"}
)


# ---------------------------------------------------------------------------
# Public result types
# ---------------------------------------------------------------------------

@dataclass
class AgentInstrumentationSummary:
    """
    Per-agent instrumentation outcome — the primary integration surface with AWCP.

    All list fields contain plain strings so this object can be serialised to
    JSON without any domain-layer imports on the consumer side.

    Attributes:
        agent_name:         Logical name derived from the file stem.
        agent_path:         Absolute path to the agent file.
        capabilities:       Inferred ``AgentCapability`` value strings (e.g.
                            ``["llm_agent", "search_agent"]``).  Empty when the
                            engine could not detect any recognisable patterns.
        required_hooks:     AWCP lifecycle hook categories required for this
                            agent given its detected capabilities.
        present_hooks:      Lifecycle categories already found in the source
                            before any patching.
        missing_hooks:         Categories absent from the source and required by
                               the agent's detected capabilities.
        quarantine_blockers:   Subset of ``missing_hooks`` that directly gates
                               AWCP quarantine exit (observability, feature_flag,
                               policy).  Empty means the agent can exit quarantine
                               even with other hooks still missing.
        patches_applied:       Number of patch proposals successfully applied.
        patches_failed:        Number of proposals that could not be applied.
        validation_status:     ``"passed"`` / ``"failed"`` / ``"skipped"``.
        warnings:              Non-fatal issues from the sandbox validation stage.
        errors:                Fatal issues encountered during validation.
        report:                Full ``BuiltReport`` for downstream rendering.
    """

    agent_name: str
    agent_path: str
    capabilities: List[str]
    required_hooks: List[str]
    present_hooks: List[str]
    missing_hooks: List[str]
    quarantine_blockers: List[str]
    patches_applied: int
    patches_failed: int
    validation_status: str
    warnings: List[str]
    errors: List[str]
    report: BuiltReport

    @property
    def success(self) -> bool:
        """True when sandbox validation passed for this agent."""
        return self.validation_status == "passed"

    @property
    def is_fully_instrumented(self) -> bool:
        """True when no required hooks are missing."""
        return len(self.missing_hooks) == 0


@dataclass
class InstrumentationResult:
    """
    Top-level result returned by :func:`run_instrumentation`.

    This object is the planned integration interface with AWCP — it contains
    everything a control-plane consumer needs without requiring access to any
    internal pipeline type.

    Attributes:
        repository_path:    Absolute path that was scanned.
        scanned_files:      Total ``.py`` files encountered during scanning.
        agents_processed:   Agents that completed the full pipeline.
        agents:             Per-agent summaries in file-discovery order.
        scan_errors:        Files that could not be read during scanning.
        pipeline_errors:    Unexpected errors during per-agent pipeline stages.
        generated_at:       UTC timestamp of when the result was produced.
    """

    repository_path: str
    scanned_files: int
    agents_processed: int
    agents: List[AgentInstrumentationSummary] = field(default_factory=list)
    scan_errors: List[str] = field(default_factory=list)
    pipeline_errors: List[str] = field(default_factory=list)
    generated_at: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )

    # ------------------------------------------------------------------
    # Status properties
    # ------------------------------------------------------------------

    @property
    def success(self) -> bool:
        """True when every agent passed sandbox validation with no pipeline errors."""
        return (
            bool(self.agents)
            and not self.pipeline_errors
            and all(a.success for a in self.agents)
        )

    @property
    def is_fully_instrumented(self) -> bool:
        """True when every agent passed sandbox validation."""
        return bool(self.agents) and all(
            a.validation_status == "passed" for a in self.agents
        )

    # ------------------------------------------------------------------
    # Aggregate counts
    # ------------------------------------------------------------------

    @property
    def total_missing_hooks(self) -> int:
        """Total missing-hook count across all agents."""
        return sum(len(a.missing_hooks) for a in self.agents)

    @property
    def total_patches_applied(self) -> int:
        """Total proposals applied across all agents."""
        return sum(a.patches_applied for a in self.agents)

    @property
    def total_warnings(self) -> int:
        """Total non-fatal warnings across all agents."""
        return sum(len(a.warnings) for a in self.agents)

    @property
    def total_errors(self) -> int:
        """Total fatal validation errors across all agents."""
        return sum(len(a.errors) for a in self.agents)

    # ------------------------------------------------------------------
    # AWCP quarantine blockers
    # ------------------------------------------------------------------

    @property
    def quarantine_blockers(self) -> List[str]:
        """Union of per-agent quarantine blockers (unique, stable order).

        Categories in this list must be present before any agent can exit
        AWCP quarantine.  An empty list means no agent is blocked on
        observability, feature_flag, or policy grounds.
        """
        seen: set = set()
        result: List[str] = []
        for a in self.agents:
            for h in a.quarantine_blockers:
                if h not in seen:
                    seen.add(h)
                    result.append(h)
        return result

    # ------------------------------------------------------------------
    # Patch bundle
    # ------------------------------------------------------------------

    @property
    def patch_bundle(self) -> str:
        """Combined unified diff across all agents.

        Concatenates the per-agent ``patch_diff`` strings from the
        instrumentation reports.  Suitable for attaching to a PR or CI
        review step (AWCP Operating Model Step 06).  Empty when no
        patches were generated.
        """
        parts = [a.report.patch_diff for a in self.agents if a.report.patch_diff]
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Repository summary
    # ------------------------------------------------------------------

    @property
    def repository_summary(self) -> str:
        """One-line human-readable summary of the instrumentation run."""
        if not self.agents:
            return (
                f"No agents found in {self.repository_path} "
                f"({self.scanned_files} files scanned)."
            )
        passed = sum(1 for a in self.agents if a.success)
        total = len(self.agents)
        missing = self.total_missing_hooks
        patches = self.total_patches_applied
        return (
            f"{self.repository_path}: {total} agent(s) processed, "
            f"{passed}/{total} passed validation, "
            f"{missing} hook(s) missing, "
            f"{patches} patch(es) applied."
        )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_instrumentation(
    repository_path: str,
    *,
    llm_provider: Optional[object] = None,
    dry_run: bool = False,
) -> InstrumentationResult:
    """
    Run the AWCP instrumentation pipeline against *repository_path*.

    Args:
        repository_path: Path to a Python file or directory to analyse.
        llm_provider:    Optional ``LlmProvider`` implementation.  Defaults to
                         ``MockLlmProvider`` (no network calls).  Inject a real
                         provider (e.g. ``AnthropicProvider``) for live patching.
        dry_run:         When ``True``, Stages 7-8 (sandbox validation and full
                         report building) are skipped.  Each agent summary gets
                         ``validation_status="skipped"`` and the report contains
                         only the patch diff.  Use this to preview generated
                         patches without executing untrusted code.

    Returns:
        ``InstrumentationResult`` with per-agent summaries and aggregate stats.

    Raises:
        ValueError: If *repository_path* does not exist.
    """
    target = Path(repository_path).resolve()
    if not target.exists():
        raise ValueError(f"repository_path does not exist: {target}")

    provider = llm_provider if llm_provider is not None else MockLlmProvider()

    # Wire the pipeline — all concrete implementations injected here.
    scanner = FilesystemScanner()
    capability_analyzer = AstCapabilityAnalyzer()
    detector = RuleBasedHookDetector()
    reporter = GovernanceGapReporter()
    generator = LlmPatchGenerator(llm_provider=provider)
    applier = SourcePatchApplier()
    validator = PythonSandboxValidator(collectors=[OutputPatternCollector()])
    builder = ValidationReportBuilder()

    tracer = get_tracer()

    # Stage 1 — Scan
    with tracer.start_as_current_span("awcp.instrumentation.scan") as span:
        scan_result = scanner.scan(target)
        span.set_attribute("scanned_files", scan_result.scanned_files)
    scan_errors = [f"{e.path}: {e.reason}" for e in scan_result.errors]

    summaries: List[AgentInstrumentationSummary] = []
    pipeline_errors: List[str] = []

    for agent in scan_result.agents:
        agent_name = agent.agent_name or str(agent.path)
        try:
            with tracer.start_as_current_span("awcp.instrumentation.agent") as agent_span:
                agent_span.set_attribute("agent.name", agent_name)

                # Stage 2 — Capability analysis (determines which hooks are required)
                with tracer.start_as_current_span("awcp.instrumentation.capability_analysis"):
                    cap_result: CapabilityAnalysisResult = capability_analyzer.analyze(agent)

                # Stage 3 — Detect existing hooks
                with tracer.start_as_current_span("awcp.instrumentation.detect"):
                    detection = detector.detect(agent)

                # Stage 4 — Gap report (gaps scoped to capability-required hooks only)
                with tracer.start_as_current_span("awcp.instrumentation.gap_report") as gs:
                    gap_report = reporter.generate(
                        detection,
                        required_categories=cap_result.required_hook_categories,
                    )
                    gs.set_attribute("gap_count", len(gap_report.gaps))

                # Stage 5 — Generate targeted instrumentation patches
                with tracer.start_as_current_span("awcp.instrumentation.generate"):
                    generation = generator.generate(gap_report)

                # Stage 6 — Apply patches to source text
                with tracer.start_as_current_span("awcp.instrumentation.apply"):
                    apply_result = applier.apply(agent, generation)
                patched = apply_result.patched_source
                redetect_warnings: List[str] = []

                # Stage 6.5 — Re-detect on patched source to confirm hooks landed
                if patched.has_changes and patched.applied_proposals:
                    with tracer.start_as_current_span("awcp.instrumentation.redetect"):
                        patched_detection = detector.detect(patched.as_agent_source)
                    detected_cats = {h.category for h in patched_detection.present_hooks}
                    for proposal in patched.applied_proposals:
                        if proposal.category not in detected_cats:
                            redetect_warnings.append(
                                f"Hook '{proposal.category.value}' was applied but "
                                "is not detectable in the patched source — "
                                "the patch may have been inserted in an unreachable location."
                            )

                if dry_run:
                    # Stages 7-8 skipped — produce a minimal report from the
                    # in-memory patch only; no subprocess is spawned.
                    report: BuiltReport = BuiltReport(
                        agent=AgentInfo(name=agent_name, path=str(agent.path)),
                        generated_at=datetime.now(tz=timezone.utc),
                        overall_status="skipped",
                        execution_summary=ExecutionSummary(
                            mode="dry_run",
                            environment="none",
                            executed=False,
                            duration_ms=None,
                            exit_code=None,
                            timed_out=False,
                            syntax_valid=True,
                            stdout_excerpt="",
                            stderr_excerpt="",
                        ),
                        patch_diff=patched.diff,
                        summary="Dry-run: sandbox validation skipped.",
                    )
                else:
                    # Stage 7 — Validate patched code in sandbox
                    with tracer.start_as_current_span("awcp.instrumentation.validate"):
                        validation = validator.validate(patched=patched)

                    # Stage 8 — Build structured report
                    with tracer.start_as_current_span("awcp.instrumentation.report"):
                        report = builder.build(validation)

            present = [h.category.value for h in detection.present_hooks]
            missing = [
                h.category.value for h in detection.missing_hooks
                if h.category in cap_result.required_hook_categories
            ]
            quarantine_blockers = [
                h for h in missing if h in _QUARANTINE_BLOCKING_CATEGORIES
            ]
            warnings = [w.message for w in report.warnings] + redetect_warnings
            errors = [
                f"{e.error_type}: {e.message}" for e in report.errors
            ]

            summaries.append(
                AgentInstrumentationSummary(
                    agent_name=agent.agent_name or str(agent.path),
                    agent_path=str(agent.path),
                    capabilities=cap_result.capability_names,
                    required_hooks=cap_result.required_hook_names,
                    present_hooks=present,
                    missing_hooks=missing,
                    quarantine_blockers=quarantine_blockers,
                    patches_applied=len(patched.applied_proposals),
                    patches_failed=len(patched.errors),
                    validation_status=report.overall_status,
                    warnings=warnings,
                    errors=errors,
                    report=report,
                )
            )

        except Exception as exc:  # noqa: BLE001
            pipeline_errors.append(
                f"{agent.agent_name or agent.path}: {type(exc).__name__}: {exc}"
            )

    return InstrumentationResult(
        repository_path=str(target),
        scanned_files=scan_result.scanned_files,
        agents_processed=len(summaries),
        agents=summaries,
        scan_errors=scan_errors,
        pipeline_errors=pipeline_errors,
    )
