"""
BareAgent — an AWCP agent with NO lifecycle instrumentation.

This agent performs a simple document summarisation task but has zero
AWCP lifecycle hooks: no task_started/completed/failed events, no LLM-call
tracking, no token usage recording, no tool-call or web-search hooks, no
synthesis tracking, and no budget monitoring.

It serves as the "before patching" baseline for the instrumentation engine.
"""
from __future__ import annotations

from typing import Any, Dict, List


def fetch_documents(query: str) -> List[str]:
    """Stub: returns synthetic document fragments."""
    return [
        f"Document 1 about {query}: Lorem ipsum dolor sit amet.",
        f"Document 2 about {query}: Consectetur adipiscing elit.",
        f"Document 3 about {query}: Sed do eiusmod tempor incididunt.",
    ]


def call_llm(prompt: str) -> str:
    """Stub: simulates an LLM response without a real API call."""
    return f"Summary based on prompt ({len(prompt)} chars): key findings identified."


def run(query: str, budget_tokens: int = 4096) -> Dict[str, Any]:
    """Execute the summarisation task — no AWCP hooks present."""
    docs = fetch_documents(query)
    combined = "\n".join(docs)

    prompt = f"Summarise the following documents for query '{query}':\n\n{combined}"
    response = call_llm(prompt)

    return {
        "status": "completed",
        "query": query,
        "summary": response,
        "documents_used": len(docs),
    }


if __name__ == "__main__":
    result = run("climate change research")
    print(result)
