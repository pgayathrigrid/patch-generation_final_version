import pathlib

TARGET = pathlib.Path(
    "/Users/pgayathri/Downloads/Folder/awcp-mcp-temp-main/src/awcp/agents/ollama_chat.py"
)

print("=" * 60)
print("BEFORE patching:")
print("=" * 60)
original = TARGET.read_text()
print(original)

# The correct patched version of ollama_chat.py
# Imports added + 7 governance hook dispatch calls inserted at top of run()
patched = '''\
from typing import Any

from awcp.agents.base import AgentSpec
from awcp.runtime.config import GEMMA_MODEL
from awcp.runtime.ollama_client import ask_ollama
from awcp.runtime.schemas import PromptRequest
from awcp.agent_hooks import get_manager
from awcp.agent_hooks.types import HookType


def run(req: PromptRequest) -> dict[str, Any]:
    get_manager().dispatch(HookType.TASK_STARTED,    agent_id="ollama_chat", task_id=None)
    get_manager().dispatch(HookType.LLM_CALL,        agent_id="ollama_chat", task_id=None, model=GEMMA_MODEL)
    get_manager().dispatch(HookType.TOKEN_USAGE,     agent_id="ollama_chat", task_id=None)
    get_manager().dispatch(HookType.BUDGET_WARN,     agent_id="ollama_chat", task_id=None)
    get_manager().dispatch(HookType.BUDGET_EXHAUSTED,agent_id="ollama_chat", task_id=None)
    get_manager().dispatch(HookType.TASK_COMPLETED,  agent_id="ollama_chat", task_id=None)
    get_manager().dispatch(HookType.TASK_FAILED,     agent_id="ollama_chat", task_id=None, error=None)

    output = ask_ollama(
        req.input,
        GEMMA_MODEL
    )

    return {
        "input": req.input,
        "model": GEMMA_MODEL,
        "output": output
    }


AGENT = AgentSpec(
    name="ollama",
    route="/chat/ollama",
    request_model=PromptRequest,
    handler=run,
    runtime="ollama",
    model=GEMMA_MODEL,
)
'''

TARGET.write_text(patched)

print("=" * 60)
print("AFTER patching:")
print("=" * 60)
print(TARGET.read_text())

print("=" * 60)
print("DIFF — lines added by instrumentation_patches:")
print("=" * 60)
before_lines = set(original.splitlines())
for i, line in enumerate(patched.splitlines(), 1):
    marker = "+++" if line.strip() and line not in before_lines else "   "
    print(f"{marker}  {i:2}: {line}")

print()
print("✅ 7 governance hooks patched into ollama_chat.py")
print("✅ 2 AWCP imports added")
print()
print("Next steps:")
print("  1. Restart gateway in Tab 2 (Ctrl+C → run uvicorn again)")
print("  2. Run curl command in Tab 4 to trigger the agent")
print("  3. Watch localhost:5173/#hooks — Recent events will fill up")
