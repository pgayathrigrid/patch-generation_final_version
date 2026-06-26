from __future__ import annotations

from typing import FrozenSet, List, Optional, Set, Union

from awcp_instrumentation.application.gap_reporter.interface import GapReporter
from awcp_instrumentation.application.gap_reporter.models import (
    GovernanceGap,
    GovernanceGapReport,
    GovernanceRecommendation,
    GovernanceRisk,
    RiskSeverity,
    severity_rank,
)
from awcp_instrumentation.application.gap_reporter.risk_catalog import (
    DEFAULT_RISK_CATALOG,
    RiskCatalog,
)
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.entities.hook_detection_result import HookDetectionResult
from awcp_instrumentation.domain.enums.hook_category import HookCategory


class GovernanceGapReporter(GapReporter):
    """
    Converts a ``HookDetectionResult`` into a rich ``GovernanceGapReport``.

    The reporter consults a ``RiskCatalog`` to attach governance risk and
    recommendations to each missing hook.  The catalog is injected at
    construction time so organisations can provide custom severity levels
    without subclassing.

    Args:
        catalog: Risk catalog mapping each ``HookCategory`` to a
                 ``(GovernanceRisk, GovernanceRecommendation)`` pair.
                 Defaults to ``DEFAULT_RISK_CATALOG`` when ``None``.
    """

    def __init__(self, catalog: Optional[RiskCatalog] = None) -> None:
        self._catalog: RiskCatalog = catalog if catalog is not None else DEFAULT_RISK_CATALOG

    # ------------------------------------------------------------------
    # Public API (implements GapReporter port)
    # ------------------------------------------------------------------

    def generate(
        self,
        detection_result: HookDetectionResult,
        *,
        required_categories: Optional[Union[Set[HookCategory], FrozenSet[HookCategory]]] = None,
    ) -> GovernanceGapReport:
        """
        Build a ``GovernanceGapReport`` from a single ``HookDetectionResult``.

        Args:
            detection_result:    The raw hook detection output.
            required_categories: When provided, only missing hooks whose
                                 category appears in this set are reported as
                                 gaps.  Pass the ``required_hook_categories``
                                 from a ``CapabilityAnalysisResult`` to avoid
                                 reporting hooks that the agent genuinely does
                                 not need (e.g. TOOL_CALL for a pure LLM agent).
                                 When ``None``, all missing hooks are reported.

        Missing hooks that have no entry in the catalog are still included as
        gaps but with a fallback risk/recommendation so no information is lost.
        """
        if required_categories is not None:
            filtered_missing = [
                h for h in detection_result.missing_hooks
                if h.category in required_categories
            ]
            required_count = len(required_categories)
        else:
            filtered_missing = list(detection_result.missing_hooks)
            required_count = len(HookCategory)
        gaps = self._build_gaps(filtered_missing)
        overall_risk = self._compute_overall_risk(gaps)
        summary = self._build_summary(
            agent_name=detection_result.agent.agent_name or str(detection_result.agent.path),
            present_hooks=detection_result.present_hooks,
            gaps=gaps,
            overall_risk=overall_risk,
            required_count=required_count,
        )
        return GovernanceGapReport(
            agent=detection_result.agent,
            present_hooks=list(detection_result.present_hooks),
            gaps=gaps,
            overall_risk_level=overall_risk,
            summary=summary,
            metadata={
                "agent_path": str(detection_result.agent.path),
                "generated_by": "GovernanceGapReporter",
            },
        )

    def generate_all(
        self,
        detection_results: List[HookDetectionResult],
        *,
        required_categories: Optional[Union[Set[HookCategory], FrozenSet[HookCategory]]] = None,
    ) -> List[GovernanceGapReport]:
        """Generate one report per detection result, preserving list order."""
        return [self.generate(r, required_categories=required_categories) for r in detection_results]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_gaps(self, missing_hooks: List[GovernanceHook]) -> List[GovernanceGap]:
        """
        Create a ``GovernanceGap`` for each missing hook.

        Gaps are sorted by descending severity then ascending priority so the
        most urgent items appear first in the report.
        """
        gaps: List[GovernanceGap] = []
        for hook in missing_hooks:
            risk, recommendation = self._lookup(hook.category)
            gaps.append(GovernanceGap(hook=hook, risk=risk, recommendation=recommendation))

        return sorted(
            gaps,
            key=lambda g: (-severity_rank(g.severity), g.recommendation.priority),
        )

    def _lookup(
        self, category: HookCategory
    ) -> tuple[GovernanceRisk, GovernanceRecommendation]:
        """
        Return the ``(risk, recommendation)`` for *category* from the catalog.

        Falls back to a MEDIUM risk entry for categories not in the catalog so
        that custom or future categories are never silently dropped.
        """
        if category in self._catalog:
            return self._catalog[category]
        return (
            GovernanceRisk(
                severity=RiskSeverity.MEDIUM,
                description=f"No catalog entry found for category '{category.value}'.",
                impact="Risk cannot be assessed without a catalog entry.",
            ),
            GovernanceRecommendation(
                action=f"Add governance instrumentation for '{category.value}' hooks.",
                rationale="This category is not yet covered by the risk catalog.",
                instrumentation_hint=(
                    f"Insert a '{category.value}' governance hook at the appropriate "
                    "point in the agent's execution flow."
                ),
                priority=5,
            ),
        )

    @staticmethod
    def _compute_overall_risk(gaps: List[GovernanceGap]) -> RiskSeverity:
        """Return the highest severity across all gaps, or NONE if there are none."""
        if not gaps:
            return RiskSeverity.NONE
        return max(gaps, key=lambda g: severity_rank(g.severity)).severity

    @staticmethod
    def _build_summary(
        agent_name: str,
        present_hooks: List[GovernanceHook],
        gaps: List[GovernanceGap],
        overall_risk: RiskSeverity,
        required_count: int = 0,
    ) -> str:
        """Build a concise human-readable summary paragraph for the report."""
        if required_count == 0:
            required_count = len(HookCategory)
        present_count = len({h.category for h in present_hooks})
        gap_count = len(gaps)

        if gap_count == 0:
            return (
                f"Agent '{agent_name}' is fully instrumented: all "
                f"{required_count} required AWCP lifecycle hook categories present. "
                f"No patching is required."
            )

        critical = [g for g in gaps if g.severity == RiskSeverity.CRITICAL]
        high = [g for g in gaps if g.severity == RiskSeverity.HIGH]

        severity_line = f"Overall risk: {overall_risk.value.upper()}."

        if critical:
            cat_names = ", ".join(g.category.value for g in critical)
            severity_line += f" Critical gaps: {cat_names}."

        if high:
            cat_names = ", ".join(g.category.value for g in high)
            severity_line += f" High-severity gaps: {cat_names}."

        top_actions = "; ".join(g.recommendation.action for g in gaps[:3])
        if len(gaps) > 3:
            top_actions += f" (and {len(gaps) - 3} more)"

        return (
            f"Agent '{agent_name}' has {gap_count} of {required_count} "
            f"required AWCP lifecycle hook categories missing "
            f"({present_count} present). "
            f"{severity_line} "
            f"Recommended actions: {top_actions}."
        )
