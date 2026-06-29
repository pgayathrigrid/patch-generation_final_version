"""
Sandbox stub for awcp.agent_hooks.

Mirrors the public API of the real awcp.agent_hooks module exactly so that
patched agent code can call any of the following patterns in the sandbox
subprocess without needing the real AWCP control plane installed:

    import awcp.agent_hooks as hooks
    hooks.dispatch(HookType.TASK_STARTED, agent_id=..., task_id=...)

    from awcp.agent_hooks import get_manager, dispatch
    get_manager().dispatch(HookType.LLM_CALL, agent_id=..., task_id=...)

    from awcp.agent_hooks.types import HookType
"""
from __future__ import annotations

from typing import Any, Optional
from awcp.agent_hooks.types import HookCategory, HookContext, HookOutcome, HookType


class _StubManager:
    """No-op hook manager — matches the HookManager public interface."""

    def dispatch(
        self,
        hook_type: HookType,
        ctx: Optional[HookContext] = None,
        **data: Any,
    ) -> HookOutcome:
        print(f"[AWCP] hook dispatched: {hook_type.value}", flush=True)
        return HookOutcome.allow()

    def register(self, hook: Any) -> Any:
        return hook

    def register_fn(self, fn: Any, *, types: Any, name: Any = None,
                    category: Any = None, priority: int = 100) -> Any:
        return fn

    def unregister(self, name: str) -> bool:
        return True

    def set_enabled(self, name: str, enabled: bool) -> bool:
        return True

    def get(self, name: str) -> None:
        return None

    def list_hooks(self) -> list:
        return []

    def recent(self, limit: int = 50) -> list:
        return []

    def status(self) -> dict:
        return {"enabled": True, "hook_count": 0, "subscriptions": {}}


_manager = _StubManager()


def get_manager() -> _StubManager:
    """Return the process-wide no-op stub manager."""
    return _manager


def dispatch(
    hook_type: HookType,
    ctx: Optional[HookContext] = None,
    **data: Any,
) -> HookOutcome:
    """Module-level dispatch — thin wrapper matching real awcp.agent_hooks.dispatch()."""
    return _manager.dispatch(hook_type, ctx, **data)


def register(hook: Any) -> Any:
    return _manager.register(hook)


def register_fn(fn: Any, *, types: Any, name: Any = None,
                category: Any = None, priority: int = 100) -> Any:
    return _manager.register_fn(fn, types=types, name=name,
                                category=category, priority=priority)


def unregister(name: str) -> bool:
    return _manager.unregister(name)


def list_hooks() -> list:
    return _manager.list_hooks()


def recent(limit: int = 50) -> list:
    return _manager.recent(limit)


__all__ = [
    "get_manager",
    "dispatch",
    "register",
    "register_fn",
    "unregister",
    "list_hooks",
    "recent",
    "HookType",
    "HookCategory",
    "HookContext",
    "HookOutcome",
]
