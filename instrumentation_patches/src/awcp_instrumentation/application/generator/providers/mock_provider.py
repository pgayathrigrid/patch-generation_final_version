"""
Mock LLM provider for unit testing.

``MockLlmProvider`` returns predictable, fully-structured JSON responses so
tests never make real network calls.  The response content can be customised
at construction time to test different scenarios (valid JSON, malformed JSON,
provider errors, etc.).
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from awcp_instrumentation.application.generator.llm_interface import (
    LlmProvider,
    LlmProviderError,
    LlmRequest,
    LlmResponse,
)


# ---------------------------------------------------------------------------
# Per-category hook call templates
# ---------------------------------------------------------------------------

# Each value is the exact code fragment inserted into the patched agent source.
# All arguments use keyword form with safe defaults so the sandbox can execute
# the code without NameError even when the agent's local variables differ.
_HOOK_CODE: Dict[str, str] = {
    "task_started":     'get_manager().dispatch(HookType.TASK_STARTED, agent_id="agent", task_id=None)',
    "task_completed":   'get_manager().dispatch(HookType.TASK_COMPLETED, agent_id="agent", task_id=None)',
    "task_failed":      'get_manager().dispatch(HookType.TASK_FAILED, agent_id="agent", task_id=None, error="unknown")',
    "llm_call":         'get_manager().dispatch(HookType.LLM_CALL, agent_id="agent", task_id=None, model="unknown")',
    "synthesize":       'get_manager().dispatch(HookType.SYNTHESIZE, agent_id="agent", task_id=None)',
    "tool_call":        'get_manager().dispatch(HookType.TOOL_CALL, agent_id="agent", task_id=None, tool_name="unknown", action="unknown")',
    "web_search":       'get_manager().dispatch(HookType.WEB_SEARCH, agent_id="agent", task_id=None, query="unknown")',
    "token_usage":      'get_manager().dispatch(HookType.TOKEN_USAGE, agent_id="agent", task_id=None)',
    "budget_warn":      'get_manager().dispatch(HookType.BUDGET_WARN, agent_id="agent", task_id=None)',
    "budget_exhausted": 'get_manager().dispatch(HookType.BUDGET_EXHAUSTED, agent_id="agent", task_id=None)',
    "observability":    'get_manager().dispatch(HookType.STEP, agent_id="agent", task_id=None, checkpoint="step")',
    "policy":           'get_manager().dispatch(HookType.GATE_EVALUATED, agent_id="agent", task_id=None, action="unknown", decision="allow", scope="unknown", write=False, mode="policy")',
    "approval":         'get_manager().dispatch(HookType.APPROVAL_REQUIRED, agent_id="agent", task_id=None, action="unknown", risk="unknown")',
    "feature_flag":     'get_manager().dispatch(HookType.SIGNAL_RECEIVED, agent_id="agent", task_id=None, flag_name="unknown", enabled=False)',
    "recovery":         'get_manager().dispatch(HookType.SIGNAL_RECEIVED, agent_id="agent", task_id=None, attempt=0, reason="unknown")',
    "degradation":      'get_manager().dispatch(HookType.AUTONOMY_DEGRADED, agent_id="agent", task_id=None, from_mode="unknown", to_mode="unknown")',
}

# Regex to extract the hook category from a single-gap prompt:
#   **Category:** `{category}`
_CATEGORY_RE = re.compile(r"\*\*Category:\*\*\s*`([^`]+)`")

# Regex to extract gap categories from a batch prompt:
#   ### Gap N: {category}
_BATCH_GAP_RE = re.compile(r"^### Gap \d+: (\S+)", re.MULTILINE)


# ---------------------------------------------------------------------------
# Default mock response
# ---------------------------------------------------------------------------

def _default_response_json(request: LlmRequest) -> str:
    """
    Build a deterministic, valid JSON response from the request content.

    The response is deliberately minimal and structurally correct so the
    ``ResponseParser`` can always parse it in the happy-path tests.

    Category is extracted via regex from the ``**Category:** `…` `` line that
    ``PromptBuilder`` always includes.  This avoids false matches caused by
    other categories being mentioned in rationale or instrumentation-hint text
    (e.g. the task_completed rationale mentions "task_started").
    """
    category = "task_started"
    m = _CATEGORY_RE.search(request.prompt)
    if m and m.group(1) in _HOOK_CODE:
        category = m.group(1)

    hook_code = _HOOK_CODE.get(category, f"get_manager().dispatch(HookType.{category.upper()}, agent_id=agent_id, task_id=task_id)")

    response: Dict[str, Any] = {
        "import_additions": ["from awcp.agent_hooks import get_manager", "from awcp.agent_hooks.types import HookType"],
        "changes": [
            {
                "code_fragment": hook_code,
                "location": "before_function_body",
                "target_function": "run",
                "explanation": (
                    f"Insert AWCP {category} lifecycle hook at the entry point "
                    "of the agent's main execution function."
                ),
            }
        ],
        "explanation": (
            f"Added {hook_code} to satisfy AWCP {category} lifecycle instrumentation."
        ),
        "confidence": 0.85,
    }
    return json.dumps(response, indent=2)


def _default_batch_response_json(request: LlmRequest) -> str:
    """
    Build a deterministic JSON-array response for batch requests.

    Extracts every ``### Gap N: {category}`` line from the prompt and returns
    one response object per gap, in order.
    """
    categories = _BATCH_GAP_RE.findall(request.prompt)
    responses: List[Dict[str, Any]] = []
    for category in categories:
        hook_code = _HOOK_CODE.get(
            category,
            f"get_manager().dispatch(HookType.{category.upper()}, agent_id=agent_id, task_id=task_id)",
        )
        responses.append(
            {
                "import_additions": [
                    "from awcp.agent_hooks import get_manager",
                    "from awcp.agent_hooks.types import HookType",
                ],
                "changes": [
                    {
                        "code_fragment": hook_code,
                        "location": "before_function_body",
                        "target_function": "run",
                        "explanation": (
                            f"Insert AWCP {category} lifecycle hook at the "
                            "entry point of the agent's main execution function."
                        ),
                    }
                ],
                "explanation": (
                    f"Added {hook_code} to satisfy AWCP {category} lifecycle instrumentation."
                ),
                "confidence": 0.85,
            }
        )
    return json.dumps(responses, indent=2)


# ---------------------------------------------------------------------------
# MockLlmProvider
# ---------------------------------------------------------------------------

class MockLlmProvider(LlmProvider):
    """
    Deterministic LLM provider stub for unit and integration tests.

    Args:
        response_content:   The string to return as ``LlmResponse.content``.
                            When ``None``, a default valid JSON response is
                            generated from the request.
        model_name:         The model identifier reported in responses.
        prompt_tokens:      Simulated prompt token count.
        completion_tokens:  Simulated completion token count.
        raise_error:        When set, ``complete()`` raises this exception
                            instead of returning a response — used to test
                            failure handling paths.
        call_log:           Mutable list that records every ``LlmRequest``
                            passed to ``complete()``.  Inspect in tests to
                            verify prompt content without monkey-patching.
    """

    def __init__(
        self,
        response_content: Optional[str] = None,
        model_name: str = "mock-model-1.0",
        prompt_tokens: int = 120,
        completion_tokens: int = 80,
        raise_error: Optional[Exception] = None,
        call_log: Optional[List[LlmRequest]] = None,
    ) -> None:
        self._response_content = response_content
        self._model_name = model_name
        self._prompt_tokens = prompt_tokens
        self._completion_tokens = completion_tokens
        self._raise_error = raise_error
        self._call_log: List[LlmRequest] = call_log if call_log is not None else []

    # ------------------------------------------------------------------
    # LlmProvider interface
    # ------------------------------------------------------------------

    def complete(self, request: LlmRequest) -> LlmResponse:
        self._call_log.append(request)

        if self._raise_error is not None:
            raise self._raise_error

        if self._response_content is not None:
            content = self._response_content
        elif _BATCH_GAP_RE.search(request.prompt):
            content = _default_batch_response_json(request)
        else:
            content = _default_response_json(request)
        effective_model = request.model or self._model_name

        return LlmResponse(
            content=content,
            model=effective_model,
            prompt_tokens=self._prompt_tokens,
            completion_tokens=self._completion_tokens,
            raw={"mock": True},
        )

    @property
    def default_model(self) -> str:
        return self._model_name

    @property
    def provider_name(self) -> str:
        return "MockLlmProvider"

    # ------------------------------------------------------------------
    # Test helpers
    # ------------------------------------------------------------------

    @property
    def call_count(self) -> int:
        """Number of times ``complete()`` was called."""
        return len(self._call_log)

    @property
    def last_request(self) -> Optional[LlmRequest]:
        """The most recent ``LlmRequest`` passed to ``complete()``."""
        return self._call_log[-1] if self._call_log else None
