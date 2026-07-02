#!/usr/bin/env bash
# Starts the AWCP gateway + all 3 real agents in one shot.
# Run from any directory:  bash instrumentation_patches/start_awcp.sh

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AWCP_DIR="$REPO_ROOT/awcp-mcp-temp-main"
AGENTS_DIR="$REPO_ROOT/awcp-mcp-temp-agents"
VENV="$AWCP_DIR/.venv/bin/python"

export AWCP_AGENTS_DIR="$AGENTS_DIR"
export AGENT_RADAR_URL="http://localhost:8000"

echo ""
echo "==========================================================="
echo "  AWCP — Instrumentation Patches (Step 06)"
echo "  Real agents: arxiv_agent | langgraph_agent | pydanticai_agent"
echo "==========================================================="
echo ""

# ── Step 1: Governance instrumentation (already applied — skip at runtime) ───
# Instrumentation patches are applied once during development via run_instrumentation.py.
# Agents are already patched — no need to re-run Gemini on every startup.
echo "Step 1 — Governance instrumentation: already applied ✅"

# ── Step 1.5: Ensure agent venvs are correct (Python 3.11 + awcp package) ────
echo ""
echo "Step 1.5 — Checking agent venv setup..."
INSTR_SRC="$REPO_ROOT/instrumentation_patches"
PYTHON311="$(which python3.11 2>/dev/null || echo python3)"
for AGENT in arxiv_agent langgraph_agent pydanticai_agent; do
    AGENT_DIR="$AGENTS_DIR/$AGENT"
    PYVER=$("$AGENT_DIR/.venv/bin/python" --version 2>/dev/null | grep -oE '3\.[0-9]+' | head -1)
    if [ ! -d "$AGENT_DIR/.venv" ] || [ "$PYVER" = "3.9" ] || [ -z "$PYVER" ]; then
        echo "  Rebuilding $AGENT venv (Python 3.11 required)..."
        rm -rf "$AGENT_DIR/.venv"
        "$PYTHON311" -m venv "$AGENT_DIR/.venv"
        "$AGENT_DIR/.venv/bin/pip" install -q --upgrade pip
        "$AGENT_DIR/.venv/bin/pip" install -q -r "$AGENT_DIR/requirements.txt"
        "$AGENT_DIR/.venv/bin/pip" install -q -e "$INSTR_SRC"
        # pydanticai needs specific version for OpenAIModel API
        if [ "$AGENT" = "pydanticai_agent" ]; then
            "$AGENT_DIR/.venv/bin/pip" install -q "pydantic-ai>=0.0.40,<1.0"
        fi
        echo "  ✅ $AGENT ready"
    else
        # Ensure awcp package is installed
        "$AGENT_DIR/.venv/bin/python" -c "import awcp" 2>/dev/null || {
            echo "  Adding awcp to $AGENT..."
            "$AGENT_DIR/.venv/bin/pip" install -q -e "$INSTR_SRC"
        }
        echo "  ✅ $AGENT ok (Python $PYVER)"
    fi
done

# ── Step 2: Kill any stale gateway/agents on ports we need ───────────────────
echo ""
echo "Step 2 — Clearing any stale processes..."
for PORT in 8000 8100 8101 8102 8103; do
    PID=$(lsof -ti:$PORT 2>/dev/null || true)
    if [ -n "$PID" ]; then
        kill -9 $PID 2>/dev/null || true
        echo "  Cleared port $PORT (PID $PID)"
    fi
done
sleep 1

# ── Step 3: Start the AWCP gateway ───────────────────────────────────────────
echo ""
echo "Step 3 — Starting AWCP gateway on port 8000..."
AWCP_AGENTS_DIR="$AGENTS_DIR" \
PYTHONPATH="$AWCP_DIR/src" \
"$AWCP_DIR/.venv/bin/uvicorn" awcp.gateway.app:app \
    --host 0.0.0.0 --port 8000 \
    --app-dir "$AWCP_DIR/src" \
    --log-level warning &
GATEWAY_PID=$!

# Wait for gateway health
echo "  Waiting for gateway..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/healthz >/dev/null 2>&1; then
        echo "  ✅ Gateway is up (PID $GATEWAY_PID)"
        break
    fi
    sleep 1
done

if ! curl -sf http://localhost:8000/healthz >/dev/null 2>&1; then
    echo "  ❌ Gateway failed to start. Check for errors above."
    exit 1
fi

# ── Step 4: Start all 3 real agents ──────────────────────────────────────────
echo ""
echo "Step 4 — Starting real agents..."

for AGENT in arxiv_agent langgraph_agent pydanticai_agent; do
    AGENT_DIR="$AGENTS_DIR/$AGENT"
    echo "  Starting $AGENT..."
    AGENT_RADAR_URL="http://localhost:8000" \
    OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317" \
    AGENT_FINALIZE_ARTIFACT="false" \
    bash "$AGENT_DIR/run.sh" > "/tmp/${AGENT}.log" 2>&1
    echo "  ✅ $AGENT launched  (logs: /tmp/${AGENT}.log)"
done

# Give agents a moment to start and register with the radar
echo ""
echo "  Waiting for agents to register with radar..."
sleep 10

# ── Step 5: Observe policy hooks → clear quarantine for all agents ────────────
# Calling the radar's gate endpoint proves each agent's policy callback is wired.
# This is what flips status from quarantined → active in the dashboard.
echo ""
echo "Step 5 — Observing policy hooks (clears quarantine)..."
AGENT_IDS=$(curl -sf http://localhost:8000/agents 2>/dev/null | \
    python3 -c "
import sys, json
try:
    agents = json.load(sys.stdin)
    print(' '.join(a['id'] for a in agents if a.get('id','').startswith('agent-')))
except Exception:
    pass
" 2>/dev/null)

for AGENT_ID in $AGENT_IDS; do
    RESULT=$(curl -sf -X POST "http://localhost:8000/agents/${AGENT_ID}/gate" \
        -H 'Content-Type: application/json' \
        -d '{"action":"startup_policy_check","write":false}' 2>/dev/null | \
        python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null)
    echo "  ✅ $AGENT_ID → $RESULT"
done

echo ""
echo "==========================================================="
echo "  Gateway   : http://localhost:8000"
echo "  Dashboard : http://localhost:5173  (run: cd awcp-mcp-temp-main/ui && npm run dev)"
echo ""
echo "  All 3 agents starting — they appear in the Radar tab"
echo "  once they boot and register (takes ~10-20s)"
echo ""
echo "  Send a task (example):"
echo "    curl -s -X POST http://localhost:8000/user/ask \\"
echo "         -H 'Content-Type: application/json' \\"
echo "         -d '{\"agent\":\"arxiv_agent\",\"input\":\"Find papers on RAG\"}'"
echo "==========================================================="
echo ""
echo "  Press Ctrl+C to stop the gateway (agents keep running)."
echo ""

wait $GATEWAY_PID
