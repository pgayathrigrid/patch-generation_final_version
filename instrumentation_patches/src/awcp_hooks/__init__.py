"""
Backward-compatibility shim — the real integration surface is awcp.agent_hooks.

Agents should import directly:
    from awcp.agent_hooks import get_manager
    from awcp.agent_hooks.types import HookType
    get_manager().dispatch(HookType.TASK_STARTED, agent_id=..., task_id=...)
"""
from awcp.agent_hooks import get_manager
from awcp.agent_hooks.types import HookContext, HookOutcome, HookType

__all__ = ["get_manager", "HookType", "HookContext", "HookOutcome"]
