"""
Data models for the Governance Gap Report.

These are application-layer value objects that enrich the raw detection
results with governance semantics: risk levels, actionable recommendations,
and instrumentation hints for the downstream LLM Patch Generator.

The domain layer is NOT modified — all new types live here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory


# ---------------------------------------------------------------------------
# RiskSeverity
# ---------------------------------------------------------------------------

class RiskSeverity(str, Enum):
    """
    Five-level governance risk severity scale.

    Ordered lowest-to-highest: NONE < LOW < MEDIUM < HIGH < CRITICAL.
    String values are used so the enum serialises cleanly to JSON / YAML.
    """

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Explicit rank mapping so severities can be compared without using int values.
_SEVERITY_RANK: Dict[RiskSeverity, int] = {
    RiskSeverity.NONE: 0,
    RiskSeverity.LOW: 1,
    RiskSeverity.MEDIUM: 2,
    RiskSeverity.HIGH: 3,
    RiskSeverity.CRITICAL: 4,
}


def severity_rank(s: RiskSeverity) -> int:
    """Return a numeric rank for *s* suitable for sorting (higher = worse)."""
    return _SEVERITY_RANK[s]


# ---------------------------------------------------------------------------
# GovernanceRisk
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GovernanceRisk:
    """
    Describes the governance risk introduced by the absence of a hook.

    Attributes:
        severity:    How serious this gap is on the NONE–CRITICAL scale.
        description: One-sentence description of the risk itself.
        impact:      What can go wrong at runtime if this hook is absent.
    """

    severity: RiskSeverity
    description: str
    impact: str


# ---------------------------------------------------------------------------
# GovernanceRecommendation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GovernanceRecommendation:
    """
    Actionable guidance for closing a governance gap.

    Attributes:
        action:               Short imperative statement of what to do.
        rationale:            Why this action is required.
        instrumentation_hint: High-level natural-language cue consumed by the
                              LLM Patch Generator.  Must NOT contain code.
                              Describes the *intent* of the instrumentation so
                              the generator can produce context-appropriate code.
        priority:             Urgency relative to other gaps (1 = most urgent).
    """

    action: str
    rationale: str
    instrumentation_hint: str
    priority: int


# ---------------------------------------------------------------------------
# GovernanceGap
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GovernanceGap:
    """
    A single missing governance hook together with its risk and remedy.

    ``GovernanceGap`` is the unit of work for the Patch Generator: everything
    it needs to know about one missing hook is contained in this object.

    Attributes:
        hook:           The missing ``GovernanceHook`` as defined by the
                        detector (``line_number`` is always ``None`` here
                        because the hook was *not* found in the source).
        risk:           The governance risk this absence introduces.
        recommendation: What should be added and how the LLM should approach it.
    """

    hook: GovernanceHook
    risk: GovernanceRisk
    recommendation: GovernanceRecommendation

    @property
    def category(self) -> HookCategory:
        """Convenience accessor — the hook's governance category."""
        return self.hook.category

    @property
    def severity(self) -> RiskSeverity:
        """Convenience accessor — the gap's risk severity."""
        return self.risk.severity


# ---------------------------------------------------------------------------
# GovernanceGapReport
# ---------------------------------------------------------------------------

@dataclass
class GovernanceGapReport:
    """
    The complete governance gap report for a single agent.

    This is the sole input to the LLM Patch Generator.  It contains all
    information needed to decide *what* to instrument and *why*, without
    any reference to the original AST or raw detection results.

    Attributes:
        agent:              The agent that was analysed.
        present_hooks:      Hooks already present (for reference / transparency).
        gaps:               One ``GovernanceGap`` per missing hook, ordered by
                            descending severity then ascending priority.
        overall_risk_level: The highest severity among all gaps, or ``NONE``
                            when the agent is fully instrumented.
        summary:            Human-readable one-paragraph executive summary.
        generated_at:       UTC timestamp of report creation.
        metadata:           Arbitrary key/value pairs for downstream traceability.
    """

    agent: AgentSource
    present_hooks: List[GovernanceHook]
    gaps: List[GovernanceGap]
    overall_risk_level: RiskSeverity
    summary: str
    generated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, str] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def is_fully_instrumented(self) -> bool:
        """True when there are no governance gaps."""
        return len(self.gaps) == 0

    @property
    def ready_for_patching(self) -> bool:
        """
        True when the report contains gaps that the Patch Generator should
        address.  An agent that is already fully instrumented returns False
        because there is nothing to patch.
        """
        return len(self.gaps) > 0

    @property
    def present_count(self) -> int:
        """Number of governance hooks already present in the agent."""
        return len(self.present_hooks)

    @property
    def gap_count(self) -> int:
        """Number of governance hooks that are missing."""
        return len(self.gaps)

    @property
    def critical_gaps(self) -> List[GovernanceGap]:
        """Gaps with ``CRITICAL`` severity."""
        return [g for g in self.gaps if g.severity == RiskSeverity.CRITICAL]

    @property
    def high_gaps(self) -> List[GovernanceGap]:
        """Gaps with ``HIGH`` severity."""
        return [g for g in self.gaps if g.severity == RiskSeverity.HIGH]

    @property
    def gaps_by_severity(self) -> Dict[RiskSeverity, List[GovernanceGap]]:
        """All gaps grouped by their risk severity, ordered worst-first."""
        result: Dict[RiskSeverity, List[GovernanceGap]] = {}
        for gap in self.gaps:
            result.setdefault(gap.severity, []).append(gap)
        return result

    @property
    def missing_categories(self) -> List[HookCategory]:
        """Categories of all missing hooks, in gap list order."""
        return [g.category for g in self.gaps]

    @property
    def present_categories(self) -> List[HookCategory]:
        """Distinct categories of hooks already present."""
        return list({h.category for h in self.present_hooks})

    @property
    def gaps_ordered_by_priority(self) -> List[GovernanceGap]:
        """
        Gaps sorted by ascending recommendation priority (1 = patch first),
        with severity as the tiebreaker (higher severity first).
        """
        return sorted(
            self.gaps,
            key=lambda g: (g.recommendation.priority, -severity_rank(g.severity)),
        )

    def gap_for_category(self, category: HookCategory) -> Optional[GovernanceGap]:
        """Return the ``GovernanceGap`` for *category*, or ``None`` if not missing."""
        for gap in self.gaps:
            if gap.category == category:
                return gap
        return None
