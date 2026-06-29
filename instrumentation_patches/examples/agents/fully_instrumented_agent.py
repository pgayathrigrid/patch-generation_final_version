"""
FullyInstrumentedAgent — an AWCP agent with ALL lifecycle hooks using the
real AWCP dispatch pattern.

Demonstrates every required hook category using get_manager().dispatch():

  HookType.TASK_STARTED      — emitted at task entry
  HookType.LLM_CALL          — emitted before each LLM inference
  HookType.TOKEN_USAGE       — emitted after each LLM response
  HookType.TOOL_CALL         — emitted before each external tool invocation
  HookType.WEB_SEARCH        — emitted before each retrieval query
  HookType.SYNTHESIZE        — emitted at answer-synthesis time
  HookType.BUDGET_WARN       — emitted when token usage nears the threshold
  HookType.BUDGET_EXHAUSTED  — emitted when the token budget is exceeded
  HookType.TASK_COMPLETED    — emitted on successful task completion
  HookType.TASK_FAILED       — emitted on any task failure path
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Tuple

from awcp.agent_hooks import get_manager
from awcp.agent_hooks.types import HookType

AGENT_ID = "fully-instrumented-agent"
BUDGET_TOKENS = 4096
WARN_THRESHOLD = 0.80


def fetch_documents(query: str, agent_id: str, task_id: str) -> List[str]:
    get_manager().dispatch(HookType.TOOL_CALL, agent_id=agent_id, task_id=task_id,
                           tool_name="document_store.fetch", action=f"fetch:{query}")
    return [
        f"Document 1 about {query}: Lorem ipsum dolor sit amet.",
        f"Document 2 about {query}: Consectetur adipiscing elit.",
        f"Document 3 about {query}: Sed do eiusmod tempor incididunt.",
    ]


def web_lookup(query: str, agent_id: str, task_id: str) -> List[str]:
    get_manager().dispatch(HookType.WEB_SEARCH, agent_id=agent_id, task_id=task_id,
                           query=query, results_count=1)
    return [f"Web result about {query}: relevant finding."]


def call_llm(
    prompt: str,
    agent_id: str,
    task_id: str,
    model: str = "claude-sonnet-4-6",
) -> Tuple[str, int, int]:
    get_manager().dispatch(HookType.LLM_CALL, agent_id=agent_id, task_id=task_id,
                           model=model, prompt_len=len(prompt))
    response = "Summary: key findings from the provided context about the query."
    prompt_tokens = len(prompt.split())
    completion_tokens = len(response.split())
    get_manager().dispatch(HookType.TOKEN_USAGE, agent_id=agent_id, task_id=task_id,
                           prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                           total_tokens=prompt_tokens + completion_tokens)
    return response, prompt_tokens, completion_tokens


def run(query: str) -> Dict[str, Any]:
    task_id = str(uuid.uuid4())[:8]
    agent_id = AGENT_ID

    get_manager().dispatch(HookType.TASK_STARTED, agent_id=agent_id, task_id=task_id,
                           query=query)
    total_tokens_used = 0

    try:
        docs = fetch_documents(query, agent_id, task_id)
        web_results = web_lookup(query, agent_id, task_id)

        all_sources = docs + web_results
        context = "\n".join(all_sources)
        prompt = f"Query: {query}\n\nContext:\n{context}\n\nProvide a concise summary."

        estimated = len(prompt.split())
        if estimated / BUDGET_TOKENS >= WARN_THRESHOLD:
            get_manager().dispatch(HookType.BUDGET_WARN, agent_id=agent_id, task_id=task_id,
                                   used_ratio=estimated / BUDGET_TOKENS, limit=BUDGET_TOKENS)

        if estimated >= BUDGET_TOKENS:
            get_manager().dispatch(HookType.BUDGET_EXHAUSTED, agent_id=agent_id, task_id=task_id,
                                   used_ratio=estimated / BUDGET_TOKENS)
            get_manager().dispatch(HookType.TASK_FAILED, agent_id=agent_id, task_id=task_id,
                                   error="Token budget exceeded before LLM call",
                                   error_type="BudgetExhausted")
            return {"status": "failed", "reason": "budget_exhausted"}

        response, prompt_tokens, completion_tokens = call_llm(prompt, agent_id, task_id)
        total_tokens_used = prompt_tokens + completion_tokens

        if total_tokens_used / BUDGET_TOKENS >= 1.0:
            get_manager().dispatch(HookType.BUDGET_EXHAUSTED, agent_id=agent_id, task_id=task_id,
                                   used_ratio=total_tokens_used / BUDGET_TOKENS)

        get_manager().dispatch(HookType.SYNTHESIZE, agent_id=agent_id, task_id=task_id,
                               input_count=len(all_sources), output_length=len(response))

        result = {
            "status": "completed",
            "query": query,
            "summary": response,
            "documents_used": len(docs),
            "web_results_used": len(web_results),
            "tokens_used": total_tokens_used,
        }
        get_manager().dispatch(HookType.TASK_COMPLETED, agent_id=agent_id, task_id=task_id,
                               result_summary=f"Summarised {len(all_sources)} sources")
        return result

    except Exception as exc:
        get_manager().dispatch(HookType.TASK_FAILED, agent_id=agent_id, task_id=task_id,
                               error=str(exc), error_type=type(exc).__name__)
        return {"status": "failed", "reason": str(exc)}


if __name__ == "__main__":
    result = run("climate change research")
    print(result)
