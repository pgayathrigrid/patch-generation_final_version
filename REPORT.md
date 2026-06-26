# Instrumentation Patches — Project Report

## What This Project Does

`instrumentation_patches` scans any Python AI agent repository, detects missing AWCP governance hooks, generates patches using an LLM, applies them, validates them in a sandbox, and produces a structured pass/fail result used by AWCP as a pre-flight gate before launching any agent.

---

## Pipeline

```
.py files on disk
       │
 FilesystemScanner ──────────────────── AgentSource objects
       │
 AstCapabilityAnalyzer ─────────────── what does this agent do?
       │                                → which hooks does it need?
 RuleBasedHookDetector (16 rules) ──── which hooks are already there?
       │
 GovernanceGapReporter ─────────────── which hooks are missing + why?
       │                                (severity, risk, LLM hint)
 LlmPatchGenerator ─────────────────── LLM generates hook call code per gap
   (PromptBuilder → LlmProvider → ResponseParser)
       │
 SourcePatchApplier ─────────────────── inserts code into .py source text
   (ImportManager + LocationResolver + SourceEditor)
       │
 PythonSandboxValidator ─────────────── syntax + presence + compile + execute
   (LocalPythonSandbox + HookPresenceChecker)
       │
 ValidationReportBuilder ────────────── structured report
       │
 InstrumentationResult ──────────────── ✓ or ✗ → AWCP pre-flight gate
```

---

## Folder Structure

```
instrumentation_patches/
├── src/
│   ├── awcp_hooks/          ← stub module for sandbox execution
│   └── awcp_instrumentation/
│       └── application/
│           ├── scanner/
│           ├── capability_analyzer/
│           ├── detector/
│           │   └── rules/
│           ├── gap_reporter/
│           ├── generator/
│           │   └── providers/
│           ├── applicator/
│           ├── sandbox/
│           └── reporter/
├── tests/
└── pyproject.toml
```

---

## Important Files

| File | Why It Matters |
|---|---|
| `api.py` | `run_instrumentation(path)` — single entry point, wires all 8 stages |
| `awcp_hooks/__init__.py` | Stub module so patched agent code can execute in the sandbox without real AWCP |
| `ast_capability_analyzer.py` | Detects what the agent does → drives which hooks are required |
| `capability_hook_mapper.py` | Governance policy table: capability → required hook categories |
| `hook_detector.py` | Runs all 16 detection rules against the agent's AST |
| `risk_catalog.py` | Severity, impact, and LLM hint for every hook category |
| `mock_provider.py` | Default LLM provider — deterministic, no network, regex-based category extraction |
| `patch_applier.py` | Inserts LLM-generated code into agent source at the correct location |
| `python_sandbox_validator.py` | 4-phase validation: syntax → presence → compile → execute |

---

## Changes Made

### `awcp-mcp-temp-awcp-smjunaidgrid/` (team's AWCP folder)

- **`requirements.txt`** — added `-e ../instrumentation_patches` so AWCP can import the package
- **`agents_fs.py`** — added `InstrumentationError` class and governance pre-flight call inside `start()` before `subprocess.Popen()`; blocks agent launch if instrumentation fails
- **`user.py`** — wrapped `fs.start()` to catch `InstrumentationError` and return HTTP 424 with structured error detail

### `instrumentation_patches/` (gayathri's folder)

**New files (7)**
- `src/awcp_hooks/__init__.py` — 16 no-op stub functions, one per hook category
- `src/.../detector/rules/observability_rule.py`
- `src/.../detector/rules/policy_rule.py`
- `src/.../detector/rules/approval_rule.py`
- `src/.../detector/rules/feature_flag_rule.py`
- `src/.../detector/rules/recovery_rule.py`
- `src/.../detector/rules/degradation_rule.py`

**Modified files**
- `mock_provider.py` — fixed category detection (was generating `task_started` for every hook); switched to regex on `**Category:**` line; added correct hook signature per category
- `hook_category.py` — added 6 new enum values (10 → 16): OBSERVABILITY, POLICY, APPROVAL, FEATURE_FLAG, RECOVERY, DEGRADATION
- `agent_capability.py` — added 6 new capabilities (4 → 10)
- `hook_detector.py` — registered all 6 new rules (10 → 16 active rules)
- `risk_catalog.py` — added risk entries for all 6 new categories
- `capability_hook_mapper.py` — added 6 new capability → hook mappings
- `ast_capability_analyzer.py` — added import/call/decorator signals for all 6 new capabilities
- `detector/rules/__init__.py` — exported all 6 new rule classes

---

## How to Run

```bash
# Install
cd instrumentation_patches
pip install -e .

# Run on any agent directory
python3 -c "
from awcp_instrumentation import run_instrumentation
result = run_instrumentation('/path/to/agent/folder')
print(result.repository_summary)
"

# Run tests
PYTHONPATH=src python3 -m pytest

# Start AWCP with instrumentation active
cd awcp-mcp-temp-awcp-smjunaidgrid
pip install -r requirements.txt
PYTHONPATH=src uvicorn awcp.gateway.app:app --host 0.0.0.0 --port 8000
```
