"""
Sandbox stub for awcp.agent_hooks.types.

Mirrors the real HookType enum and supporting types exactly so patched agent
code can be executed in the sandbox subprocess without needing the real AWCP
control plane running.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HookType(str, Enum):
    AGENT_REGISTERED   = "agent_registered"
    AGENT_DEREGISTERED = "agent_deregistered"
    TASK_STARTED       = "task_started"
    TASK_COMPLETED     = "task_completed"
    TASK_FAILED        = "task_failed"
    STEP               = "step"
    LLM_CALL           = "llm_call"
    TOOL_CALL          = "tool_call"
    WEB_SEARCH         = "web_search"
    SYNTHESIZE         = "synthesize"
    GATE_EVALUATED     = "gate_evaluated"
    ACTION_BLOCKED     = "action_blocked"
    APPROVAL_REQUIRED  = "approval_required"
    SIGNAL_RECEIVED    = "signal_received"
    AUTONOMY_DEGRADED  = "autonomy_degraded"
    TOKEN_USAGE        = "token_usage"
    BUDGET_WARN        = "budget_warn"
    BUDGET_EXHAUSTED   = "budget_exhausted"


class HookCategory(str, Enum):
    OBSERVER = "observer"
    GUARD    = "guard"


@dataclass(frozen=True)
class HookContext:
    hook_type: HookType
    agent_id: str = ""
    task_id: str | None = None
    ts: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


@dataclass
class HookOutcome:
    decision: str = "allow"
    reason: str = ""
    note: str = ""

    @classmethod
    def allow(cls, note: str = "") -> "HookOutcome":
        return cls(decision="allow", note=note)

    @classmethod
    def deny(cls, reason: str = "") -> "HookOutcome":
        return cls(decision="deny", reason=reason)

    @property
    def is_deny(self) -> bool:
        return self.decision == "deny"
