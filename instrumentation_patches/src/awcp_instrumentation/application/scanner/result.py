from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from awcp_instrumentation.domain.entities.agent_source import AgentSource


@dataclass(frozen=True)
class ScanError:
    """
    Records a file that could not be loaded during a scan.

    Attributes:
        path:   Filesystem path that caused the error.
        reason: Human-readable description of why the file was skipped.
    """

    path: Path
    reason: str


@dataclass
class RepositoryScanResult:
    """
    Output of the Repository Scanner stage.

    Contains all successfully loaded agents plus any files that could not be
    read, giving callers full visibility without raising exceptions mid-scan.

    Attributes:
        target:        The path (file or directory) that was scanned.
        agents:        Successfully loaded AgentSource objects.
        scanned_files: Total number of .py files encountered.
        skipped_files: Files skipped due to exclusion patterns.
        errors:        Files that matched but could not be read.
    """

    target: Path
    agents: List[AgentSource] = field(default_factory=list)
    scanned_files: int = 0
    skipped_files: int = 0
    errors: List[ScanError] = field(default_factory=list)

    @property
    def agent_count(self) -> int:
        """Number of agents successfully loaded."""
        return len(self.agents)

    @property
    def has_errors(self) -> bool:
        """True when at least one file could not be read."""
        return len(self.errors) > 0

    @property
    def agent_names(self) -> List[str]:
        """Logical names of all discovered agents, in discovery order."""
        return [a.agent_name for a in self.agents if a.agent_name is not None]
