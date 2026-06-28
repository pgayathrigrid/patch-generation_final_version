"""
Prompt builder for the LLM Patch Generator.

Translates a ``GovernanceGap`` and ``AgentSource`` into a fully formed
``LlmRequest``.  All prompt engineering is encapsulated here so that changes
to prompt strategy never touch the generator or parser.
"""
from __future__ import annotations

import ast
from typing import List

from awcp_instrumentation.application.detector.rules import _ast_helpers as _h
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
- Use ONLY variable names that already exist in the target function's scope \
(listed in the "Available Variables" section). Do NOT invent variable names \
that do not appear there. If the required variable does not exist, use None \
as a fallback literal.
- Respond ONLY with the JSON object. No markdown fences, no preamble, no \
trailing explanation outside the JSON structure.
"""

_USER_PROMPT_TEMPLATE = """\
## Agent Source Code

```python
{source_code}
```

---

## Available Variables Per Function

The following variables are in scope within each function in the agent above.
Use ONLY these names in your generated code fragment — do not invent names \
that are not listed here.

{variable_context}

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

_BATCH_SYSTEM_PROMPT = """\
You are an expert Python software engineer specialising in AI agent governance \
instrumentation. Your task is to add multiple missing governance hooks to a \
Python agent's source code.

Your response MUST be a JSON array with exactly one object per gap, in the \
same order as the gaps are listed. Each object must have this exact structure:

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
  "explanation": "<explanation for this gap>",
  "confidence": <float between 0.0 and 1.0>
}

Strict rules:
- Address ONLY the governance gap described for each array element.
- Keep additions minimal. Do not refactor, rename, or restructure existing code.
- Do not duplicate imports that already exist in the source.
- All code_fragment values must be syntactically valid Python.
- If no imports are needed, return an empty list: "import_additions": [].
- Use ONLY variable names that already exist in the target function's scope \
(listed in the "Available Variables" section). Do NOT invent variable names \
that do not appear there. If the required variable does not exist, use None \
as a fallback literal.
- Respond ONLY with the JSON array. No markdown fences, no preamble, no \
trailing explanation outside the JSON array.
"""

_BATCH_GAP_TEMPLATE = """\
### Gap {index}: {category}

**Hook Name:** `{hook_name}`
**Description:** {hook_description}

**Required Action:** {action}

**Instrumentation Guidance:** {instrumentation_hint}

**Rationale:** {rationale}"""

_BATCH_USER_PROMPT_TEMPLATE = """\
## Agent Source Code

```python
{source_code}
```

---

## Available Variables Per Function

The following variables are in scope within each function in the agent above.
Use ONLY these names in your generated code fragments — do not invent names \
that are not listed here.

{variable_context}

---

## Governance Gaps to Address

{gaps_section}

---

Generate the minimal Python code additions for each gap above. Return a JSON \
array with exactly {gap_count} object(s), one per gap in order.\
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
        variable_context = self._format_variable_context(agent.source_code)
        user_prompt = _USER_PROMPT_TEMPLATE.format(
            source_code=agent.source_code,
            variable_context=variable_context,
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

    def build_batch(self, gaps: List[GovernanceGap], agent: AgentSource) -> LlmRequest:
        """
        Build a single ``LlmRequest`` covering all *gaps* in one prompt.

        The LLM is asked to return a JSON array with one response object per
        gap (in the same order).  Use this when there are multiple gaps so the
        pipeline makes one LLM call instead of N.

        Args:
            gaps:  All governance gaps for this agent.
            agent: The agent whose source code will be included in the prompt.

        Returns:
            A single ``LlmRequest`` whose expected response is a JSON array.
        """
        variable_context = self._format_variable_context(agent.source_code)
        gaps_section = "\n\n".join(
            _BATCH_GAP_TEMPLATE.format(
                index=i + 1,
                category=g.category.value,
                hook_name=g.hook.name,
                hook_description=g.hook.description,
                action=g.recommendation.action,
                instrumentation_hint=g.recommendation.instrumentation_hint,
                rationale=g.recommendation.rationale,
            )
            for i, g in enumerate(gaps)
        )
        user_prompt = _BATCH_USER_PROMPT_TEMPLATE.format(
            source_code=agent.source_code,
            variable_context=variable_context,
            gaps_section=gaps_section,
            gap_count=len(gaps),
        )
        return LlmRequest(
            prompt=user_prompt,
            system_prompt=_BATCH_SYSTEM_PROMPT,
            max_tokens=self._max_tokens * len(gaps),
            temperature=self._temperature,
            model=self._model,
        )

    @staticmethod
    def _format_variable_context(source_code: str) -> str:
        """Parse *source_code* and return a human-readable summary of each
        function's in-scope variable names for inclusion in the LLM prompt."""
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return "(source could not be parsed — variable names unavailable)"

        func_vars = _h.get_function_variable_names(tree)
        if not func_vars:
            return "(no functions found in source)"

        lines = []
        for fn_name, var_names in func_vars.items():
            if var_names:
                lines.append(f"- `{fn_name}`: {', '.join(f'`{v}`' for v in var_names)}")
            else:
                lines.append(f"- `{fn_name}`: (no local variables)")
        return "\n".join(lines)
