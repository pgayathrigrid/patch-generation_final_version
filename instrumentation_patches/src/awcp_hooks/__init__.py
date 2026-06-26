"""
Stub awcp_hooks module — used by the instrumentation_patches sandbox validator.

All hook functions are intentional no-ops. They accept any arguments and
return None so that patched agent code can be executed inside the sandbox
without requiring the real AWCP platform to be running.

In production the real awcp_hooks package (part of the AWCP control plane)
replaces this stub and provides actual telemetry, policy enforcement, and
audit event emission.
"""
from __future__ import annotations

from typing import Any


def task_started(task_id: Any = None, agent_name: Any = None, **context: Any) -> None:
    """Fired at the very beginning of every agent task execution."""


def task_completed(task_id: Any = None, result: Any = None, **context: Any) -> None:
    """Fired when an agent task finishes successfully."""


def task_failed(
    task_id: Any = None,
    error: Any = None,
    traceback: Any = None,
    **context: Any,
) -> None:
    """Fired when an agent task terminates with an error or exception."""


def llm_call(model: Any = None, prompt_tokens: Any = 0, **context: Any) -> None:
    """Fired before and/or after every LLM inference call."""


def synthesize(
    input_count: Any = 0, output_length: Any = 0, **context: Any
) -> None:
    """Fired when the agent synthesises a final answer from gathered context."""


def tool_call(tool_name: Any = None, tool_input: Any = None, **context: Any) -> None:
    """Fired before every external tool invocation."""


def web_search(query: Any = None, results_count: Any = 0, **context: Any) -> None:
    """Fired before every web or retrieval search call."""


def token_usage(
    prompt_tokens: Any = 0,
    completion_tokens: Any = 0,
    total_tokens: Any = 0,
    **context: Any,
) -> None:
    """Fired to report token counts after each LLM response."""


def budget_warn(
    used_ratio: Any = 0.0,
    limit: Any = 0,
    agent_name: Any = None,
    **context: Any,
) -> None:
    """Fired when cumulative usage approaches the configured budget threshold."""


def budget_exhausted(
    used_ratio: Any = 1.0, agent_name: Any = None, **context: Any
) -> None:
    """Fired when the agent exhausts its allocated token or cost budget."""


def observability(
    checkpoint_name: Any = None, data: Any = None, **context: Any
) -> None:
    """Fired at key checkpoints to expose intermediate agent state."""


def policy_check(
    policy_name: Any = None, decision: Any = None, **context: Any
) -> None:
    """Fired when the agent evaluates a governance policy gate."""


def approval_request(
    action: Any = None, risk_level: Any = None, **context: Any
) -> None:
    """Fired when the agent requests human approval for a high-risk action."""


def feature_flag(
    flag_name: Any = None, enabled: Any = False, **context: Any
) -> None:
    """Fired when the agent evaluates a feature flag that gates its behaviour."""


def recovery(
    attempt_number: Any = 0, reason: Any = None, **context: Any
) -> None:
    """Fired when the agent attempts to recover from a failure or starts a retry."""


def degradation(
    from_mode: Any = None, to_mode: Any = None, reason: Any = None, **context: Any
) -> None:
    """Fired when the agent's autonomy mode is stepped down by the control plane."""
