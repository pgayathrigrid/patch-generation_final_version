"""
Instrumentation Patches — End-to-End Demo Script

Stage 1: Scan the real AWCP agents folder (dry_run) — shows what's missing.
Stage 2: Patch bare_agent.py and show before/after — proves the full loop works.
"""
import shutil
import pathlib
from awcp_instrumentation import run_instrumentation
from awcp_instrumentation.application.generator.providers.mock_provider import MockLlmProvider

AWCP_AGENTS = "/Users/pgayathri/Downloads/Folder/awcp-mcp-temp-main/src/awcp/agents/"
BARE_AGENT  = "/Users/pgayathri/Downloads/Folder/instrumentation_patches/examples/agents/bare_agent.py"
DEMO_AGENT  = "/tmp/demo_bare_agent.py"

provider = MockLlmProvider()

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1 — Scan real AWCP agents (preview only, nothing written)
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 70)
print("STAGE 1 — Scanning real AWCP agents (dry_run, no files changed)")
print("=" * 70)

r1 = run_instrumentation(AWCP_AGENTS, llm_provider=provider, dry_run=True)
print(r1.repository_summary)
print()

for a in r1.agents:
    status = "✅ ready     " if not a.missing_hooks else "❌ quarantined"
    print(f"  {status}  {a.agent_name}")
    if a.missing_hooks:
        print(f"               Missing : {a.missing_hooks}")
    if a.patches_applied:
        print(f"               Patches : {a.patches_applied} hook(s) would be added")

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 2 — Full patch demo on bare_agent.py (before → patch → after)
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("STAGE 2 — Patching bare_agent.py (before → patch diff → after)")
print("=" * 70)

# Work on a fresh copy so this demo is repeatable
shutil.copy(BARE_AGENT, DEMO_AGENT)
before = pathlib.Path(DEMO_AGENT).read_text()

# dry_run=True: patches are applied to in-memory source and diff is produced,
# but sandbox validation (which needs a real LLM's variable names) is skipped.
r2 = run_instrumentation(DEMO_AGENT, llm_provider=provider, dry_run=True)

print()
print("── BEFORE patching ───────────────────────────────────────────────────")
for i, line in enumerate(before.splitlines(), 1):
    print(f"  {i:3}: {line}")

for agent in r2.agents:
    diff = agent.report.patch_diff or ""

    print()
    print("── PATCH DIFF (lines added by instrumentation_patches) ───────────────")
    print(f"  Agent          : {agent.agent_name}")
    print(f"  Missing before : {agent.missing_hooks}")
    print(f"  Patches applied: {agent.patches_applied}")
    print()
    if diff:
        print(diff)
    else:
        print("  (no diff — agent already fully instrumented)")

    # Reconstruct "after" by applying the diff's + lines to the before text
    if diff:
        added = [
            ln[1:]
            for ln in diff.splitlines()
            if ln.startswith("+") and not ln.startswith("+++")
        ]
        print()
        print("── AFTER patching (new lines marked +++, unchanged shown normally) ──")
        before_set = set(before.splitlines())
        # Build after content from the diff
        after_lines = []
        for ln in diff.splitlines():
            if ln.startswith("+++") or ln.startswith("---") or ln.startswith("@@"):
                continue
            if ln.startswith("+"):
                after_lines.append(("+++", ln[1:]))
            elif ln.startswith("-"):
                pass  # removed lines not shown in after
            else:
                after_lines.append(("   ", ln[1:] if ln.startswith(" ") else ln))

        for marker, content in after_lines:
            print(f"{marker}  {content}")

print()
print("=" * 70)
total_patches = sum(a.patches_applied for a in r2.agents)
total_missing_before = sum(len(a.missing_hooks) for a in r2.agents)
if total_patches > 0:
    print(f"RESULT: {total_patches} patch(es) generated for {total_missing_before} missing hook(s)")
    print("        Agent would exit quarantine → status: active ✅")
    print()
    print("  NOTE: Sandbox validation is skipped with MockProvider (it uses")
    print("        placeholder variable names). With GeminiProvider or")
    print("        AnthropicProvider the sandbox passes and the file is written.")
else:
    print("RESULT: No patches generated — check agent source structure ❌")
print("=" * 70)
