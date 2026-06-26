"""
AST-based concrete implementation of ``CapabilityAnalyzer``.

Detection strategy (in priority order):
1. Import analysis — module-level ``import X`` / ``from X import Y``
2. Call-site analysis — function / method call names in the AST
3. Decorator analysis — class and function decorators

Keyword matching is intentionally kept out of the primary path to avoid
false positives from comments, string literals, and variable names.
"""
from __future__ import annotations

import ast
from typing import Dict, FrozenSet, List, Set

from awcp_instrumentation.application.capability_analyzer.capability_hook_mapper import (
    CapabilityHookMapper,
)
from awcp_instrumentation.application.capability_analyzer.interface import (
    CapabilityAnalyzer,
)
from awcp_instrumentation.application.capability_analyzer.models import (
    CapabilityAnalysisResult,
)
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.enums.agent_capability import AgentCapability

# ---------------------------------------------------------------------------
# Detection signal tables
# ---------------------------------------------------------------------------

# Top-level module names (or prefixes) that indicate LLM usage.
_LLM_IMPORT_SIGNALS: FrozenSet[str] = frozenset(
    {
        "openai",
        "anthropic",
        "google.generativeai",
        "google.genai",
        "ollama",
        "deepseek",
        "langchain",
        "langchain_openai",
        "langchain_anthropic",
        "langchain_google_genai",
        "langchain_ollama",
        "litellm",
        "transformers",
        "huggingface_hub",
        "together",
        "cohere",
        "mistralai",
        "groq",
        "ai21",
        "replicate",
        "boto3",          # Amazon Bedrock is commonly accessed via boto3
    }
)

# Call-site function/method names that indicate LLM usage.
_LLM_CALL_SIGNALS: FrozenSet[str] = frozenset(
    {
        "chat",
        "complete",
        "create",
        "generate",
        "invoke",
        "agenerate",
        "acreate",
        "ainvoke",
        "stream",
        "astream",
        "predict",
        "run",
        "call_llm",
        "llm_call",
        "query_llm",
        "ask_llm",
        "generate_content",     # google genai
        "generate_text",
        "messages_create",      # anthropic pattern
        "completions_create",   # openai pattern
    }
)

# Decorators that mark a function as an LLM-calling routine.
_LLM_DECORATOR_SIGNALS: FrozenSet[str] = frozenset(
    {
        "llm_call",
        "ai_call",
        "with_llm",
    }
)

# ---------------------------------------------------------------------------

_TOOL_IMPORT_SIGNALS: FrozenSet[str] = frozenset(
    {
        "mcp",
        "tool_registry",
        "langchain.tools",
        "langchain_core.tools",
        "langchain.agents",
    }
)

_TOOL_CALL_SIGNALS: FrozenSet[str] = frozenset(
    {
        "execute_tool",
        "call_tool",
        "run_tool",
        "invoke_tool",
        "function_call",
        "tool_call",
        "use_tool",
        "dispatch_tool",
    }
)

_TOOL_DECORATOR_SIGNALS: FrozenSet[str] = frozenset(
    {
        "tool",
        "function_tool",
        "mcp_tool",
        "register_tool",
        "tool_handler",
    }
)

# ---------------------------------------------------------------------------

_SEARCH_IMPORT_SIGNALS: FrozenSet[str] = frozenset(
    {
        "tavily",
        "tavily_python",
        "arxiv",
        "serpapi",
        "serper",
        "duckduckgo_search",
        "qdrant_client",
        "chromadb",
        "pinecone",
        "weaviate",
        "faiss",
        "langchain.vectorstores",
        "langchain_community.vectorstores",
        "langchain_core.vectorstores",
        "langchain.retrievers",
        "langchain_community.retrievers",
        "langchain.document_loaders",
        "elasticsearch",
        "opensearchpy",
        "pymongo",
    }
)

