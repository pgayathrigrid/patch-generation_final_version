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
