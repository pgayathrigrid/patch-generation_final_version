"""
Default governance risk catalog.

Each ``HookCategory`` maps to a ``(GovernanceRisk, GovernanceRecommendation)``
pair that reflects standard AWCP governance policy.

This catalog is intentionally decoupled from the reporter implementation so
that organisations can provide their own severity calibrations by injecting a
custom ``RiskCatalog`` into ``GovernanceGapReporter``.

Nothing in this module generates code.  ``instrumentation_hint`` values are
natural-language descriptions that the LLM Patch Generator will interpret.
"""
from __future__ import annotations

from typing import Dict, Tuple

from awcp_instrumentation.application.gap_reporter.models import (
    GovernanceRecommendation,
    GovernanceRisk,
    RiskSeverity,
)
from awcp_instrumentation.domain.enums.hook_category import HookCategory


# Type alias: maps each category to (risk, recommendation).
RiskCatalog = Dict[HookCategory, Tuple[GovernanceRisk, GovernanceRecommendation]]


DEFAULT_RISK_CATALOG: RiskCatalog = {
    HookCategory.TASK_STARTED: (
        GovernanceRisk(
            severity=RiskSeverity.HIGH,
            description="No hook fires when a task begins; task lifecycle is invisible to governance.",
            impact=(
                "Operators cannot track when tasks start, which agents are active, or "
                "whether tasks are being dispatched correctly. Debugging task attribution "
                "requires log archaeology rather than structured event data."
            ),
        ),
        GovernanceRecommendation(
            action="Emit an AWCP task_started hook at the entry point of every task handler.",
            rationale=(
                "Task lifecycle observability is a baseline AWCP governance requirement. "
                "Without a task_started event the audit trail is incomplete and incident "
                "timelines cannot be reconstructed."
            ),
            instrumentation_hint=(
                "Call get_manager().dispatch(HookType.TASK_STARTED, agent_id=agent_id, task_id=task_id) at the "
                "very beginning of each task handler, before any business logic runs. "
                "Include task_id and agent_name in every call."
            ),
            priority=2,
        ),
    ),

    HookCategory.TASK_COMPLETED: (
        GovernanceRisk(
            severity=RiskSeverity.HIGH,
            description="No hook fires when a task completes; successful outcomes are not recorded.",
            impact=(
                "Governance dashboards cannot report task throughput or success rates. "
                "Compliance auditors cannot confirm that tasks finished cleanly. "
                "Task duration cannot be computed without paired start/complete events."
            ),
        ),
        GovernanceRecommendation(
            action="Emit an AWCP task_completed hook at every successful task exit point.",
            rationale=(
                "Paired task_started / task_completed events are required for lifecycle "
                "tracking, SLA monitoring, and audit completeness."
            ),
            instrumentation_hint=(
                "Call get_manager().dispatch(HookType.TASK_COMPLETED, agent_id=agent_id, task_id=task_id) at "
                "each successful return point in the task handler. Pass the same task_id "
                "used in the corresponding task_started call."
            ),
            priority=2,
        ),
    ),

    HookCategory.TASK_FAILED: (
        GovernanceRisk(
            severity=RiskSeverity.CRITICAL,
            description="No hook fires when a task fails; failures are silent to the governance layer.",
            impact=(
                "Failed tasks go unrecorded until a human notices missing output. "
                "Root-cause analysis must rely on raw exception traces rather than "
                "structured failure events. Repeated failures cannot trigger automated alerts."
            ),
        ),
        GovernanceRecommendation(
            action="Emit an AWCP task_failed hook in every exception handler and early-exit path.",
            rationale=(
                "Task failure events are critical governance signals. They drive alerting, "
                "retry policies, and incident response. Without them, failures are invisible "
                "to the platform."
            ),
            instrumentation_hint=(
                "Call get_manager().dispatch(HookType.TASK_FAILED, agent_id=agent_id, task_id=task_id, error=str(error)) "
                "inside every except block and at each non-success return path. Include the "
                "exception type name and a short description."
            ),
            priority=1,
        ),
    ),

    HookCategory.LLM_CALL: (
        GovernanceRisk(
            severity=RiskSeverity.CRITICAL,
            description="LLM calls are not instrumented; prompt content and model responses are unaudited.",
            impact=(
                "Sensitive prompts or model outputs may leave the system without being "
                "recorded. Policy violations inside prompts cannot be detected. "
                "Cost attribution by LLM call is impossible without per-call events."
            ),
        ),
        GovernanceRecommendation(
            action="Emit an AWCP llm_call hook before every LLM invocation.",
            rationale=(
                "LLM call hooks are the primary mechanism for prompt auditing, cost tracking, "
                "and PII detection. They are mandatory in regulated environments."
            ),
            instrumentation_hint=(
                "Call get_manager().dispatch(HookType.LLM_CALL, agent_id=agent_id, task_id=task_id, model=model) immediately "
                "before every call to an LLM client. Do not include the full prompt in the "
                "hook payload if it may contain PII; use a redacted summary instead."
            ),
            priority=1,
        ),
    ),

    HookCategory.SYNTHESIZE: (
        GovernanceRisk(
            severity=RiskSeverity.HIGH,
            description="Synthesis steps are not instrumented; final-answer construction is untracked.",
            impact=(
                "The governance layer cannot observe how the agent assembles its final "
                "answer from retrieved evidence. Hallucination risks at synthesis time "
                "cannot be monitored or mitigated by downstream hooks."
            ),
        ),
        GovernanceRecommendation(
            action="Emit an AWCP synthesize hook at the start of each answer-synthesis step.",
            rationale=(
                "Synthesis is the highest-risk step in RAG and agentic workflows. "
                "Instrumenting it enables hallucination monitoring, citation checking, "
                "and quality gate enforcement."
            ),
            instrumentation_hint=(
                "Call get_manager().dispatch(HookType.SYNTHESIZE, agent_id=agent_id, task_id=task_id) at the "
                "beginning of the synthesis function, after retrieving supporting evidence "
                "but before generating the final response."
            ),
            priority=2,
        ),
    ),

    HookCategory.TOOL_CALL: (
        GovernanceRisk(
            severity=RiskSeverity.CRITICAL,
            description="Tool invocations are not instrumented; external side-effects are unrecorded.",
            impact=(
                "The agent can call external tools (APIs, databases, file systems) without "
                "any governance record. Unauthorised or erroneous tool calls cannot be "
                "detected, blocked, or audited after the fact."
            ),
        ),
        GovernanceRecommendation(
            action="Emit an AWCP tool_call hook before every external tool invocation.",
            rationale=(
                "Tool calls represent the agent's interface with the outside world. "
                "They must be instrumented for policy enforcement, rate limiting, and "
                "audit completeness. This is a hard AWCP governance requirement."
            ),
            instrumentation_hint=(
                "Call get_manager().dispatch(HookType.TOOL_CALL, agent_id=agent_id, task_id=task_id, tool_name=tool_name, action=action) "
                "immediately before invoking any external tool. The hook must fire before "
                "the tool executes so that a policy check can block the call if needed."
            ),
            priority=1,
        ),
    ),

    HookCategory.WEB_SEARCH: (
        GovernanceRisk(
            severity=RiskSeverity.HIGH,
            description="Web search calls are not instrumented; retrieval queries are unaudited.",
            impact=(
                "Search queries may leak sensitive context to external search providers "
                "without any governance record. The content retrieved cannot be inspected "
                "for relevance or safety before being fed into the LLM."
            ),
        ),
        GovernanceRecommendation(
            action="Emit an AWCP web_search hook before every retrieval or web search call.",
            rationale=(
                "Web search instrumentation enables query auditing, result filtering, and "
                "data-provenance tracking. It is required when agents perform retrieval "
                "over external or user-controlled content."
            ),
            instrumentation_hint=(
                "Call get_manager().dispatch(HookType.WEB_SEARCH, agent_id=agent_id, task_id=task_id, query=query) immediately "
                "before the search client is invoked. Pass the raw query so that policy "
                "hooks can inspect or redact it."
            ),
            priority=2,
        ),
    ),

    HookCategory.TOKEN_USAGE: (
        GovernanceRisk(
            severity=RiskSeverity.MEDIUM,
            description="Token consumption is not tracked; cost and quota management is blind.",
            impact=(
                "The platform cannot enforce per-agent or per-task token budgets. "
                "Runaway agents may exhaust shared quota without warning. "
                "Cost attribution across teams or tenants is impossible."
            ),
        ),
        GovernanceRecommendation(
            action="Emit an AWCP token_usage hook after each LLM response to record token counts.",
            rationale=(
                "Token usage events are the foundation of cost governance. Without them "
                "budgets cannot be enforced, anomalies cannot be detected, and chargeback "
                "reports cannot be generated."
            ),
            instrumentation_hint=(
                "Call get_manager().dispatch(HookType.TOKEN_USAGE, agent_id=agent_id, task_id=task_id) "
                "immediately after receiving each LLM response. Add prompt_tokens and completion_tokens "
                "as extra kwargs so the hook manager can forward them to OTel metrics."
            ),
            priority=3,
        ),
    ),

    HookCategory.BUDGET_WARN: (
        GovernanceRisk(
            severity=RiskSeverity.HIGH,
            description="No early warning fires when token usage approaches the budget threshold.",
            impact=(
                "Agents consume budget silently until it is exhausted. There is no "
                "opportunity to reduce scope, switch to a cheaper model, or notify "
                "operators before the hard budget limit is hit."
            ),
        ),
        GovernanceRecommendation(
            action="Emit an AWCP budget_warn hook when cumulative token usage exceeds the warning threshold.",
            rationale=(
                "Budget warnings give operators and the agent itself an opportunity to "
                "adapt before a hard budget stop. They are a required escalation step "
                "between normal operation and budget exhaustion."
            ),
            instrumentation_hint=(
                "Call get_manager().dispatch(HookType.BUDGET_WARN, agent_id=agent_id, task_id=task_id) "
                "when cumulative token or cost usage crosses the warning threshold "
                "(typically 80 % of the configured budget). Include used_ratio as a "
                "float between 0 and 1."
            ),
            priority=2,
        ),
    ),

    HookCategory.BUDGET_EXHAUSTED: (
        GovernanceRisk(
            severity=RiskSeverity.CRITICAL,
            description="No hook fires when the agent exhausts its budget; hard stops are unrecorded.",
            impact=(
                "Budget exhaustion events are not captured in the audit trail. "
                "Downstream systems receive no structured signal that the agent stopped "
                "due to budget constraints rather than an error. Quota violations cannot "
                "be tracked or reported to cost-governance stakeholders."
            ),
        ),
        GovernanceRecommendation(
            action="Emit an AWCP budget_exhausted hook immediately when the agent hits its budget limit.",
            rationale=(
                "Budget exhaustion is a governance-critical event. It must be recorded "
                "so that platform operators can enforce quotas, trigger alerts, and "
                "attribute costs to the correct team or task."
            ),
            instrumentation_hint=(
                "Call get_manager().dispatch(HookType.BUDGET_EXHAUSTED, agent_id=agent_id, task_id=task_id) as "
                "the first action inside the budget-exhaustion handler. Set used_ratio to "
                "1.0 (or the actual overage ratio) and include the agent name and task id."
            ),
            priority=1,
        ),
    ),

    HookCategory.OBSERVABILITY: (
        GovernanceRisk(
            severity=RiskSeverity.MEDIUM,
            description="No observability checkpoints emit intermediate state; agent internals are opaque.",
            impact=(
                "Operators cannot inspect what the agent computed between task start and "
                "completion. Debugging regressions requires log archaeology. Monitoring "
                "dashboards have no intermediate data points to surface anomalies early."
            ),
        ),
        GovernanceRecommendation(
            action="Emit AWCP observability hooks at key checkpoints throughout the agent's execution.",
            rationale=(
                "Observability checkpoints give operators a live window into the agent's "
                "intermediate state. They are essential for debugging, alerting, and "
                "producing meaningful traces in the governance dashboard."
            ),
            instrumentation_hint=(
                "Call get_manager().dispatch(HookType.STEP, agent_id=agent_id, task_id=task_id, checkpoint=checkpoint_name) at each "
                "significant intermediate step — after retrieval, after each reasoning "
                "pass, and before final synthesis. Use a descriptive checkpoint_name so "
                "traces are self-documenting."
            ),
            priority=3,
        ),
    ),

    HookCategory.POLICY: (
        GovernanceRisk(
            severity=RiskSeverity.HIGH,
            description="Policy gate evaluations are not instrumented; gate outcomes are unaudited.",
            impact=(
                "Governance auditors cannot verify which policy rules were evaluated "
                "for each action, or whether the agent respected gate decisions. "
                "Policy drift and misconfigured gates cannot be detected without "
                "structured evaluation records."
            ),
        ),
        GovernanceRecommendation(
            action="Emit an AWCP policy_check hook at every governance gate evaluation.",
            rationale=(
                "Policy check events are the primary audit signal for governance "
                "compliance. They must be recorded for every gate evaluation so that "
                "auditors can reconstruct the full policy decision history for any task."
            ),
            instrumentation_hint=(
                "Call get_manager().dispatch(HookType.GATE_EVALUATED, agent_id=agent_id, task_id=task_id, action=action, decision=decision, write=True, mode='policy') "
                "immediately after each policy gate returns a decision. Pass the exact "
                "policy identifier and the allow/deny outcome so the audit trail is "
                "unambiguous."
            ),
            priority=2,
        ),
    ),

    HookCategory.APPROVAL: (
        GovernanceRisk(
            severity=RiskSeverity.HIGH,
            description="Human approval requests are not instrumented; high-risk actions may proceed unrecorded.",
            impact=(
                "There is no audit trail of which actions required human review, who "
                "approved them, or how long approval took. Compliance reports cannot "
                "confirm that required human oversight actually occurred."
            ),
        ),
        GovernanceRecommendation(
            action="Emit an AWCP approval_request hook whenever the agent requests human approval.",
            rationale=(
                "Human-in-the-loop governance requires a verifiable record of every "
                "approval request. Without it, there is no way to demonstrate that "
                "oversight happened, which is a hard requirement in regulated environments."
            ),
            instrumentation_hint=(
                "Call get_manager().dispatch(HookType.APPROVAL_REQUIRED, agent_id=agent_id, task_id=task_id, action=action, risk=risk_level) before "
                "the agent suspends execution to wait for a human decision. Include the "
                "action description and its assessed risk level so the approver has full "
                "context in the governance dashboard."
            ),
            priority=1,
        ),
    ),

    HookCategory.FEATURE_FLAG: (
        GovernanceRisk(
            severity=RiskSeverity.LOW,
            description="Feature flag evaluations are not tracked; flag-driven behaviour changes are invisible.",
            impact=(
                "Operators cannot tell which feature flags were active during a task, "
                "making it impossible to reproduce issues caused by flag changes. "
                "Gradual rollouts cannot be monitored for behavioural regressions."
            ),
        ),
        GovernanceRecommendation(
            action="Emit an AWCP feature_flag hook at each feature flag evaluation.",
            rationale=(
                "Feature flag events allow the governance layer to correlate behavioural "
                "changes with flag state. This is essential for safe rollouts and for "
                "auditing which code paths were active during any given task."
            ),
            instrumentation_hint=(
                "Call get_manager().dispatch(HookType.SIGNAL_RECEIVED, agent_id=agent_id, task_id=task_id, flag_name=flag_name, enabled=enabled) immediately "
                "after evaluating a feature flag. Pass the flag's canonical name and its "
                "resolved boolean value so the audit trail captures the exact flag state "
                "at execution time."
            ),
            priority=4,
        ),
    ),

    HookCategory.RECOVERY: (
        GovernanceRisk(
            severity=RiskSeverity.MEDIUM,
            description="Recovery and retry attempts are not instrumented; failure loops are invisible.",
            impact=(
                "Repeated failures masked by silent retries exhaust budget and degrade "
                "service without any governance signal. Operators cannot distinguish a "
                "single clean execution from one that silently retried ten times."
            ),
        ),
        GovernanceRecommendation(
            action="Emit an AWCP recovery hook at the start of each retry or recovery attempt.",
            rationale=(
                "Recovery events are leading indicators of instability. Tracking them "
                "enables the platform to enforce retry budgets, trigger alerts on "
                "repeated failures, and surface degraded agents before they exhaust "
                "their token or time budgets."
            ),
            instrumentation_hint=(
                "Call get_manager().dispatch(HookType.SIGNAL_RECEIVED, agent_id=agent_id, task_id=task_id, attempt=attempt_number, reason=reason) at the top "
                "of every retry loop iteration or exception-recovery block. Pass the "
                "1-based attempt count and a short description of why recovery was "
                "triggered."
            ),
            priority=3,
        ),
    ),

    HookCategory.DEGRADATION: (
        GovernanceRisk(
            severity=RiskSeverity.HIGH,
            description="Autonomy degradation events are not instrumented; mode changes are unrecorded.",
            impact=(
                "The governance layer cannot track when or why an agent was stepped down "
                "its autonomy ladder. Compliance auditors cannot verify that degradation "
                "policies were applied correctly or reconstruct the sequence of events "
                "that led to a lower-autonomy operating mode."
            ),
        ),
        GovernanceRecommendation(
            action="Emit an AWCP degradation hook whenever the agent's autonomy mode is stepped down.",
            rationale=(
                "Autonomy degradation is a governance-critical transition. Recording it "
                "ensures that the full history of a task's operating mode is available "
                "for compliance review and that degradation policies can be verified "
                "against actual agent behaviour."
            ),
            instrumentation_hint=(
                "Call get_manager().dispatch(HookType.AUTONOMY_DEGRADED, agent_id=agent_id, task_id=task_id, from_mode=from_mode, to_mode=to_mode) "
                "immediately when the agent receives a degradation signal from the "
                "control plane. Pass the previous and new autonomy modes and a short "
                "reason so the audit trail captures the full transition."
            ),
            priority=2,
        ),
    ),
}