_SEARCH_CALL_SIGNALS: FrozenSet[str] = frozenset(
    {
        "search",
        "retrieve",
        "similarity_search",
        "similarity_search_with_score",
        "as_retriever",
        "get_relevant_documents",
        "ainvoke_retriever",
        "web_search",
        "fetch_results",
        "query_index",
        "vector_search",
        "hybrid_search",
        "full_text_search",
    }
)

_SEARCH_DECORATOR_SIGNALS: FrozenSet[str] = frozenset(
    {
        "search_tool",
        "retriever",
        "web_retriever",
    }
)

# ---------------------------------------------------------------------------

_SYNTHESIS_IMPORT_SIGNALS: FrozenSet[str] = frozenset(
    {
        "langchain.chains",
        "langchain_core.chains",
        "langchain.chains.summarize",
        "langchain.chains.combine_documents",
    }
)

_SYNTHESIS_CALL_SIGNALS: FrozenSet[str] = frozenset(
    {
        "synthesize",
        "summarize",
        "summarise",
        "generate_answer",
        "final_response",
        "aggregate",
        "merge_results",
        "combine_documents",
        "stuff_documents",
        "reduce_documents",
        "refine",
        "map_reduce",
        "produce_answer",
    }
)

_SYNTHESIS_DECORATOR_SIGNALS: FrozenSet[str] = frozenset(
    {
        "synthesizer",
        "synthesis_step",
        "answer_generator",
    }
)

# ---------------------------------------------------------------------------

_OBSERVABLE_IMPORT_SIGNALS: FrozenSet[str] = frozenset(
    {
        "opentelemetry",
        "prometheus_client",
        "datadog",
        "statsd",
        "structlog",
        "loguru",
    }
)

_OBSERVABLE_CALL_SIGNALS: FrozenSet[str] = frozenset(
    {
        "checkpoint",
        "observe",
        "record_observation",
        "emit_checkpoint",
        "log_checkpoint",
        "observability_hook",
    }
)

_OBSERVABLE_DECORATOR_SIGNALS: FrozenSet[str] = frozenset(
    {
        "observable",
        "checkpoint_step",
        "with_observability",
    }
)

# ---------------------------------------------------------------------------

_POLICY_IMPORT_SIGNALS: FrozenSet[str] = frozenset(
    {
        "casbin",
        "opa_client",
        "rego",
        "policy_engine",
    }
)

_POLICY_CALL_SIGNALS: FrozenSet[str] = frozenset(
    {
        "check_policy",
        "evaluate_policy",
        "gate_check",
        "policy_gate",
        "policy_eval",
        "policy_hook",
    }
)

_POLICY_DECORATOR_SIGNALS: FrozenSet[str] = frozenset(
    {
        "policy_guard",
        "requires_policy",
        "with_policy",
    }
)

# ---------------------------------------------------------------------------

_APPROVAL_IMPORT_SIGNALS: FrozenSet[str] = frozenset(
    {
        "human_approval",
        "approval_service",
    }
)

_APPROVAL_CALL_SIGNALS: FrozenSet[str] = frozenset(
    {
        "request_approval",
        "await_approval",
        "needs_approval",
        "require_approval",
        "human_review",
        "approval_hook",
    }
)

_APPROVAL_DECORATOR_SIGNALS: FrozenSet[str] = frozenset(
    {
        "requires_approval",
        "human_in_loop",
        "with_approval",
    }
)

# ---------------------------------------------------------------------------

_FEATURE_FLAG_IMPORT_SIGNALS: FrozenSet[str] = frozenset(
    {
        "launchdarkly",
        "flagsmith",
        "unleash",
        "flipt",
        "openfeature",
        "feature_flags",
    }
)

_FEATURE_FLAG_CALL_SIGNALS: FrozenSet[str] = frozenset(
    {
        "is_enabled",
        "get_flag",
        "evaluate_flag",
        "flag_enabled",
        "check_feature_flag",
        "feature_flag_hook",
    }
)

_FEATURE_FLAG_DECORATOR_SIGNALS: FrozenSet[str] = frozenset(
    {
        "feature_flag",
        "flagged",
        "with_flag",
    }
)

