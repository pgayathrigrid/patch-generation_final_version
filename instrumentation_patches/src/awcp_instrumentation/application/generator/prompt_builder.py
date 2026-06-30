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

## AWCP Hook Dispatch Pattern

ALL hooks MUST be dispatched using the real AWCP hook system — never use \
custom classes or print statements. The exact pattern is:

    from awcp.agent_hooks import get_manager
    from awcp.agent_hooks.types import HookType

    get_manager().dispatch(HookType.<TYPE>, agent_id=<agent_id_var>, task_id=<task_id_var>)

The "import_additions" field MUST always include BOTH of these imports \
(unless they are already present in the source):
    "from awcp.agent_hooks import get_manager"
    "from awcp.agent_hooks.types import HookType"

## Response Format

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

## Strict Rules

- Address ONLY the specified governance gap. Do not add unrelated code.
- NEVER restructure, rewrite, or modify existing function bodies. Only INSERT \
the single dispatch call. Do not add helper variables, do not move existing \
statements, do not add a new return statement.
- code_fragment MUST contain only the single get_manager().dispatch(...) call \
(one statement). If numeric values like token counts are unavailable, use 0 \
or None as fallbacks. Do not compute them with new variable assignments.
- Keep additions minimal. Do not refactor, rename, or restructure existing code.
- Do not duplicate imports that already exist in the source.
- All code_fragment values must be syntactically valid Python.
- code_fragment values MUST NOT contain any leading indentation. Write every \
line starting at column 0. Relative indentation within the fragment (e.g. \
for nested if-blocks) is allowed, but the outermost level must be column 0. \
The instrumentation engine automatically applies the correct indentation when \
it inserts the fragment into the target function body.
- If no imports are needed, return an empty list: "import_additions": [].
- Use ONLY variable names listed in the "Available Variables" section for the \
target function. For location="before_function_body", only use variables that \
are function parameters or module-level constants — NOT local variables \
assigned inside the function body (they do not exist yet at that point). If a \
needed variable (e.g. task_id) is defined inside the function, use None as the \
fallback for task_id.
- Do NOT access attributes of parameter objects (e.g. do NOT write req.agent_id \
or req.task_id). Only use bare top-level variable names from the Available \
Variables list. If no agent_id variable is in scope, use a descriptive string \
literal such as "agent". If no task_id variable is in scope, use None.
- Do NOT use exception handler variables (e.g. `e` from `except Exception as e:`) \
— they only exist inside the except block and are not available at the insertion \
point. If you need to pass an error, use None or an empty string as a fallback.
- Never generate custom hook classes, stub classes, or print-based hooks. \
Always use get_manager().dispatch(HookType.<TYPE>, ...).
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

## AWCP Hook Dispatch Pattern

ALL hooks MUST be dispatched using the real AWCP hook system — never use \
custom classes or print statements. The exact pattern is:

    from awcp.agent_hooks import get_manager
    from awcp.agent_hooks.types import HookType

    get_manager().dispatch(HookType.<TYPE>, agent_id=<agent_id_var>, task_id=<task_id_var>)

Every object in your response array MUST include these two imports in \
"import_additions" (unless already present in the source):
    "from awcp.agent_hooks import get_manager"
    "from awcp.agent_hooks.types import HookType"

## Response Format

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

## Strict Rules

