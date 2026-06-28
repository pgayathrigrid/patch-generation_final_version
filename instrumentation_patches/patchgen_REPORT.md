# Instrumentation Patches — Project Report

## What This Project Does

`instrumentation_patches` is a governance instrumentation engine built to work as part of the AWCP platform. It scans any Python AI agent repository, detects which AWCP governance hooks are missing, generates targeted patches using an LLM, applies them to the source code, and validates the result in an isolated sandbox. The final output is a structured pass/fail result that AWCP uses as a pre-flight gate before allowing any agent to launch.

This is **Step 06** of the AWCP Operating Model: *"Generate Instrumentation Patches — for agents missing hooks, generate and attach a proposed patch for telemetry, feature flags, and policy callbacks before they can leave quarantine."*

---

## Pipeline

```
.py files on disk
       │
 Stage 1 — FilesystemScanner
       │   Walks the folder, reads all .py files
       │   → AgentSource objects (filename + source code)
       │
 Stage 2 — AstCapabilityAnalyzer
       │   Parses AST to detect what the agent does
       │   (calls openai/anthropic? uses tools? does web search?)
       │   → which AWCP hook categories are required for this agent
       │
 Stage 3 — RuleBasedHookDetector  (16 rules)
       │   Scans source for existing AWCP hook calls
       │   → which hook categories are already present
       │
 Stage 4 — GovernanceGapReporter
       │   required hooks − present hooks = gaps
       │   → GovernanceGap objects (severity, risk, LLM hint per gap)
       │
 Stage 5 — LlmPatchGenerator
       │   1 gap  → single LLM call
       │   2+ gaps → one batched LLM call (JSON array), fallback to per-gap
       │   → PatchProposal objects (generated hook call code)
       │
 Stage 6 — SourcePatchApplier
       │   Inserts generated code into the correct location in source
       │   (ImportManager + LocationResolver + SourceEditor)
       │   → PatchedSource in memory + unified diff
       │
 Stage 6.5 — Re-detection
       │   Runs the hook detector again on the patched source
       │   Warns if a hook was inserted but is not detectable
       │
 Stage 7 — PythonSandboxValidator       ← skipped when dry_run=True
       │   Runs patched code in an isolated Python subprocess
       │   4 phases: syntax check → compile → execute → hook presence
       │   → pass / fail / skipped
       │
 Stage 8 — ValidationReportBuilder      ← skipped when dry_run=True
       │   Assembles per-hook results, warnings, errors, diff, recommendations
       │   → BuiltReport (renderable as Markdown or JSON)
       │
 InstrumentationResult
       └── ✓ passed  →  AWCP allows agent to launch
           ✗ failed  →  AWCP blocks agent launch (InstrumentationError)
```

---

## Folder Structure

```
instrumentation_patches/
├── src/
│   ├── awcp/
│   │   └── observability/
│   │       └── setup.py          ← OTel tracer stub (matches real AWCP API)
│   ├── awcp_hooks/
│   │   └── __init__.py           ← 16 no-op stub hook functions for sandbox use
│   └── awcp_instrumentation/
│       ├── api.py                ← public entry point: run_instrumentation()
│       ├── domain/
│       │   └── enums/
│       │       ├── hook_category.py     ← 16 HookCategory values
│       │       ├── hook_type.py
│       │       └── agent_capability.py  ← 10 AgentCapability values
│       └── application/
│           ├── scanner/               Stage 1
│           ├── capability_analyzer/   Stage 2
│           ├── detector/              Stage 3
│           │   └── rules/             16 detection rules (one per hook category)
│           ├── gap_reporter/          Stage 4
│           ├── generator/             Stage 5
│           │   └── providers/         LLM provider implementations
│           ├── applicator/            Stage 6
│           ├── sandbox/               Stage 7
│           └── reporter/              Stage 8
├── tests/                        1034 tests
└── pyproject.toml
```

---

## Important Files

