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
    "task_started":     "awcp_hooks.task_started(task_id=None, agent_name=None)",
    "task_completed":   "awcp_hooks.task_completed(task_id=None, result=None)",
    "task_failed":      "awcp_hooks.task_failed(task_id=None, error=None, traceback=None)",
    "llm_call":         "awcp_hooks.llm_call(model=None, prompt_tokens=0)",
    "synthesize":       "awcp_hooks.synthesize(input_count=0, output_length=0)",
    "tool_call":        "awcp_hooks.tool_call(tool_name=None, tool_input=None)",
    "web_search":       "awcp_hooks.web_search(query=None, results_count=0)",
    "token_usage":      "awcp_hooks.token_usage(prompt_tokens=0, completion_tokens=0, total_tokens=0)",
    "budget_warn":      "awcp_hooks.budget_warn(used_ratio=0.0, limit=0, agent_name=None)",
    "budget_exhausted": "awcp_hooks.budget_exhausted(used_ratio=1.0, agent_name=None)",
    "observability":    "awcp_hooks.observability(checkpoint_name=None, data=None)",
    "policy":           "awcp_hooks.policy_check(policy_name=None, decision=None)",
    "approval":         "awcp_hooks.approval_request(action=None, risk_level=None)",
    "feature_flag":     "awcp_hooks.feature_flag(flag_name=None, enabled=False)",
    "recovery":         "awcp_hooks.recovery(attempt_number=0, reason=None)",
    "degradation":      "awcp_hooks.degradation(from_mode=None, to_mode=None, reason=None)",
}

# Regex to extract the hook category from the structured prompt produced by
# PromptBuilder, which always includes the line:  **Category:** `{category}`
_CATEGORY_RE = re.compile(r"\*\*Category:\*\*\s*`([^`]+)`")


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

    hook_code = _HOOK_CODE.get(category, f"awcp_hooks.{category}()")

    response: Dict[str, Any] = {
        "import_additions": ["import awcp_hooks"],
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

        content = (
            self._response_content
            if self._response_content is not None
            else _default_response_json(request)
        )
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
