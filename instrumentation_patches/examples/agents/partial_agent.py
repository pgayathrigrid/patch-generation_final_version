"""
PartialAgent — an AWCP agent with PARTIAL lifecycle instrumentation.

This agent has task_started, task_completed, and task_failed hooks, but
is missing the following AWCP lifecycle hooks:
  - LLM_CALL       (LLM calls are not instrumented)
  - TOKEN_USAGE    (token counts are not recorded)
  - TOOL_CALL      (tool invocations are not tracked)
  - WEB_SEARCH     (retrieval queries are not logged)
  - SYNTHESIZE     (synthesis step has no hook)
  - BUDGET_WARN    (no early warning before budget exhaustion)
  - BUDGET_EXHAUSTED (no hook when budget is exceeded)

It demonstrates a mid-instrumentation state and serves as a target for
the patch engine to fill the remaining gaps.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Stub AWCP hooks — only task lifecycle hooks present
# ---------------------------------------------------------------------------

class _AwcpHooks:
    def task_started(self, task_id: str, agent_name: str, **ctx: Any) -> None:
        print(f"[AWCP] task_started task_id={task_id} agent={agent_name}")

    def task_completed(self, task_id: str, result_summary: str, **ctx: Any) -> None:
        print(f"[AWCP] task_completed task_id={task_id} summary={result_summary!r}")

    def task_failed(self, task_id: str, error_type: str, error_message: str, **ctx: Any) -> None:
        print(f"[AWCP] task_failed task_id={task_id} error={error_type}: {error_message}")


awcp_hooks = _AwcpHooks()

AGENT_NAME = "PartialAgent"


# ---------------------------------------------------------------------------
# Business logic stubs (un-instrumented)
# ---------------------------------------------------------------------------

def fetch_documents(query: str) -> List[str]:
    # Missing: awcp_hooks.tool_call(...)
    return [
        f"Document 1 about {query}: Lorem ipsum.",
        f"Document 2 about {query}: Consectetur adipiscing.",
    ]


def call_llm(prompt: str) -> str:
    # Missing: awcp_hooks.llm_call(...) and awcp_hooks.token_usage(...)
    return f"Summary of {len(prompt)} char prompt: key findings identified."


def run(query: str) -> Dict[str, Any]:
    task_id = str(uuid.uuid4())[:8]
    awcp_hooks.task_started(task_id, AGENT_NAME, query=query)

    try:
        docs = fetch_documents(query)
        # Missing: awcp_hooks.web_search(...)
        prompt = f"Query: {query}\n\nContext:\n" + "\n".join(docs)
        response = call_llm(prompt)

        # Missing: awcp_hooks.synthesize(...)
        result = {
            "status": "completed",
            "query": query,
            "summary": response,
            "documents_used": len(docs),
        }
        awcp_hooks.task_completed(task_id, f"Processed {len(docs)} documents")
        return result

    except Exception as exc:
        awcp_hooks.task_failed(task_id, type(exc).__name__, str(exc))
        return {"status": "failed", "reason": str(exc)}


if __name__ == "__main__":
    result = run("renewable energy policy")
    print(result)
