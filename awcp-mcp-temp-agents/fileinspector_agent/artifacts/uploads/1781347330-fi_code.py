from awcp.agent_hooks import get_manager
from awcp.agent_hooks.types import HookType
get_manager().dispatch(HookType.FEATURE_FLAG, agent_id=None, task_id=None, flag_name=None, enabled=False)
get_manager().dispatch(HookType.RECOVERY, agent_id=None, task_id=None, attempt=1, reason=None)
get_manager().dispatch(HookType.TOKEN_USAGE, agent_id=None, task_id=None, prompt_tokens=0, completion_tokens=0)
get_manager().dispatch(HookType.DEGRADATION, agent_id=None, task_id=None, from_mode=None, to_mode=None)
get_manager().dispatch(HookType.POLICY, agent_id=None, task_id=None, action=None, decision=None, write=True, mode='policy')
get_manager().dispatch(HookType.BUDGET_WARN, agent_id=None, task_id=None, used_ratio=0.8)
get_manager().dispatch(HookType.WEB_SEARCH, agent_id=None, task_id=None, query=None)
get_manager().dispatch(HookType.SYNTHESIZE, agent_id=None, task_id=None)
get_manager().dispatch(HookType.APPROVAL, agent_id=None, task_id=None, action=None, risk=None)
get_manager().dispatch(HookType.BUDGET_EXHAUSTED, agent_id=None, task_id=None, used_ratio=1.0)
get_manager().dispatch(HookType.TOOL_CALL, agent_id=None, task_id=None, tool_name=None, action=None)
get_manager().dispatch(HookType.LLM_CALL, agent_id=None, task_id=None, model=None)
get_manager().dispatch(HookType.TASK_FAILED, agent_id=None, task_id=None, error="Hypothetical task failure in main execution block")
def fib(n):
    get_manager().dispatch(HookType.OBSERVABILITY, agent_id=None, task_id=None, checkpoint="fib_loop_completed")
    get_manager().dispatch(HookType.TASK_COMPLETED, agent_id=None, task_id=None)
    get_manager().dispatch(HookType.TASK_STARTED, agent_id=None, task_id=None)
    a,b=0,1
    for _ in range(n): a,b=b,a+b
    return a

if __name__=="__main__":
    print(fib(10))
