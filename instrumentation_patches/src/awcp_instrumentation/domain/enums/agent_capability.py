from __future__ import annotations
from enum import Enum


class AgentCapability(str, Enum):
    """
    Inferred capabilities of an agent, determined by Capability Analysis.

    Each value represents a distinct behavioural pattern detected via AST
    analysis of the agent's source code.  Capabilities drive which AWCP
    lifecycle hooks are *required* for that agent — an agent with no LLM
    calls does not need TOKEN_USAGE or BUDGET_WARN hooks.
    """

    LLM_AGENT = "llm_agent"
    """Agent makes calls to an LLM provider (OpenAI, Anthropic, LangChain, …)."""

    TOOL_AGENT = "tool_agent"
    """Agent invokes external tools, functions, or MCP-registered tools."""

    SEARCH_AGENT = "search_agent"
    """Agent performs web retrieval, RAG, or vector-database searches."""

    SYNTHESIS_AGENT = "synthesis_agent"
    """Agent synthesises or summarises retrieved context into a final answer."""

    OBSERVABLE_AGENT = "observable_agent"
    """Agent emits observability checkpoints to expose intermediate execution state."""

    POLICY_AGENT = "policy_agent"
    """Agent evaluates governance policy gates before taking actions."""

    APPROVAL_AGENT = "approval_agent"
    """Agent requests human approval before executing high-risk actions."""

    FEATURE_FLAG_AGENT = "feature_flag_agent"
    """Agent evaluates feature flags to gate or vary its behaviour."""

    RECOVERY_AGENT = "recovery_agent"
    """Agent performs explicit retry or recovery logic on failure."""

    DEGRADATION_AGENT = "degradation_agent"
    """Agent handles autonomy-degradation signals from the control plane."""
