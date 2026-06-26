# AWCP Instrumentation Engine — Architecture

## Overview

The AWCP Instrumentation Engine is a standalone Python library that prepares
AI agent repositories for onboarding into the Agent Workforce Control Plane
(AWCP).  It detects missing AWCP lifecycle hooks, generates targeted
instrumentation patches via an LLM, validates them in a local sandbox, and
returns a structured result suitable for direct consumption by the AWCP
control plane.

**Public entry point:**

```python
from awcp_instrumentation import run_instrumentation, InstrumentationResult

result: InstrumentationResult = run_instrumentation("/path/to/agent/repo")
```

The engine is completely standalone — it has no runtime dependency on
Temporal, MCP, Registry, Radar, OPA, Laminar, or the AWCP runtime.  It can
be embedded in any Python environment and requires no external services in its
default configuration.

---

## Execution Pipeline

```
Repository Scanner          — discovers Python agent files
        ↓
Capability Analysis         — infers what each agent actually does (LLM / Tool / Search / Synthesis)
        ↓
Hook Detection              — AST-detects which AWCP lifecycle hooks are already present
        ↓
Gap Reporting               — identifies missing hooks scoped to detected capabilities
        ↓
LLM Patch Generator         — generates targeted code patches for each missing hook
        ↓
Patch Apply Engine          — applies patches to source text with import deduplication
        ↓
CodeAct Sandbox             — validates patched code: syntax → presence → execution
        ↓
Validation Report Builder   — assembles a structured BuiltReport
        ↓
InstrumentationResult       — returned to the caller / AWCP control plane
```

---

## Clean Architecture Layers

```
src/awcp_instrumentation/
├── domain/                   ← Innermost layer — pure value objects, no application deps
│   ├── entities/             ← AgentSource, GovernanceHook, HookDetectionResult, …
│   └── enums/                ← HookCategory (10 AWCP events), AgentCapability, ValidationStatus
│
├── application/              ← Business logic — depends only on domain
│   ├── scanner/              ← Stage 1: FilesystemScanner → RepositoryScanResult
│   ├── capability_analyzer/  ← Stage 2: AstCapabilityAnalyzer → CapabilityAnalysisResult
│   ├── detector/             ← Stage 3: RuleBasedHookDetector → HookDetectionResult
│   ├── gap_reporter/         ← Stage 4: GovernanceGapReporter → GovernanceGapReport
│   ├── generator/            ← Stage 5: LlmPatchGenerator → PatchGenerationResult
│   ├── applicator/           ← Stage 6: SourcePatchApplier → ApplyResult
│   ├── sandbox/              ← Stage 7: PythonSandboxValidator → SandboxValidationResult
│   └── reporter/             ← Stage 8: ValidationReportBuilder → BuiltReport
│
└── api.py                    ← Public façade: run_instrumentation()
```

**Dependency rule:** inner layers never import from outer layers.  Every
pipeline stage is defined as an ABC port (`interface.py`) and injected as a
constructor argument, allowing each stage to be replaced or mocked in tests
without subclassing.

---

## AWCP Lifecycle Hook Categories

The engine detects 10 AWCP lifecycle events:

| Category | Severity | When Emitted |
|----------|----------|--------------|
| `task_started` | HIGH | At task entry, before any business logic |
| `task_completed` | HIGH | On every successful task exit point |
| `task_failed` | CRITICAL | In every except block and failure path |
| `llm_call` | CRITICAL | Before every LLM inference call |
| `synthesize` | HIGH | At the start of answer synthesis |
| `tool_call` | CRITICAL | Before every external tool invocation |
| `web_search` | HIGH | Before every retrieval or web search call |
| `token_usage` | MEDIUM | After every LLM response (reports token counts) |
| `budget_warn` | HIGH | When cumulative usage exceeds the warning threshold |
| `budget_exhausted` | CRITICAL | When the agent hits its hard budget limit |

---

## Capability Analysis

Before checking for missing hooks, the engine infers *what each agent
actually does* via AST analysis.  Only hooks appropriate for the detected
capabilities are required — a pure LLM agent is never told it needs
`TOOL_CALL` or `WEB_SEARCH` instrumentation.

### AgentCapability Enum