| File | What it does |
|---|---|
| `api.py` | Single public entry point — `run_instrumentation(path, dry_run=False)` wires all 8 stages and returns `InstrumentationResult` |
| `awcp_hooks/__init__.py` | 16 no-op stub functions so patched agent code can execute in the sandbox without a real AWCP installation |
| `awcp/observability/setup.py` | OTel tracer stub — matches the real AWCP `awcp.observability.setup.get_tracer()` API; used for pipeline-level tracing |
| `ast_capability_analyzer.py` | Reads imports, function calls, and decorators to detect what the agent does → drives which hooks are required |
| `capability_hook_mapper.py` | Governance policy table: maps each `AgentCapability` to its required `HookCategory` set |
| `hook_detector.py` | Runs all 16 detection rules against the agent's AST to find present hooks |
| `risk_catalog.py` | Severity, business impact, and LLM instrumentation hint for every hook category |
| `prompt_builder.py` | Builds single-gap and batched LLM prompts; `build_batch()` sends 2+ gaps in one call |
| `response_parser.py` | Parses LLM responses; `parse_batch()` handles the JSON array batch response |
| `mock_provider.py` | Default LLM provider — deterministic, regex-based, no network calls; used in all tests |
| `patch_applier.py` | Inserts LLM-generated hook code at the correct location in the agent source |
| `python_sandbox_validator.py` | Runs patched code in an isolated subprocess; 4-phase validation: syntax → compile → execute → hook presence |
| `markdown_formatter.py` | Renders `BuiltReport` as a Markdown report including the patch diff section |

---

## Public API

```python
from awcp_instrumentation import run_instrumentation, InstrumentationResult

# Full run (all 8 stages, sandbox included)
result = run_instrumentation("/path/to/agent/folder")

# Dry run (Stages 1–6 only — generates patches, skips sandbox)
result = run_instrumentation("/path/to/agent/folder", dry_run=True)

# Inject a real LLM provider instead of the mock
from awcp_instrumentation.application.generator.providers.anthropic_provider import AnthropicProvider
result = run_instrumentation("/path/to/agent/folder", llm_provider=AnthropicProvider())
```

**Key fields on `InstrumentationResult`:**

| Field / Property | Type | What it tells you |
|---|---|---|
| `result.agents` | `List[AgentInstrumentationSummary]` | Per-agent outcome |
| `result.total_missing_hooks` | `int` | Total hooks still missing after patching |
| `result.total_patches_applied` | `int` | Total patches successfully applied |
| `result.quarantine_blockers` | `List[str]` | Missing hooks that specifically block AWCP quarantine exit (`observability`, `feature_flag`, `policy`) |
| `result.patch_bundle` | `str` | Combined unified diff across all agents — for PR / CI review |
| `result.success` | `bool` | `True` when every agent passed sandbox validation |
| `agent.validation_status` | `str` | `"passed"` / `"failed"` / `"skipped"` |
| `agent.report.patch_diff` | `str` | The exact code diff applied to that agent |

---

## How to Run

```bash
# Install
cd instrumentation_patches
pip install -e .

# Run against any agent folder
python3 -c "
from awcp_instrumentation import run_instrumentation
result = run_instrumentation('/path/to/agent/folder')
print(result.repository_summary)
for agent in result.agents:
    print(agent.agent_name, agent.validation_status)
    print('quarantine blockers:', agent.quarantine_blockers)
"

# Dry run — preview patches without sandbox execution
python3 -c "
from awcp_instrumentation import run_instrumentation
result = run_instrumentation('/path/to/agent/folder', dry_run=True)
print(result.patch_bundle)
"

# Run tests
cd instrumentation_patches
python -m pytest tests/ -q
```

---

## How It Works Inside the AWCP Application

When AWCP receives `POST /user/ask` to run an agent task, the gateway goes through `agents_fs.py` to launch the agent. Before the agent process is started, the governance pre-flight runs:

```
User → POST /user/ask
         │
         ▼
   user.py (gateway)
         │
         ▼
   agents_fs.start(agent)
         │
         ├── run_instrumentation(agent["dir"])   ← instrumentation_patches runs here
         │        │
         │        ├── Scans agent source for missing hooks
         │        ├── Generates + applies patches via LLM
         │        └── Validates in sandbox
         │
         ├── result.success == True  →  subprocess.Popen(agent run.sh)  ✅ agent launches
         │
         └── result.success == False →  raise InstrumentationError      ❌ agent blocked
                                              │
                                         user.py catches it
                                              │
                                         HTTP 424 returned to user
                                         "agent blocked by governance instrumentation"
```

**What this means in practice:**

- An agent that is missing required AWCP hooks (`observability`, `feature_flag`, `policy`, etc.) **cannot launch** through AWCP
- `instrumentation_patches` runs automatically every time an agent is started — it is the enforcement mechanism
- If the patches succeed and the sandbox validates them, the agent launches normally
- If the patches fail (hooks can't be inserted, sandbox rejects them), the agent is blocked and the user gets a clear error explaining why

The `quarantine_blockers` field on `InstrumentationResult` maps directly to what AWCP's quarantine check reports: an agent stays quarantined until `observability`, `feature_flag`, and `policy` hooks are present and observed. `instrumentation_patches` is the tool that generates those hooks so agents can exit quarantine.
