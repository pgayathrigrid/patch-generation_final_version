"""Tests for AnthropicProvider — all tests use mocks, no real API calls.

The ``anthropic`` package is NOT required to be installed for these tests.
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
from awcp_instrumentation.application.generator.providers.anthropic_provider import (
    AnthropicProvider,
)


# ---------------------------------------------------------------------------
# Fake exception classes (stand-ins for anthropic SDK errors)
# ---------------------------------------------------------------------------

class _FakeAPIConnectionError(Exception):
    pass


class _FakeAPITimeoutError(Exception):
    pass


class _FakeAPIStatusError(Exception):
    def __init__(self, status_code: int = 429, message: str = "error"):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


# Minimal fake anthropic module — holds only what AnthropicProvider.complete() needs
_FAKE_ANTHROPIC = SimpleNamespace(
    Anthropic=MagicMock(),
    APIConnectionError=_FakeAPIConnectionError,
    APITimeoutError=_FakeAPITimeoutError,
    APIStatusError=_FakeAPIStatusError,
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


def _make_anthropic_response(text: str, model: str = "claude-sonnet-4-6",
                              input_tokens: int = 50,
                              output_tokens: int = 30) -> Any:
    """Build a minimal fake Anthropic Messages response object."""
    block = SimpleNamespace(type="text", text=text)
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    return SimpleNamespace(
        id="msg_test123",
        model=model,
        stop_reason="end_turn",
        content=[block],
        usage=usage,
    )


def _make_provider(mock_client: MagicMock) -> AnthropicProvider:
    """Create a provider with a pre-wired mock client (no real anthropic needed)."""
    with patch(
        "awcp_instrumentation.application.generator.providers.anthropic_provider.AnthropicProvider.__init__",
        return_value=None,
    ):
        provider = AnthropicProvider.__new__(AnthropicProvider)
    provider._model = "claude-sonnet-4-6"
    provider._client = mock_client
    provider._anthropic = _FAKE_ANTHROPIC
    return provider


# ---------------------------------------------------------------------------
# Basic contract
# ---------------------------------------------------------------------------

class TestAnthropicProviderContract:
    def test_provider_name(self):
        provider = _make_provider(MagicMock())
        assert provider.provider_name == "AnthropicProvider"

    def test_default_model(self):
        provider = _make_provider(MagicMock())
        assert provider.default_model == "claude-sonnet-4-6"

    def test_complete_returns_llm_response(self):
        mock_client = MagicMock()
        fake_resp = _make_anthropic_response('{"changes": []}')
        mock_client.messages.create.return_value = fake_resp

        response = _make_provider(mock_client).complete(_make_request())

        assert response.content == '{"changes": []}'
        assert response.model == "claude-sonnet-4-6"
        assert response.prompt_tokens == 50
        assert response.completion_tokens == 30
        assert response.total_tokens == 80

    def test_complete_uses_request_model_when_set(self):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_anthropic_response("ok", model="claude-opus-4-8")

        _make_provider(mock_client).complete(_make_request(model="claude-opus-4-8"))

        assert mock_client.messages.create.call_args.kwargs["model"] == "claude-opus-4-8"

    def test_complete_uses_default_model_when_request_model_is_none(self):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_anthropic_response("ok")

        _make_provider(mock_client).complete(_make_request(model=None))

        assert mock_client.messages.create.call_args.kwargs["model"] == "claude-sonnet-4-6"

    def test_complete_passes_system_prompt(self):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_anthropic_response("ok")

        req = LlmRequest(prompt="user prompt", system_prompt="system instruction", max_tokens=100)
        _make_provider(mock_client).complete(req)

        assert mock_client.messages.create.call_args.kwargs["system"] == "system instruction"

    def test_complete_passes_max_tokens_and_temperature(self):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_anthropic_response("ok")

        req = LlmRequest(prompt="p", system_prompt="s", max_tokens=512, temperature=0.1)
        _make_provider(mock_client).complete(req)

        kwargs = mock_client.messages.create.call_args.kwargs
        assert kwargs["max_tokens"] == 512
        assert kwargs["temperature"] == 0.1

    def test_complete_sends_user_message(self):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_anthropic_response("ok")

        _make_provider(mock_client).complete(_make_request(prompt="hello agent"))

        assert mock_client.messages.create.call_args.kwargs["messages"] == [
            {"role": "user", "content": "hello agent"}
        ]

    def test_raw_contains_id_and_stop_reason(self):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_anthropic_response("ok")

        response = _make_provider(mock_client).complete(_make_request())

        assert response.raw["id"] == "msg_test123"
        assert response.raw["stop_reason"] == "end_turn"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestAnthropicProviderErrors:
    def test_connection_error_raises_llm_provider_error(self):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = _FakeAPIConnectionError("conn refused")
        with pytest.raises(LlmProviderError, match="connection failed"):
            _make_provider(mock_client).complete(_make_request())

    def test_timeout_error_raises_llm_provider_error(self):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = _FakeAPITimeoutError("timeout")
        with pytest.raises(LlmProviderError, match="timed out"):
            _make_provider(mock_client).complete(_make_request())

    def test_status_error_raises_llm_provider_error(self):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = _FakeAPIStatusError(status_code=429, message="rate limited")
        with pytest.raises(LlmProviderError):
            _make_provider(mock_client).complete(_make_request())

    def test_unexpected_error_raises_llm_provider_error(self):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("unexpected")
        with pytest.raises(LlmProviderError, match="Unexpected error"):
            _make_provider(mock_client).complete(_make_request())

    def test_llm_provider_error_wraps_original_exception(self):
        mock_client = MagicMock()
        original = _FakeAPIConnectionError("root cause")
        mock_client.messages.create.side_effect = original
        with pytest.raises(LlmProviderError) as exc_info:
            _make_provider(mock_client).complete(_make_request())
        assert exc_info.value.__cause__ is original


# ---------------------------------------------------------------------------
# Import error handling
# ---------------------------------------------------------------------------

class TestAnthropicProviderImportError:
    def test_import_error_when_anthropic_not_installed(self):
        # Remove anthropic from sys.modules so the lazy import inside __init__ fails
        saved = sys.modules.pop("anthropic", ...)
        try:
            with patch.dict("sys.modules", {"anthropic": None}):
                with pytest.raises(ImportError, match="pip install anthropic"):
                    AnthropicProvider()
        finally:
            if saved is not ...:
                sys.modules["anthropic"] = saved


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

class TestExtractText:
    def test_extracts_first_text_block(self):
        block = SimpleNamespace(type="text", text="hello")
        response = SimpleNamespace(content=[block])
        assert AnthropicProvider._extract_text(response) == "hello"

    def test_skips_non_text_blocks(self):
        tool_block = SimpleNamespace(type="tool_use", id="x")
        text_block = SimpleNamespace(type="text", text="found it")
        response = SimpleNamespace(content=[tool_block, text_block])
        assert AnthropicProvider._extract_text(response) == "found it"

    def test_returns_empty_string_when_no_text_block(self):
        response = SimpleNamespace(content=[])
        assert AnthropicProvider._extract_text(response) == ""
