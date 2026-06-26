"""
AWCP Governance Hook Categories.

These categories represent the lifecycle events that AWCP monitors for every
AI agent.  An agent must emit instrumentation for each category before it can
be onboarded into the AWCP production environment.

Lifecycle ordering (approximate):
  TASK_STARTED → (LLM_CALL | TOOL_CALL | WEB_SEARCH | SYNTHESIZE)*
               → TOKEN_USAGE → (BUDGET_WARN → BUDGET_EXHAUSTED)?
               → (TASK_COMPLETED | TASK_FAILED)
"""
from enum import Enum


class HookCategory(str, Enum):
    """
    The ten AWCP governance hook lifecycle categories.

    String values are snake_case so they serialise cleanly to JSON/YAML and
    match the AWCP hook type identifiers used in the platform's event bus.
    """

    # ── Task lifecycle ───────────────────────────────────────────────────────
    TASK_STARTED     = "task_started"
    """Emitted at the very beginning of an agent task execution."""

    TASK_COMPLETED   = "task_completed"
    """Emitted when an agent task finishes successfully."""

    TASK_FAILED      = "task_failed"
    """Emitted when an agent task terminates with an error or exception."""

    # ── Model interaction ────────────────────────────────────────────────────
    LLM_CALL         = "llm_call"
    """Emitted before and/or after every LLM inference call."""

    SYNTHESIZE       = "synthesize"
    """Emitted when the agent synthesises a final answer from gathered context."""

    # ── Tool and external calls ──────────────────────────────────────────────
    TOOL_CALL        = "tool_call"
    """Emitted whenever the agent invokes a registered tool."""

    WEB_SEARCH       = "web_search"
    """Emitted specifically when the agent performs a web or retrieval search."""

    # ── Resource and budget ──────────────────────────────────────────────────
    TOKEN_USAGE      = "token_usage"
    """Emitted to report prompt and completion token counts after each LLM call."""

    BUDGET_WARN      = "budget_warn"
    """Emitted when cumulative token/cost usage approaches a configured threshold."""

    BUDGET_EXHAUSTED = "budget_exhausted"
    """Emitted when the agent exhausts its allocated token or cost budget."""

    # ── Observability ────────────────────────────────────────────────────────
    OBSERVABILITY    = "observability"
    """Emitted at key checkpoints to expose intermediate agent state for monitoring."""

    # ── Policy ───────────────────────────────────────────────────────────────
    POLICY           = "policy"
    """Emitted when the agent evaluates a governance policy gate."""

    # ── Approval ─────────────────────────────────────────────────────────────
    APPROVAL         = "approval"
    """Emitted when the agent requests human approval for a high-risk action."""

    # ── Feature flag ─────────────────────────────────────────────────────────
    FEATURE_FLAG     = "feature_flag"
    """Emitted when the agent evaluates a feature flag that gates its behaviour."""

    # ── Recovery ─────────────────────────────────────────────────────────────
    RECOVERY         = "recovery"
    """Emitted when the agent attempts to recover from a failure or starts a retry."""

    # ── Degradation ──────────────────────────────────────────────────────────
    DEGRADATION      = "degradation"
    """Emitted when the agent's autonomy mode is stepped down by the control plane."""
