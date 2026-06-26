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
from awcp_instrumentation.application.reporter.models import BuiltReport
from awcp_instrumentation.application.sandbox.output_pattern_collector import (
    OutputPatternCollector,
)
from awcp_instrumentation.application.sandbox.python_sandbox_validator import (
    PythonSandboxValidator,
)
from awcp_instrumentation.application.scanner.filesystem_scanner import FilesystemScanner


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
        missing_hooks:      Categories absent from the source and required by
                            the agent's detected capabilities.
        patches_applied:    Number of patch proposals successfully applied.
        patches_failed:     Number of proposals that could not be applied.
        validation_status:  ``"passed"`` / ``"failed"`` / ``"skipped"``.
        warnings:           Non-fatal issues from the sandbox validation stage.
        errors:             Fatal issues encountered during validation.
        report:             Full ``BuiltReport`` for downstream rendering.
    """

    agent_name: str
    agent_path: str
    capabilities: List[str]
    required_hooks: List[str]
    present_hooks: List[str]
    missing_hooks: List[str]
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
) -> InstrumentationResult:
    """
    Run the full AWCP instrumentation pipeline against *repository_path*.

    Args:
        repository_path: Path to a Python file or directory to analyse.
        llm_provider:    Optional ``LlmProvider`` implementation.  Defaults to
                         ``MockLlmProvider`` (no network calls).  Inject a real
                         provider (e.g. ``AnthropicProvider``) for live patching.

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

    # Stage 1 — Scan
    scan_result = scanner.scan(target)
    scan_errors = [f"{e.path}: {e.reason}" for e in scan_result.errors]

    summaries: List[AgentInstrumentationSummary] = []
    pipeline_errors: List[str] = []

    for agent in scan_result.agents:
        try:
            # Stage 2 — Capability analysis (determines which hooks are required)
            cap_result: CapabilityAnalysisResult = capability_analyzer.analyze(agent)

            # Stage 3 — Detect existing hooks
            detection = detector.detect(agent)

            # Stage 4 — Gap report (gaps scoped to capability-required hooks only)
            gap_report = reporter.generate(
                detection,
                required_categories=cap_result.required_hook_categories,
            )

            # Stage 5 — Generate targeted instrumentation patches
            generation = generator.generate(gap_report)

            # Stage 6 — Apply patches to source text
            apply_result = applier.apply(agent, generation)
            patched = apply_result.patched_source

            # Stage 7 — Validate patched code in sandbox
            validation = validator.validate(patched=patched)

            # Stage 8 — Build structured report
            report: BuiltReport = builder.build(validation)

            present = [h.category.value for h in detection.present_hooks]
            missing = [
                h.category.value for h in detection.missing_hooks
                if h.category in cap_result.required_hook_categories
            ]
            warnings = [w.message for w in report.warnings]
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
