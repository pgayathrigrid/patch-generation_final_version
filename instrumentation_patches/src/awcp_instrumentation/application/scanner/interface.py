from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from awcp_instrumentation.application.scanner.result import RepositoryScanResult


class AgentScanner(ABC):
    """
    Port (abstract interface) for the Repository Scanner stage.

    Any concrete scanner must implement ``scan`` and return a
    ``RepositoryScanResult``.  Downstream stages (detector, generator, etc.)
    depend only on this abstraction — never on a concrete implementation.
    """

    @abstractmethod
    def scan(self, target: Path) -> RepositoryScanResult:
        """
        Scan *target* and return all discovered Python agents.

        Args:
            target: A ``.py`` file or a directory to scan recursively.

        Returns:
            A ``RepositoryScanResult`` containing loaded agents and any errors.
        """