- Address ONLY the governance gap described for each array element.
- NEVER restructure, rewrite, or modify existing function bodies. Only INSERT \
the single dispatch call. Do not add helper variables, do not move existing \
statements, do not add a new return statement.
- code_fragment MUST contain only the single get_manager().dispatch(...) call \
(one statement). If numeric values like token counts are unavailable, use 0 \
or None as fallbacks. Do not compute them with new variable assignments.
- Each array element has its own Hook Name. Use EXACTLY that HookType for that \
element's dispatch call — do not repeat the same HookType across multiple \
elements. If Gap 1 is TASK_STARTED, Gap 2 is TASK_COMPLETED, Gap 3 is \
TASK_FAILED — each must dispatch its own distinct type.
- Keep additions minimal. Do not refactor, rename, or restructure existing code.
- Do not duplicate imports that already exist in the source.
- All code_fragment values must be syntactically valid Python.
- code_fragment values MUST NOT contain any leading indentation. Write every \
line starting at column 0. Relative indentation within the fragment (e.g. \
for nested if-blocks) is allowed, but the outermost level must be column 0. \
The instrumentation engine automatically applies the correct indentation when \
it inserts the fragment into the target function body.
- If no imports are needed, return an empty list: "import_additions": [].
- Use ONLY variable names listed in the "Available Variables" section for the \
target function. For location="before_function_body", only use variables that \
are function parameters or module-level constants — NOT local variables \
assigned inside the function body (they do not exist yet at that point). If a \
needed variable (e.g. task_id) is defined inside the function, use None as the \
fallback for task_id.
- Do NOT access attributes of parameter objects (e.g. do NOT write req.agent_id \
or req.task_id). Only use bare top-level variable names from the Available \
Variables list. If no agent_id variable is in scope, use a descriptive string \
literal such as "agent". If no task_id variable is in scope, use None.
- Do NOT use exception handler variables (e.g. `e` from `except Exception as e:`) \
— they only exist inside the except block and are not available at the insertion \
point. If you need to pass an error, use None or an empty string as a fallback.
- Never generate custom hook classes, stub classes, or print-based hooks. \
Always use get_manager().dispatch(HookType.<TYPE>, ...).
- Respond ONLY with the JSON array. No markdown fences, no preamble, no \
trailing explanation outside the JSON array.
"""

_BATCH_GAP_TEMPLATE = """\
### Gap {index}: {category}

**Hook Name:** `{hook_name}`
**REQUIRED HookType (use EXACTLY this, no other):** `HookType.{hook_type_name}`
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
                hook_type_name=g.category.name,
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
        """Parse *source_code* and return a per-function variable summary.

        Separates parameters (available at function entry — safe to use in
        before_function_body or inline patches) from local variables (assigned
        during the function body — NOT available at the very start).
        """
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return "(source could not be parsed — variable names unavailable)"

        lines = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            # Collect parameters — available immediately at function entry
            args = node.args
            params = []
            for arg in args.args + args.posonlyargs + args.kwonlyargs:
                params.append(arg.arg)
            if args.vararg:
                params.append(args.vararg.arg)
            if args.kwarg:
                params.append(args.kwarg.arg)

            # Collect local variables — only available AFTER they are assigned
            locals_set: set = set()
            for child in ast.walk(node):
                if isinstance(child, ast.Assign):
                    for t in child.targets:
                        locals_set.update(_h._extract_assign_names(t))
                elif isinstance(child, (ast.AnnAssign, ast.AugAssign)):
                    locals_set.update(_h._extract_assign_names(child.target))
                elif isinstance(child, (ast.For, ast.AsyncFor)):
                    locals_set.update(_h._extract_assign_names(child.target))
                elif isinstance(child, ast.withitem) and child.optional_vars:
                    locals_set.update(_h._extract_assign_names(child.optional_vars))
                # ExceptHandler names (e.g. `e` in `except Exception as e:`) are
                # intentionally excluded — they only exist inside the except block and
                # confuse the LLM into using them at insertion points where they are
                # not in scope.
            # Remove params from locals to avoid duplication
            local_vars = sorted(locals_set - set(params))

            param_str = ", ".join(f"`{p}`" for p in params) if params else "none"
            local_str = ", ".join(f"`{v}`" for v in local_vars) if local_vars else "none"
            lines.append(
                f"- `{node.name}`:\n"
                f"    Parameters (safe at function start): {param_str}\n"
                f"    Locals (assigned inside body — NOT available at function start): {local_str}"
            )

        if not lines:
            return "(no functions found in source)"
        return "\n".join(lines)
