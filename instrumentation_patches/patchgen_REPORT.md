# Instrumentation Patches — Project Report

## What This Does

`instrumentation_patches` is **Step 06 of the AWCP Operating Model**. It scans Python AI agent source code, finds missing AWCP governance hooks, generates patch code using an LLM, applies the patches, and validates the result. AWCP uses this as a gate — agents with missing hooks cannot launch until they pass.

---

## How the Pipeline Works

```
Agent .py files
       │
  1 — FilesystemScanner       reads all .py files in the target path
  2 — AstCapabilityAnalyzer   detects what the agent does (LLM calls? tools? web search?)
  3 — RuleBasedHookDetector   finds which AWCP hooks are already present (16 rules)
  4 — GovernanceGapReporter   required hooks − present hooks = gaps to fill
  5 — LlmPatchGenerator       sends gaps to an LLM → gets back hook dispatch code
  6 — SourcePatchApplier      inserts the generated code into the right place in source
  6.5 — Re-detection          confirms the inserted hooks are actually detectable
  7 — PythonSandboxValidator  runs patched code in a subprocess (skipped in dry_run)
  8 — ValidationReportBuilder builds the final report with diff, warnings, pass/fail
       │
  InstrumentationResult
       ├── passed  → agent is allowed to launch
       └── failed  → agent is blocked (HTTP 424 returned to user)
```

---

## Folder Structure

```
instrumentation_patches/
├── src/
│   ├── awcp_hooks/                    ← 16 no-op stubs so patched code runs in sandbox
│   ├── awcp/observability/setup.py    ← OTel tracer stub (matches real AWCP API)
│   └── awcp_instrumentation/
│       ├── api.py                     ← single entry point: run_instrumentation()
│       ├── domain/enums/              ← HookCategory, HookType, AgentCapability
│       └── application/
│           ├── scanner/               Stage 1
│           ├── capability_analyzer/   Stage 2
│           ├── detector/rules/        Stage 3 — 16 detection rules
│           ├── gap_reporter/          Stage 4
│           ├── generator/
│           │   └── providers/
│           │       ├── gemini_provider.py     ← real LLM (Google Gemini)
│           │       ├── anthropic_provider.py  ← real LLM (Claude)
│           │       └── mock_provider.py       ← deterministic, used in tests
│           ├── applicator/            Stage 6
│           ├── sandbox/               Stage 7
│           └── reporter/              Stage 8
├── tests/                             1068 tests
└── pyproject.toml
```

---

## Key Files — What Each One Does

| File | Purpose |
|---|---|
| `api.py` | The only file you need to import. Wires all 8 stages together and auto-detects the LLM provider from env vars. |
| `gemini_provider.py` | Calls Gemini API using `GEMINI_API_KEY`. Default model: `gemini-2.5-flash`. |
| `anthropic_provider.py` | Calls Claude API using `ANTHROPIC_API_KEY`. |
| `mock_provider.py` | Offline fallback — no API key needed. Used in all tests. |
| `prompt_builder.py` | Builds the LLM prompt for each gap. Tells the LLM exactly what hook to add and where. |
| `location_resolver.py` | Figures out the exact line number to insert code, so hooks always land after the variables they need. |
| `patch_applier.py` | Does the actual text insertion into source code. |
| `python_sandbox_validator.py` | Runs the patched code in a subprocess to check it works before reporting success. |
| `risk_catalog.py` | Defines severity and guidance for each of the 16 hook categories. |

---

## LLM Providers

The provider is picked automatically from your environment — no configuration required.

**Priority:**
1. `GEMINI_API_KEY` set → uses **GeminiProvider** (get key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey))
2. `ANTHROPIC_API_KEY` set → uses **AnthropicProvider**
3. Neither set → uses **MockLlmProvider** (works offline, good for tests)

**What every generated patch guarantees:**
- Correct AWCP pattern: `get_manager().dispatch(HookType.X, agent_id=..., task_id=..., **kwargs)`
- Syntactically valid Python
- Inserted after any local variables it references (so no `NameError` at runtime)
- Only adds the dispatch call — never rewrites or restructures existing code

---

## Public API

```python
from awcp_instrumentation import run_instrumentation

# Preview patches without touching any files (recommended first step)
result = run_instrumentation("/path/to/agent.py", dry_run=True)

# Full run — patches + sandbox validation
result = run_instrumentation("/path/to/agent.py")

# Explicitly choose a provider
from awcp_instrumentation.application.generator.providers.gemini_provider import GeminiProvider
result = run_instrumentation("/path/to/agent.py", llm_provider=GeminiProvider())
```

**What you get back:**

| Field | What it tells you |
|---|---|
| `result.agents` | List of per-agent results |
| `result.patch_bundle` | Combined diff across all agents — ready for PR review |
| `result.quarantine_blockers` | Hook categories still missing that block AWCP quarantine exit |
| `result.total_patches_applied` | How many patches were successfully applied |
| `agent.missing_hooks` | Which hooks were missing before patching |
| `agent.patches_applied` | How many were patched |
| `agent.report.patch_diff` | The exact diff for that agent |
| `agent.validation_status` | `"passed"` / `"failed"` / `"skipped"` |

---

## For Team

### 1. Setup

```bash
# Requires Python 3.11+
pip install -e instrumentation_patches/

# Add your API key to ~/.zshrc, then run: source ~/.zshrc
export GEMINI_API_KEY="your-key-from-aistudio.google.com/apikey"
# or: export ANTHROPIC_API_KEY="your-key"
```

### 2. Run it

```python
from awcp_instrumentation import run_instrumentation

# Point it at your agent file — it handles everything automatically
result = run_instrumentation("/path/to/your/agent.py", dry_run=True)

for agent in result.agents:
    print(f"Missing hooks:    {agent.missing_hooks}")
    print(f"Patches applied:  {agent.patches_applied}")
    print(agent.report.patch_diff)  # exact lines that would be added
```

### 3. Scan a whole folder

```python
result = run_instrumentation("/path/to/agents/folder/", dry_run=True)

for agent in result.agents:
    print(f"{agent.agent_name}: {agent.patches_applied} patches applied")
    if agent.quarantine_blockers:
        print(f"  Still blocked: {agent.quarantine_blockers}")
```

### 4. Save and apply the diff

```python
result = run_instrumentation("/path/to/agent.py", dry_run=True)

with open("instrumentation.patch", "w") as f:
    f.write(result.patch_bundle)
```

```bash
# Apply from terminal after reviewing the diff
patch -p0 < instrumentation.patch
```

> **Set your API key, point it at your agent — done.**

---

## How It Fits Into AWCP

```
User → POST /user/ask
            │
      agents_fs.start(agent)
            │
            ├── run_instrumentation(agent["dir"])
            │       ├── scans for missing hooks
            │       ├── generates + applies patches via LLM
            │       └── validates in sandbox
            │
            ├── success → agent launches normally         ✅
            └── failure → HTTP 424, agent blocked         ❌
                          "blocked by governance instrumentation"
```

An agent stays in AWCP quarantine until `observability`, `feature_flag`, and `policy` hooks are present. `instrumentation_patches` is the tool that generates those hooks so the agent can exit quarantine and launch.
