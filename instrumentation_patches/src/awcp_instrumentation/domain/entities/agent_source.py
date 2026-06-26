from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class AgentSource:
    """
    Represents a Python agent file submitted for governance instrumentation.

    Attributes:
        path:        Filesystem path to the agent module.
        source_code: Raw Python source text.
        agent_name:  Logical name for the agent (defaults to the file stem).
    """

    path: Path
    source_code: str
    agent_name: Optional[str] = field(default=None)

    def __post_init__(self) -> None:
        if self.agent_name is None:
            self.agent_name = self.path.stem

    @classmethod
    def from_path(cls, path: Path) -> "AgentSource":
        """Load an AgentSource directly from a file on disk."""
        return cls(path=path, source_code=path.read_text(encoding="utf-8"))

    @classmethod
    def from_string(cls, source_code: str, name: str = "inline_agent") -> "AgentSource":
        """Create an AgentSource from a raw source string (useful in tests)."""
        return cls(path=Path(f"{name}.py"), source_code=source_code, agent_name=name)
