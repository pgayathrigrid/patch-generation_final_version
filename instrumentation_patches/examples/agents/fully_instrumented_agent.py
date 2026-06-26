"""
FullyInstrumentedAgent — an AWCP agent with ALL 10 lifecycle hooks.

Demonstrates every AWCP lifecycle hook category:
  1. TASK_STARTED      — emitted at task entry
  2. LLM_CALL          — emitted before each LLM inference
  3. TOKEN_USAGE       — emitted after each LLM response
  4. TOOL_CALL         — emitted before each external tool invocation
  5. WEB_SEARCH        — emitted before each retrieval query
  6. SYNTHESIZE        — emitted at answer-synthesis time
  7. BUDGET_WARN       — emitted when token usage nears the threshold
  8. BUDGET_EXHAUSTED  — emitted when the token budget is exceeded
  9. TASK_COMPLETED    — emitted on successful task completion
 10. TASK_FAILED       — emitted on any task failure path

The hook implementations are stubs (print-based) so the file runs without
any external dependencies. Replace with real awcp_hooks SDK calls in production.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Stub AWCP hooks namespace (replace with real SDK import in production)
# ---------------------------------------------------------------------------

class _AwcpHooks:
    def task_started(self, task_id: str, agent_name: str, **ctx: Any) -> None:
        print(f"[AWCP] task_started task_id={task_id} agent={agent_name}")

    def task_completed(self, task_id: str, result_summary: str, **ctx: Any) -> None:
        print(f"[AWCP] task_completed task_id={task_id} summary={result_summary!r}")

    def task_failed(self, task_id: str, error_type: str, error_message: str, **ctx: Any) -> None:
        print(f"[AWCP] task_failed task_id={task_id} error={error_type}: {error_message}")

    def llm_call(self, model: str, prompt_preview: str, **ctx: Any) -> None:
        print(f"[AWCP] llm_call model={model} prompt_len={len(prompt_preview)}")

    def token_usage(self, prompt_tokens: int, completion_tokens: int, total_tokens: int, **ctx: Any) -> None:
        print(f"[AWCP] token_usage prompt={prompt_tokens} completion={completion_tokens} total={total_tokens}")

    def tool_call(self, tool_name: str, tool_input_summary: str, **ctx: Any) -> None:
        print(f"[AWCP] tool_call tool={tool_name} input={tool_input_summary!r}")

    def web_search(self, query: str, results_count: int, **ctx: Any) -> None:
        print(f"[AWCP] web_search query={query!r} results={results_count}")

    def synthesize(self, input_count: int, output_length: int, **ctx: Any) -> None:
        print(f"[AWCP] synthesize inputs={input_count} output_len={output_length}")

    def budget_warn(self, used_ratio: float, limit: int, agent_name: str, **ctx: Any) -> None:
        print(f"[AWCP] budget_warn ratio={used_ratio:.2f} limit={limit} agent={agent_name}")

    def budget_exhausted(self, used_ratio: float, agent_name: str, **ctx: Any) -> None:
        print(f"[AWCP] budget_exhausted ratio={used_ratio:.2f} agent={agent_name}")


awcp_hooks = _AwcpHooks()

AGENT_NAME = "FullyInstrumentedAgent"
BUDGET_TOKENS = 4096
WARN_THRESHOLD = 0.80


# ---------------------------------------------------------------------------
# Business logic stubs
# ---------------------------------------------------------------------------

def fetch_documents(query: str) -> List[str]:
    awcp_hooks.tool_call("document_store.fetch", f"query={query!r}")
    return [
        f"Document 1 about {query}: Lorem ipsum dolor sit amet.",
        f"Document 2 about {query}: Consectetur adipiscing elit.",
        f"Document 3 about {query}: Sed do eiusmod tempor incididunt.",
    ]


def web_lookup(query: str) -> List[str]:
    awcp_hooks.web_search(query, results_count=3)
    return [f"Web result about {query}: relevant finding."]


def call_llm(prompt: str, model: str = "claude-3-5-sonnet") -> tuple[str, int, int]:
    """Returns (response_text, prompt_tokens, completion_tokens)."""
    awcp_hooks.llm_call(model, prompt[:200])
    response = f"Summary: key findings from the provided context about the query."
    prompt_tokens = len(prompt.split())
    completion_tokens = len(response.split())
    awcp_hooks.token_usage(prompt_tokens, completion_tokens, prompt_tokens + completion_tokens)
    return response, prompt_tokens, completion_tokens


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(query: str) -> Dict[str, Any]:
    task_id = str(uuid.uuid4())[:8]
    awcp_hooks.task_started(task_id, AGENT_NAME, query=query)

    total_tokens_used = 0

    try:
        # Retrieve documents
        docs = fetch_documents(query)
        web_results = web_lookup(query)

        all_sources = docs + web_results
        context = "\n".join(all_sources)
        prompt = f"Query: {query}\n\nContext:\n{context}\n\nProvide a concise summary."

        # Check budget before LLM call
        estimated = len(prompt.split())
        if estimated / BUDGET_TOKENS >= WARN_THRESHOLD:
            awcp_hooks.budget_warn(estimated / BUDGET_TOKENS, BUDGET_TOKENS, AGENT_NAME)

        if estimated >= BUDGET_TOKENS:
            awcp_hooks.budget_exhausted(estimated / BUDGET_TOKENS, AGENT_NAME)
            awcp_hooks.task_failed(task_id, "BudgetExhausted", "Token budget exceeded before LLM call")
            return {"status": "failed", "reason": "budget_exhausted"}

        # Call LLM
        response, prompt_tokens, completion_tokens = call_llm(prompt)
        total_tokens_used = prompt_tokens + completion_tokens

        # Check budget after LLM call
        ratio = total_tokens_used / BUDGET_TOKENS
        if ratio >= 1.0:
            awcp_hooks.budget_exhausted(ratio, AGENT_NAME)

        # Synthesise final answer
        awcp_hooks.synthesize(input_count=len(all_sources), output_length=len(response))

        result = {
            "status": "completed",
            "query": query,
            "summary": response,
            "documents_used": len(docs),
            "web_results_used": len(web_results),
            "tokens_used": total_tokens_used,
        }
        awcp_hooks.task_completed(task_id, f"Summarised {len(all_sources)} sources")
        return result

    except Exception as exc:
        awcp_hooks.task_failed(task_id, type(exc).__name__, str(exc))
        return {"status": "failed", "reason": str(exc)}


if __name__ == "__main__":
    result = run("climate change research")
    print(result)
