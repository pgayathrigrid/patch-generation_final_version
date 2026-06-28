"""
Sandbox stub for awcp.agent_hooks.

Provides a no-op get_manager() so patched agent code can call
get_manager().dispatch(HookType.X, ...) in the sandbox subprocess without
needing the real AWCP control plane.
"""
from __future__ import annotations

from typing import Any
from awcp.agent_hooks.types import HookOutcome, HookType


class _StubManager:
    """No-op hook manager for sandbox execution."""

    def dispatch(self, hook_type: HookType, **data: Any) -> HookOutcome:
        return HookOutcome.allow()

    def register(self, hook: Any) -> Any:
        return hook

    def unregister(self, name: str) -> bool:
        return True

    def recent(self, limit: int = 50) -> list:
        return []

    def status(self) -> dict:
        return {"enabled": True, "hook_count": 0}


_manager = _StubManager()


def get_manager() -> _StubManager:
    return _manager