# ---------------------------------------------------------------------------

_RECOVERY_IMPORT_SIGNALS: FrozenSet[str] = frozenset(
    {
        "tenacity",
        "backoff",
        "retry",
        "circuitbreaker",
    }
)

_RECOVERY_CALL_SIGNALS: FrozenSet[str] = frozenset(
    {
        "retry",
        "recover",
        "on_retry",
        "retry_attempt",
        "recovery_hook",
        "backoff_retry",
    }
)

_RECOVERY_DECORATOR_SIGNALS: FrozenSet[str] = frozenset(
    {
        "retry",
        "with_retry",
        "on_failure",
        "recoverable",
    }
)

# ---------------------------------------------------------------------------

_DEGRADATION_IMPORT_SIGNALS: FrozenSet[str] = frozenset(
    {
        "autonomy_manager",
        "degradation_service",
    }
)

_DEGRADATION_CALL_SIGNALS: FrozenSet[str] = frozenset(
    {
        "degrade",
        "step_down",
        "reduce_autonomy",
        "autonomy_degraded",
        "degradation_hook",
        "on_degradation",
    }
)

_DEGRADATION_DECORATOR_SIGNALS: FrozenSet[str] = frozenset(
    {
        "degradable",
        "with_degradation",
        "autonomy_aware",
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _top_module(module_name: str) -> str:
    """Return the top-level package name from a dotted module path."""
    return module_name.split(".")[0]


def _collect_imports(tree: ast.Module) -> List[str]:
    """
    Return a flat list of all imported module names (dotted, as written in
    the source).  Both ``import X`` and ``from X import Y`` forms are
    captured; only the module path (not the symbol) is returned.
    """
    names: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def _collect_call_names(tree: ast.Module) -> List[str]:
    """
    Return the simple name of every call site in the AST.

    For ``foo()`` → ``"foo"``
    For ``obj.foo()`` → ``"foo"``
    For ``a.b.foo()`` → ``"foo"``

    Only the leaf name is used so that
    ``langchain_openai.ChatOpenAI(...).invoke()`` registers as ``"invoke"``.
    """
    names: List[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            names.append(func.id)
        elif isinstance(func, ast.Attribute):
            names.append(func.attr)
    return names


def _collect_decorator_names(tree: ast.Module) -> List[str]:
    """
    Return the simple name of every decorator applied to a function or class.

    ``@tool`` → ``"tool"``
    ``@registry.tool`` → ``"tool"``
    ``@tool()`` (call-form) → ``"tool"``
    """
    names: List[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name):
                names.append(dec.id)
            elif isinstance(dec, ast.Attribute):
                names.append(dec.attr)
            elif isinstance(dec, ast.Call):
                inner = dec.func
                if isinstance(inner, ast.Name):
                    names.append(inner.id)
                elif isinstance(inner, ast.Attribute):
                    names.append(inner.attr)
    return names


def _match_any(candidates: List[str], signals: FrozenSet[str]) -> List[str]:
    """Return the subset of *candidates* that appear in *signals*."""
    return [c for c in candidates if c in signals]


def _match_prefix(candidates: List[str], signals: FrozenSet[str]) -> List[str]:
    """
    Return candidates whose top-level module name OR full dotted name appears
    in *signals*.  Used for import matching where both ``openai`` and
    ``langchain.chat_models`` need to match their respective signal sets.
    """
    matched: List[str] = []
    for c in candidates:
        if c in signals or _top_module(c) in signals:
            matched.append(c)
    return matched


# ---------------------------------------------------------------------------
# Concrete analyser
# ---------------------------------------------------------------------------


class AstCapabilityAnalyzer(CapabilityAnalyzer):
    """
    Infers ``AgentCapability`` values by walking the Python AST of an agent's
    source file.

    Detection for each capability checks three independent signal sources and
    short-circuits on the first hit:
        1. Import names
        2. Call-site function/method names
        3. Decorator names

    Evidence is accumulated from *all* matching signals so that the result
    can be explained to the user.
    """

    def analyze(self, agent: AgentSource) -> CapabilityAnalysisResult:  # noqa: D102
        try:
            tree = ast.parse(agent.source_code)
        except SyntaxError:
            # Unparseable source — return no capabilities (safe fallback
            # causes all hooks to be required).
            return CapabilityAnalysisResult(
                agent=agent,
                capabilities=frozenset(),
                evidence={},
                required_hook_categories=CapabilityHookMapper.all_hooks(),
            )

        imports = _collect_imports(tree)
        calls = _collect_call_names(tree)
        decorators = _collect_decorator_names(tree)

        capabilities: Set[AgentCapability] = set()
        evidence: Dict[AgentCapability, List[str]] = {}

        def _check(
            cap: AgentCapability,
            import_signals: FrozenSet[str],
            call_signals: FrozenSet[str],
            decorator_signals: FrozenSet[str],
        ) -> None:
            ev: List[str] = []
            ev.extend(f"import:{m}" for m in _match_prefix(imports, import_signals))
            ev.extend(f"call:{m}" for m in _match_any(calls, call_signals))
            ev.extend(f"decorator:{m}" for m in _match_any(decorators, decorator_signals))
            if ev:
                capabilities.add(cap)
                evidence[cap] = ev

        _check(
            AgentCapability.LLM_AGENT,
            _LLM_IMPORT_SIGNALS,
            _LLM_CALL_SIGNALS,
            _LLM_DECORATOR_SIGNALS,
        )
        _check(
            AgentCapability.TOOL_AGENT,
            _TOOL_IMPORT_SIGNALS,
            _TOOL_CALL_SIGNALS,
            _TOOL_DECORATOR_SIGNALS,
        )
        _check(
            AgentCapability.SEARCH_AGENT,
            _SEARCH_IMPORT_SIGNALS,
            _SEARCH_CALL_SIGNALS,
            _SEARCH_DECORATOR_SIGNALS,
        )
        _check(
            AgentCapability.SYNTHESIS_AGENT,
            _SYNTHESIS_IMPORT_SIGNALS,
            _SYNTHESIS_CALL_SIGNALS,
            _SYNTHESIS_DECORATOR_SIGNALS,
        )
        _check(
            AgentCapability.OBSERVABLE_AGENT,
            _OBSERVABLE_IMPORT_SIGNALS,
            _OBSERVABLE_CALL_SIGNALS,
            _OBSERVABLE_DECORATOR_SIGNALS,
        )
        _check(
            AgentCapability.POLICY_AGENT,
            _POLICY_IMPORT_SIGNALS,
            _POLICY_CALL_SIGNALS,
            _POLICY_DECORATOR_SIGNALS,
        )
        _check(
            AgentCapability.APPROVAL_AGENT,
            _APPROVAL_IMPORT_SIGNALS,
            _APPROVAL_CALL_SIGNALS,
            _APPROVAL_DECORATOR_SIGNALS,
        )
        _check(
            AgentCapability.FEATURE_FLAG_AGENT,
            _FEATURE_FLAG_IMPORT_SIGNALS,
            _FEATURE_FLAG_CALL_SIGNALS,
            _FEATURE_FLAG_DECORATOR_SIGNALS,
        )
        _check(
            AgentCapability.RECOVERY_AGENT,
            _RECOVERY_IMPORT_SIGNALS,
            _RECOVERY_CALL_SIGNALS,
            _RECOVERY_DECORATOR_SIGNALS,
        )
        _check(
            AgentCapability.DEGRADATION_AGENT,
            _DEGRADATION_IMPORT_SIGNALS,
            _DEGRADATION_CALL_SIGNALS,
            _DEGRADATION_DECORATOR_SIGNALS,
        )

        caps_frozen = frozenset(capabilities)
        required = CapabilityHookMapper.required_hooks(caps_frozen)

        return CapabilityAnalysisResult(
            agent=agent,
            capabilities=caps_frozen,
            evidence=evidence,
            required_hook_categories=required,
        )
