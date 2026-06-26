"""
Abstract port: EvidenceCollector.

Defines the contract for collecting runtime observations from a
``ExecutionRecord`` produced by a ``SandboxEnvironment``.

Evidence collection is deliberately separated from execution so that:
1.  Multiple collectors can be composed (pass a ``List[EvidenceCollector]``
    to ``PythonSandboxValidator``).
2.  Future AWCP environments can provide richer evidence streams (traces,
    structured logs, metrics) through specialised collector implementations
    without changing the validator.

Concrete implementations
------------------------
OutputPatternCollector  (output_pattern_collector.py)
    Searches stdout and stderr for category-specific text patterns.

[future] StructuredLogCollector
    Parses JSON log lines emitted by the agent.

[future] TraceCollector
    Reads OpenTelemetry spans from ``ExecutionRecord.metadata["spans"]``
    (populated by a CodeActSandbox).

[future] MetricsCollector
    Reads Prometheus-style counters from ``ExecutionRecord.metadata["metrics"]``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from awcp_instrumentation.application.generator.models import PatchProposal
from awcp_instrumentation.application.sandbox.models import (
    ExecutionRecord,
    RuntimeObservation,
)


class EvidenceCollector(ABC):
    """
    Port: extracts ``RuntimeObservation`` objects from an ``ExecutionRecord``.

    Each call to ``collect`` inspects the raw execution artefacts and returns
    one observation per applied proposal (one per governance hook category).
    Collectors that have no signal for a hook still return an observation with
    ``observed=False`` so callers always receive a complete set.
    """

    @abstractmethod
    def collect(
        self,
        record: ExecutionRecord,
        applied_proposals: List[PatchProposal],
    ) -> List[RuntimeObservation]:
        """
        Inspect *record* and return one ``RuntimeObservation`` per proposal.

        Args:
            record:            Raw artefacts from ``SandboxEnvironment.execute()``.
            applied_proposals: The proposals that were successfully applied to
                               the patched source.  Each proposal identifies a
                               hook category and name.

        Returns:
            A list of ``RuntimeObservation`` objects.  Length should equal
            ``len(applied_proposals)`` so callers can correlate them by index
            or by category.
        """

    @property
    @abstractmethod
    def collector_name(self) -> str:
        """
        Short identifier for this collector (e.g. ``"output_pattern"``).

        Stored in each ``RuntimeObservation.collector_name`` for traceability.
        """
