"""Tests for GeminiProvider — all tests use mocks, no real API calls.

The ``google-genai`` package is NOT required to be installed for these tests.
All SDK types are fully stubbed out below.
"""
from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from awcp_instrumentation.application.generator.llm_interface import (
    LlmProviderError,
    LlmRequest,
)
from awcp_instrumentation.application.generator.providers.gemini_provider import (
    GeminiProvider,
)


# ---------------------------------------------------------------------------
# Fake exception classes (stand-ins for google.genai.errors)
# ---------------------------------------------------------------------------

class _FakeAPIError(Exception):
    pass


class _FakeClientError(_FakeAPIError):
    pass


class _FakeServerError(_FakeAPIError):
    pass


# Minimal fake errors module
_FAKE_ERRORS = SimpleNamespace(
    APIError=_FakeAPIError,
    ClientError=_FakeClientError,
    ServerError=_FakeServerError,
)

# Minimal fake types module
_FAKE_TYPES = SimpleNamespace(
    GenerateContentConfig=MagicMock(return_value=MagicMock()),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(prompt: str = "test prompt", model: str | None = None) -> LlmRequest:
    return LlmRequest(
        prompt=prompt,
        system_prompt="You are a test assistant.",
        max_tokens=256,
        temperature=0.2,
        model=model,
    )


def _make_gemini_response(text: str, model: str = "gemini-2.0-flash",
                           prompt_tokens: int = 40,
                           candidates_tokens: int = 25) -> Any:
    """Build a minimal fake Gemini generate_content response."""
    usage = SimpleNamespace(
        prompt_token_count=prompt_tokens,
        candidates_token_count=candidates_tokens,
        total_token_count=prompt_tokens + candidates_tokens,
    )
    candidate = SimpleNamespace(finish_reason="STOP")
    return SimpleNamespace(
        text=text,
        usage_metadata=usage,
        candidates=[candidate],
    )


def _make_provider(mock_client: MagicMock) -> GeminiProvider:
    """Create a provider with a pre-wired mock client (no real google-genai needed)."""
    with patch(
        "awcp_instrumentation.application.generator.providers.gemini_provider.GeminiProvider.__init__",
        return_value=None,
    ):
        provider = GeminiProvider.__new__(GeminiProvider)
    provider._model = "gemini-2.0-flash"
    provider._client = mock_client
    provider._errors = _FAKE_ERRORS
    provider._types = _FAKE_TYPES
    return provider


# ---------------------------------------------------------------------------
# Basic contract
# ---------------------------------------------------------------------------

class TestGeminiProviderContract:
    def test_provider_name(self):
        provider = _make_provider(MagicMock())
        assert provider.provider_name == "GeminiProvider"

    def test_default_model(self):
        provider = _make_provider(MagicMock())
        assert provider.default_model == "gemini-2.0-flash"

    def test_complete_returns_llm_response(self):
        mock_client = MagicMock()
        fake_resp = _make_gemini_response('{"changes": []}')
        mock_client.models.generate_content.return_value = fake_resp

        response = _make_provider(mock_client).complete(_make_request())

        assert response.content == '{"changes": []}'
        assert response.model == "gemini-2.0-flash"
        assert response.prompt_tokens == 40
        assert response.completion_tokens == 25
        assert response.total_tokens == 65

    def test_complete_uses_request_model_when_set(self):
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _make_gemini_response("ok")

        _make_provider(mock_client).complete(_make_request(model="gemini-1.5-pro"))

        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        assert call_kwargs["model"] == "gemini-1.5-pro"

    def test_complete_uses_default_model_when_request_model_is_none(self):
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _make_gemini_response("ok")

        _make_provider(mock_client).complete(_make_request(model=None))

        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        assert call_kwargs["model"] == "gemini-2.0-flash"

    def test_complete_passes_prompt_as_contents(self):
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _make_gemini_response("ok")

        _make_provider(mock_client).complete(_make_request(prompt="hello gemini"))

        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        assert call_kwargs["contents"] == "hello gemini"

    def test_raw_contains_model_and_finish_reason(self):
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _make_gemini_response("ok")

        response = _make_provider(mock_client).complete(_make_request())

        assert "model" in response.raw
        assert "finish_reason" in response.raw
        assert response.raw["model"] == "gemini-2.0-flash"
        assert response.raw["finish_reason"] == "STOP"

    def test_empty_text_response_returns_empty_string(self):
        mock_client = MagicMock()
        fake_resp = _make_gemini_response("")
        fake_resp = SimpleNamespace(
            text=None,
            usage_metadata=SimpleNamespace(prompt_token_count=0, candidates_token_count=0),
            candidates=[],
        )
        mock_client.models.generate_content.return_value = fake_resp

        response = _make_provider(mock_client).complete(_make_request())
        assert response.content == ""

    def test_missing_usage_metadata_fields_default_to_zero(self):
        mock_client = MagicMock()
        fake_resp = SimpleNamespace(
            text="ok",
            usage_metadata=SimpleNamespace(),  # no token count fields
            candidates=[SimpleNamespace(finish_reason="STOP")],
        )
        mock_client.models.generate_content.return_value = fake_resp

        response = _make_provider(mock_client).complete(_make_request())
        assert response.prompt_tokens == 0
        assert response.completion_tokens == 0


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestGeminiProviderErrors:
    def test_api_error_raises_llm_provider_error(self):
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = _FakeAPIError("quota exceeded")
        with pytest.raises(LlmProviderError, match="Gemini API error"):
            _make_provider(mock_client).complete(_make_request())

    def test_client_error_raises_llm_provider_error(self):
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = _FakeClientError("invalid key")
        with pytest.raises(LlmProviderError, match="Gemini API error"):
            _make_provider(mock_client).complete(_make_request())

    def test_server_error_raises_llm_provider_error(self):
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = _FakeServerError("500 internal")
        with pytest.raises(LlmProviderError, match="Gemini API error"):
            _make_provider(mock_client).complete(_make_request())

    def test_unexpected_error_raises_llm_provider_error(self):
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("unexpected")
        with pytest.raises(LlmProviderError, match="Unexpected error"):
            _make_provider(mock_client).complete(_make_request())

    def test_llm_provider_error_wraps_original_exception(self):
        mock_client = MagicMock()
        original = _FakeAPIError("root cause")
        mock_client.models.generate_content.side_effect = original
        with pytest.raises(LlmProviderError) as exc_info:
            _make_provider(mock_client).complete(_make_request())
        assert exc_info.value.__cause__ is original


# ---------------------------------------------------------------------------
# Import error handling
# ---------------------------------------------------------------------------

class TestGeminiProviderImportError:
    def test_import_error_when_google_genai_not_installed(self):
        saved_google = sys.modules.pop("google", ...)
        saved_genai = sys.modules.pop("google.genai", ...)
        try:
            with patch.dict("sys.modules", {"google": None, "google.genai": None}):
                with pytest.raises(ImportError, match="pip install google-genai"):
                    GeminiProvider()
        finally:
            if saved_google is not ...:
                sys.modules["google"] = saved_google
            if saved_genai is not ...:
                sys.modules["google.genai"] = saved_genai
