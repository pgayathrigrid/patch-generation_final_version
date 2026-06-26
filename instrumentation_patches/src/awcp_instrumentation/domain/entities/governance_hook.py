from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from awcp_instrumentation.domain.enums.hook_category import HookCategory


@dataclass(frozen=True)
class GovernanceHook:
    """
    Represents a single governance hook — either detected in existing source
    or required by policy.

    Attributes:
        category:    Which governance category this hook belongs to.
        name:        Canonical hook name (e.g. ``"log_decision"``).
        description: Human-readable purpose of this hook.
        signature:   Optional expected call signature for validation.
        line_number: Source line where the hook was found (None if absent).
    """

    category: HookCategory
    name: str
    description: str
    signature: Optional[str] = field(default=None)
    line_number: Optional[int] = field(default=None)

    def is_present(self) -> bool:
        """Return True when the hook was found at a concrete line in source."""
        return self.line_number is not None
