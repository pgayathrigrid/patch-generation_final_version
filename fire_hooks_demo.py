"""
Direct hook firing demo.
Calls ollama_chat.run() directly — the 7 patched dispatch() calls execute
and print to terminal, proving your patches work end-to-end.
"""
import sys
sys.path.insert(0, "/Users/pgayathri/Downloads/Folder/awcp-mcp-temp-main/src")

# Monkey-patch ollama so we don't need a real model running
import awcp.runtime.ollama_client as _oc
_oc.ask_ollama = lambda prompt, model: f"[mock response to: {prompt[:40]}...]"

# Patch get_manager to print every dispatch call visibly
import awcp.agent_hooks as _ah
original_dispatch = _ah.dispatch

fired_events = []

def visible_dispatch(hook_type, ctx=None, **data):
    fired_events.append(hook_type)
    print(f"  🔥 HOOK FIRED: {hook_type.value:30s}  data={data}")
    return original_dispatch(hook_type, ctx, **data)

_ah.dispatch = visible_dispatch

# Also patch get_manager().dispatch
original_mgr_dispatch = _ah.get_manager().dispatch
def mgr_visible_dispatch(hook_type, ctx=None, **data):
    fired_events.append(hook_type)
    print(f"  🔥 HOOK FIRED: {hook_type.value:30s}  data={data}")
    return original_mgr_dispatch(hook_type, ctx, **data)
_ah.get_manager().dispatch = mgr_visible_dispatch

from awcp.runtime.schemas import PromptRequest

print("=" * 65)
print("Calling ollama_chat.run() — watch the patched hooks fire")
print("=" * 65)
print()

import awcp.agents.ollama_chat as agent

req = PromptRequest(input="say hello")
result = agent.run(req)

print()
print("=" * 65)
print(f"Agent returned: {result}")
print()
print(f"Total hooks fired: {len(fired_events)}")
for e in fired_events:
    print(f"  ✅ {e.value}")
print()
print("These are YOUR patches executing inside ollama_chat.py")
print("On the full team setup this fires into the dashboard live.")
print("=" * 65)
