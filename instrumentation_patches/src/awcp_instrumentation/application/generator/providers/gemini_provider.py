"""
Google Gemini LLM provider for the Instrumentation Patch Generator.

Calls the Gemini API using the ``google-genai`` Python SDK.
The API key is read from the ``GOOGLE_API_KEY`` environment variable
(your Google AI Studio key) — nothing is hardcoded.

Usage::

    from awcp_instrumentation.application.generator.providers.gemini_provider import (
        GeminiProvider,
    )
    from awcp_instrumentation import run_instrumentation

    result = run_instrumentation(
        "/path/to/agent/repo",
        llm_provider=GeminiProvider(),
    )

Optional dependency::

    pip install google-genai
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

_DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiProvider(LlmProvider):
    """
    LLM provider that calls Google Gemini via the google-genai SDK.

    Args:
        api_key: Google AI Studio API key.  Defaults to the ``GOOGLE_API_KEY``
                 environment variable.
        model:   Default Gemini model to use when ``LlmRequest.model`` is
                 ``None``.  Defaults to ``gemini-2.0-flash``.

    Raises:
        ImportError:      If the ``google-genai`` package is not installed.
        LlmProviderError: If the API call fails (auth, quota, network, etc.).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = _DEFAULT_MODEL,
    ) -> None:
        try:
            from google import genai as _genai
            from google.genai import errors as _errors
            from google.genai import types as _types
        except ImportError as exc:
            raise ImportError(
                "The 'google-genai' package is required to use GeminiProvider. "
                "Install it with: pip install google-genai"
            ) from exc

        self._model = model
        resolved_key = (
            api_key
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
        )
        self._client = _genai.Client(api_key=resolved_key)
        self._genai = _genai
        self._errors = _errors
        self._types = _types

    # ------------------------------------------------------------------
    # LlmProvider interface
    # ------------------------------------------------------------------

    def complete(self, request: LlmRequest) -> LlmResponse:
        """
        Send *request* to the Gemini API and return a normalised ``LlmResponse``.

        Raises:
            LlmProviderError: On any API or network error.
        """
        model = request.model or self._model
        try:
            response = self._client.models.generate_content(
                model=model,
                contents=request.prompt,
                config=self._types.GenerateContentConfig(
                    system_instruction=request.system_prompt,
                    temperature=request.temperature,
                    max_output_tokens=request.max_tokens,
                ),
            )
        except self._errors.APIError as exc:
            raise LlmProviderError(f"Gemini API error: {exc}") from exc
        except Exception as exc:
            raise LlmProviderError(
                f"Unexpected error from Gemini provider: {type(exc).__name__}: {exc}"
            ) from exc

        content = response.text or ""
        usage = response.usage_metadata
        prompt_tokens: int = getattr(usage, "prompt_token_count", 0) or 0
        completion_tokens: int = getattr(usage, "candidates_token_count", 0) or 0

        finish_reason = "unknown"
        if response.candidates:
            finish_reason = str(response.candidates[0].finish_reason)

        raw: Dict[str, Any] = {
            "model": model,
            "finish_reason": finish_reason,
        }

        return LlmResponse(
            content=content,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            raw=raw,
        )

    @property
    def default_model(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "GeminiProvider"
