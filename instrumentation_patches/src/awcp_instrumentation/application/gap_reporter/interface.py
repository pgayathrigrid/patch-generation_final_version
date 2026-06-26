from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from awcp_instrumentation.application.gap_reporter.models import GovernanceGapReport
from awcp_instrumentation.domain.entities.hook_detection_result import HookDetectionResult


class GapReporter(ABC):
    """
    Port (abstract interface) for the Governance Gap Report stage.

    The Patch Generator and any other downstream consumer depends on this
    abstraction — never on the concrete ``GovernanceGapReporter``.
    """

    @abstractmethod
    def generate(self, detection_result: HookDetectionResult) -> GovernanceGapReport:
        """
        Transform a single ``HookDetectionResult`` into a ``GovernanceGapReport``.

        Args:
            detection_result: Output from the Governance Hook Detector stage.

        Returns:
            A fully populated ``GovernanceGapReport`` ready for the Patch Generator.
        """

    @abstractmethod
    def generate_all(
        self, detection_results: List[HookDetectionResult]
    ) -> List[GovernanceGapReport]:
        """
        Generate reports for a batch of detection results.

        Args:
            detection_results: One result per agent from the detector stage.

        Returns:
            One ``GovernanceGapReport`` per input result, in the same order.
        """