| Capability | Detected Via |
|------------|-------------|
| `llm_agent` | Imports: `openai`, `anthropic`, `langchain`, `litellm`, etc. · Calls: `invoke()`, `create()`, `generate_content()` |
| `tool_agent` | Imports: `mcp`, `langchain.tools` · Calls: `execute_tool()`, `call_tool()` · Decorator: `@tool` |
| `search_agent` | Imports: `tavily`, `chromadb`, `pinecone`, `faiss`, `langchain.vectorstores` · Calls: `similarity_search()`, `retrieve()` |
| `synthesis_agent` | Imports: `langchain.chains` · Calls: `synthesize()`, `summarize()`, `generate_answer()` |

### Capability → Required Hooks

| Capability | Additional Required Hooks |
|------------|--------------------------|
| _(always)_ | `task_started`, `task_completed`, `task_failed` |
| `llm_agent` | `llm_call`, `token_usage`, `budget_warn`, `budget_exhausted` |
| `tool_agent` | `tool_call` |
| `search_agent` | `web_search` |
| `synthesis_agent` | `synthesize` |

When **no capability is detected**, all 10 hooks are required as a safe
fallback to avoid silent under-instrumentation.

### Detection Strategy (`AstCapabilityAnalyzer`)

For each capability the analyser runs three independent passes:

1. **Import analysis** — `ast.Import` / `ast.ImportFrom` node names
2. **Call-site analysis** — leaf attribute/name of every `ast.Call` node
3. **Decorator analysis** — decorators on functions and classes

Evidence strings (`"import:openai"`, `"call:invoke"`, `"decorator:tool"`) are
stored in `CapabilityAnalysisResult.evidence` for auditability.

---

## Hook Detection

`RuleBasedHookDetector` fans a pre-parsed `ast.Module` out to all 10
`DetectionRule` instances, one per AWCP lifecycle category.  Each rule checks
call sites and decorators for AWCP hook patterns.

```python
class XyzDetectionRule(BaseDetectionRule):
    @property
    def category(self) -> HookCategory: ...

    @property
    def required_hooks(self) -> List[GovernanceHook]: ...

    def detect(self, tree: ast.Module, agent: AgentSource) -> List[GovernanceHook]:
        match = self._first_matching_call(self._call_sites(tree), _KEYWORDS)
        if match:
            return [self._found(_HOOK, match[1])]
        ...
        return []
```

The gap reporter then filters the missing hooks to only those required by the
agent's detected capabilities, eliminating false gaps.

---

## Patch Generator

`LlmPatchGenerator` iterates over every `GovernanceGap` in the report:

```
GovernanceGap → PromptBuilder → LlmProvider → ResponseParser → PatchProposal
```

`PromptBuilder` encapsulates all prompt engineering.  `LlmProvider` is an
injected port — swap `MockLlmProvider` for `AnthropicProvider` or
`OpenAIProvider` for live generation.  LLM and parse failures are captured
per-proposal so one broken gap never aborts the run.

---

## Sandbox Validation

`PythonSandboxValidator` runs three validation phases on patched source:

| Phase | Check | On Failure |
|-------|-------|-----------|
| 1 — Syntax | `ast.parse()` | All hooks marked FAILED, execution skipped |
| 2 — Presence | `HookPresenceChecker` (text scan for code fragment) | That hook marked FAILED |
| 3 — Execution | `LocalPythonSandbox` (subprocess) | Hooks marked FAILED with runtime details |

`EvidenceCollector` plugins collect runtime observations from stdout/stderr
for supporting evidence.  Observations do not downgrade a PASSED hook to
FAILED — their purpose is auditability, not gating.

---

## InstrumentationResult — AWCP Integration Interface

`InstrumentationResult` is the planned integration surface between this engine
and the AWCP control plane:

```python
@dataclass
class InstrumentationResult:
    repository_path: str        # absolute path scanned
    scanned_files: int
    agents_processed: int
    agents: List[AgentInstrumentationSummary]
    scan_errors: List[str]
    pipeline_errors: List[str]
    generated_at: datetime

    # Aggregate properties
    success: bool               # all agents passed, no pipeline errors
    is_fully_instrumented: bool
    repository_summary: str     # one-line human-readable result
    total_missing_hooks: int
    total_patches_applied: int
    total_warnings: int
    total_errors: int
```

Each `AgentInstrumentationSummary` contains:

