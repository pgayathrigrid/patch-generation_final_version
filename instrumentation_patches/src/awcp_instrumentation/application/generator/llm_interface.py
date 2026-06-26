"""
Abstract LLM provider interface and its request/response value objects.

The ``LlmProvider`` port decouples the Patch Generator from any specific
model or API vendor.  Concrete providers (Claude, GPT, Gemini, etc.) are
injected at construction time; only this module is imported by the generator.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Request / Response value objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LlmRequest:
    """
    Everything required to make one LLM call.

    Attributes:
        prompt:        The user-facing prompt (agent source + gap details).
        system_prompt: Instruction context given to the model before the prompt.
        max_tokens:    Maximum completion length in tokens.
        temperature:   Sampling temperature (lower = more deterministic).
        model:         Model identifier override.  ``None`` means use the
                       provider's ``default_model``.
    """

    prompt: str
    system_prompt: str
    max_tokens: int = 2048
    temperature: float = 0.2
    model: Optional[str] = None


@dataclass(frozen=True)
class LlmResponse:
    """
    The normalised response returned by any ``LlmProvider``.

    Attributes:
        content:           The text completion from the model.
        model:             The model that produced this response.
        prompt_tokens:     Tokens consumed by the prompt.
        completion_tokens: Tokens consumed by the completion.
        raw:               Unmodified provider response object (for debugging).
    """

    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


# ---------------------------------------------------------------------------
# Abstract provider port
# ---------------------------------------------------------------------------

class LlmProvider(ABC):
    """
    Port (abstract interface) for any LLM provider.

    Implement this to connect the Patch Generator to a specific model API.
    The ``LlmPatchGenerator`` depends only on this abstraction.

    Examples of concrete implementations:
    - ``ClaudeProvider`` — wraps the Anthropic API
    - ``OpenAIProvider`` — wraps the OpenAI API
    - ``MockLlmProvider`` — deterministic stub for unit tests
    """

    @abstractmethod
    def complete(self, request: LlmRequest) -> LlmResponse:
        """
        Send *request* to the underlying model and return a normalised response.

        Args:
            request: The fully populated ``LlmRequest``.

        Returns:
            A normalised ``LlmResponse`` regardless of the provider's native
            response format.

        Raises:
            LlmProviderError: If the provider call fails for any reason.
        """

    @property
    @abstractmethod
    def default_model(self) -> str:
        """The model identifier used when ``LlmRequest.model`` is ``None``."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name stored in ``PatchMetadata``."""


class LlmProviderError(Exception):
    """Raised when an LLM provider call fails at the transport or API level."""
