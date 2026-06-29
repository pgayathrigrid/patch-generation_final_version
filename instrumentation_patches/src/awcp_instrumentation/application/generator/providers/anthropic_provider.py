"""
Anthropic (Claude) LLM provider for the Instrumentation Patch Generator.

Calls the Anthropic Messages API using the ``anthropic`` Python SDK.
The API key is read from the ``ANTHROPIC_API_KEY`` environment variable
(the SDK's default behaviour) — nothing is hardcoded.

Usage::

    from awcp_instrumentation.application.generator.providers.anthropic_provider import (
        AnthropicProvider,
    )
    from awcp_instrumentation import run_instrumentation

    result = run_instrumentation(
        "/path/to/agent/repo",
        llm_provider=AnthropicProvider(),
    )

Optional dependency::

    pip install anthropic
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from awcp_instrumentation.application.generator.llm_interface import (
    LlmProvider,
    LlmProviderError,
    LlmRequest,
    LlmResponse,
)

_DEFAULT_MODEL = "claude-sonnet-4-6"


class AnthropicProvider(LlmProvider):
    """
    LLM provider that calls Claude via the Anthropic Messages API.

    Args:
        api_key:      Anthropic API key.  Defaults to the ``ANTHROPIC_API_KEY``
                      environment variable — the standard SDK convention.
        model:        Default Claude model to use when ``LlmRequest.model`` is
                      ``None``.  Defaults to ``claude-sonnet-4-6``.
        timeout:      HTTP request timeout in seconds.  Defaults to 120.
        max_retries:  Number of automatic retries on transient errors.
                      Defaults to 2 (the SDK default).

    Raises:
        ImportError:       If the ``anthropic`` package is not installed.
        LlmProviderError:  If the API call fails (auth, rate limit, network, etc.).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = _DEFAULT_MODEL,
        timeout: float = 120.0,
        max_retries: int = 2,
    ) -> None:
        try:
            import anthropic as _anthropic
        except ImportError as exc:
            raise ImportError(
                "The 'anthropic' package is required to use AnthropicProvider. "
                "Install it with: pip install anthropic"
            ) from exc

        self._model = model
        self._client = _anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"),
            timeout=timeout,
            max_retries=max_retries,
        )
        self._anthropic = _anthropic

    # ------------------------------------------------------------------
    # LlmProvider interface
    # ------------------------------------------------------------------

    def complete(self, request: LlmRequest) -> LlmResponse:
        """
        Send *request* to the Anthropic Messages API and return a normalised
        ``LlmResponse``.

        Raises:
            LlmProviderError: On any API or network error.
        """
        model = request.model or self._model
        try:
            response = self._client.messages.create(
                model=model,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                system=request.system_prompt,
                messages=[{"role": "user", "content": request.prompt}],
            )
        except self._anthropic.APIConnectionError as exc:
            raise LlmProviderError(
                f"Anthropic API connection failed: {exc}"
            ) from exc
        except self._anthropic.APITimeoutError as exc:
            raise LlmProviderError(
                f"Anthropic API request timed out: {exc}"
            ) from exc
        except self._anthropic.APIStatusError as exc:
            raise LlmProviderError(
                f"Anthropic API error {exc.status_code}: {exc.message}"
            ) from exc
        except Exception as exc:
            raise LlmProviderError(
                f"Unexpected error from Anthropic provider: {type(exc).__name__}: {exc}"
            ) from exc

        content = self._extract_text(response)
        raw: Dict[str, Any] = {
            "id": response.id,
            "model": response.model,
            "stop_reason": response.stop_reason,
        }

        return LlmResponse(
            content=content,
            model=response.model,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            raw=raw,
        )

    @property
    def default_model(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "AnthropicProvider"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text(response: Any) -> str:
        """Extract the text content from an Anthropic Messages response."""
        for block in response.content:
            if block.type == "text":
                return block.text
        return ""