```python
agent_name, agent_path          # identity
capabilities: List[str]         # detected AgentCapability values
required_hooks: List[str]       # hooks required given capabilities
present_hooks: List[str]        # hooks found before patching
missing_hooks: List[str]        # hooks absent (scoped to required)
patches_applied, patches_failed # apply-engine counts
validation_status: str          # "passed" / "failed" / "skipped"
warnings: List[str]             # non-fatal sandbox issues
errors: List[str]               # fatal validation errors
report: BuiltReport             # full structured report for rendering
success: bool                   # convenience: validation_status == "passed"
is_fully_instrumented: bool     # convenience: no missing hooks
```

---

## Key Design Decisions

### Port / Adapter Pattern
Every pipeline stage is defined as an ABC port and injected as a constructor
argument.  Unit tests replace any stage with a mock without subclassing.

### Frozen Dataclasses as Value Objects
`GovernanceHook`, `AgentSource`, `PatchChange`, `ScanError`, `CapabilityAnalysisResult`
etc. are frozen dataclasses — immutable once created, safe to share across threads.

### Text-Based Patching
`SourcePatchApplier` uses line-level text insertion rather than AST rewriting.
This preserves comments, formatting, and blank lines while remaining robust
against code styles that confuse AST round-tripping.

### Import Deduplication
`ImportManager` uses `ast.parse()` to enumerate existing imports before
injecting new ones, preventing duplicate `import awcp_hooks` lines across
multiple patch proposals.

### Capability-Scoped Gap Reporting
The gap reporter accepts an optional `required_categories` set.  When
provided (always in the standard pipeline), only missing hooks in that set
are reported, eliminating false positives for hooks the agent genuinely
does not need.

---

## AWCP Integration Points

| Integration Point | How to Connect |
|-------------------|----------------|
| **Real LLM provider** | Inject an `AnthropicProvider` (or any `LlmProvider`) into `run_instrumentation(llm_provider=...)` |
| **Custom risk catalog** | Inject a `RiskCatalog` dict into `GovernanceGapReporter(catalog=...)` |
| **Custom detection rules** | Inject a `List[DetectionRule]` into `RuleBasedHookDetector(rules=...)` |
| **External sandbox** | Implement `SandboxEnvironment` ABC and inject into `PythonSandboxValidator(sandbox=...)` |
| **Structured logging** | Implement `EvidenceCollector` ABC and inject into `PythonSandboxValidator(collectors=[...])` |
| **Report output** | Call `JsonReportFormatter` or `MarkdownReportFormatter` on the `BuiltReport` |

---

## Independence Guarantee

This engine has **zero runtime dependencies** on AWCP platform services.
It prepares repositories *before* they enter AWCP.  Do not add runtime
dependencies on:

- AWCP Registry / HookManager
- MCP
- Temporal
- Radar
- OPA / Laminar

---

## Test Coverage

964 tests covering all layers:

| Suite | What is tested |
|-------|----------------|
| `tests/domain/` | Entity and enum contracts (`AgentCapability`, `HookCategory`, …) |
| `tests/application/capability_analyzer/` | `AstCapabilityAnalyzer` (import/call/decorator detection) and `CapabilityHookMapper` |
| `tests/application/detector/` | All 10 AWCP detection rules + `RuleBasedHookDetector` orchestrator |
| `tests/application/gap_reporter/` | Gap reporter with `required_categories` filter, risk catalog, models |
| `tests/application/generator/` | Patch generation, prompt building, LLM response parsing |
| `tests/application/applicator/` | Patch application, location resolution, import deduplication |
| `tests/application/sandbox/` | Sandbox validation, evidence collection, hook presence checking |
| `tests/application/test_scanner.py` | Filesystem scanner — single file and directory modes |
| `tests/test_api.py` | End-to-end `run_instrumentation()` contract, capability fields, warnings/errors |

---

## Example Agents

`examples/agents/` contains three reference agents for manual testing and
demonstrating the engine:

| File | Description |
|------|-------------|
| `bare_agent.py` | No AWCP hooks — the "before patching" baseline |
| `partial_agent.py` | Task lifecycle hooks only — missing LLM/Tool/Search/Synthesis hooks |
| `fully_instrumented_agent.py` | All 10 AWCP lifecycle hooks — the target state |
