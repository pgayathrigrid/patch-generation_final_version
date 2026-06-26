"""
Prompt builder for the LLM Patch Generator.

Translates a ``GovernanceGap`` and ``AgentSource`` into a fully formed
``LlmRequest``.  All prompt engineering is encapsulated here so that changes
to prompt strategy never touch the generator or parser.
"""
from __future__ import annotations

from awcp_instrumentation.application.gap_reporter.models import GovernanceGap
from awcp_instrumentation.application.generator.llm_interface import LlmRequest
from awcp_instrumentation.domain.entities.agent_source import AgentSource


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert Python software engineer specialising in AI agent governance \
instrumentation. Your task is to add a single missing governance hook to a \
Python agent's source code.

You will receive:
1. The agent's complete source code.
2. A specific governance gap that must be addressed.
3. An instrumentation hint describing exactly what to add.

Your response MUST be a single valid JSON object with this exact structure:

{
  "import_additions": ["<import statement 1>", "<import statement 2>"],
  "changes": [
    {
      "code_fragment": "<syntactically valid Python code to insert>",
      "location": "<one of: top_of_file | after_imports | before_function_body | around_function | inline>",
      "target_function": "<function name or null>",
      "explanation": "<why this code fragment goes at this location>"
    }
  ],
  "explanation": "<overall explanation of what was added and why>",
  "confidence": <float between 0.0 and 1.0>
}

Strict rules:
- Address ONLY the specified governance gap. Do not add unrelated code.
- Keep additions minimal. Do not refactor, rename, or restructure existing code.
- Do not duplicate imports that already exist in the source.
- All code_fragment values must be syntactically valid Python.
- If no imports are needed, return an empty list: "import_additions": [].
- Respond ONLY with the JSON object. No markdown fences, no preamble, no \
trailing explanation outside the JSON structure.
"""

_USER_PROMPT_TEMPLATE = """\
## Agent Source Code

```python
{source_code}
```

---

## Governance Gap to Address

**Category:** `{category}`
**Hook Name:** `{hook_name}`
**Description:** {hook_description}

---

## Required Action

{action}

---

## Instrumentation Guidance

{instrumentation_hint}

---

## Rationale

{rationale}

---

Generate the minimal Python code additions required to address this single \
governance gap. Do not modify any existing code beyond what is necessary to \
introduce the hook.\
"""


# ---------------------------------------------------------------------------
# PromptBuilder
# ---------------------------------------------------------------------------

class PromptBuilder:
    """
    Constructs an ``LlmRequest`` from a ``GovernanceGap`` and ``AgentSource``.

    Encapsulates all prompt engineering decisions.  Change this class to
    experiment with different prompt strategies without touching the generator.

    Args:
        max_tokens:  Maximum completion tokens for the generated request.
        temperature: Sampling temperature for the generated request.
        model:       Model identifier to embed in the request, or ``None``
                     to use the provider's default.
    """

    def __init__(
        self,
        max_tokens: int = 2048,
        temperature: float = 0.2,
        model: str | None = None,
    ) -> None:
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._model = model

    def build(self, gap: GovernanceGap, agent: AgentSource) -> LlmRequest:
        """
        Build an ``LlmRequest`` for the given *gap* in *agent*'s source.

        Args:
            gap:   The governance gap to instrument.
            agent: The agent whose source code will be included in the prompt.

        Returns:
            A fully populated ``LlmRequest`` ready to be sent to an LLM provider.
        """
        user_prompt = _USER_PROMPT_TEMPLATE.format(
            source_code=agent.source_code,
            category=gap.category.value,
            hook_name=gap.hook.name,
            hook_description=gap.hook.description,
            action=gap.recommendation.action,
            instrumentation_hint=gap.recommendation.instrumentation_hint,
            rationale=gap.recommendation.rationale,
        )
        return LlmRequest(
            prompt=user_prompt,
            system_prompt=_SYSTEM_PROMPT,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            model=self._model,
        )
