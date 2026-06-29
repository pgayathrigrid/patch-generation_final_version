"""
PartialAgent — an AWCP agent with PARTIAL lifecycle instrumentation.

This agent has task_started, task_completed, and task_failed hooks using the
real AWCP dispatch pattern, but is missing:
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

from awcp.agent_hooks import get_manager
from awcp.agent_hooks.types import HookType

AGENT_ID = "partial-agent"


def fetch_documents(query: str) -> List[str]:
    # Missing: get_manager().dispatch(HookType.TOOL_CALL, ...)
    return [
        f"Document 1 about {query}: Lorem ipsum.",
        f"Document 2 about {query}: Consectetur adipiscing.",
    ]


def call_llm(prompt: str) -> str:
    # Missing: get_manager().dispatch(HookType.LLM_CALL, ...)
    # Missing: get_manager().dispatch(HookType.TOKEN_USAGE, ...)
    return f"Summary of {len(prompt)} char prompt: key findings identified."


def run(query: str) -> Dict[str, Any]:
    task_id = str(uuid.uuid4())[:8]
    get_manager().dispatch(HookType.TASK_STARTED, agent_id=AGENT_ID, task_id=task_id, query=query)

    try:
        docs = fetch_documents(query)
        # Missing: get_manager().dispatch(HookType.WEB_SEARCH, ...)
        prompt = f"Query: {query}\n\nContext:\n" + "\n".join(docs)
        response = call_llm(prompt)

        # Missing: get_manager().dispatch(HookType.SYNTHESIZE, ...)
        result = {
            "status": "completed",
            "query": query,
            "summary": response,
            "documents_used": len(docs),
        }
        get_manager().dispatch(HookType.TASK_COMPLETED, agent_id=AGENT_ID, task_id=task_id,
                               result_summary=f"Processed {len(docs)} documents")
        return result

    except Exception as exc:
        get_manager().dispatch(HookType.TASK_FAILED, agent_id=AGENT_ID, task_id=task_id,
                               error=str(exc), error_type=type(exc).__name__)
        return {"status": "failed", "reason": str(exc)}


if __name__ == "__main__":
    result = run("renewable energy policy")
    print(result)
