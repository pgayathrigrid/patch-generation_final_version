#!/usr/bin/env python3
"""AWCP Agent Task Runner — interactive and command-line modes.

Usage:
  python3 ask.py                              # interactive menu (recommended)
  python3 ask.py all "What is RAG?"           # send to all 3 agents at once
  python3 ask.py arxiv_agent "Find papers"    # send to one agent
"""
import sys, json, time, threading
import urllib.request
import urllib.error

AGENTS = {
    "arxiv_agent": {
        "url":   "http://localhost:8103",
        "label": "arXiv Research Worker",
        "desc":  "finds academic papers and summarises them with citations",
    },
    "langgraph_agent": {
        "url":   "http://localhost:8100",
        "label": "LangGraph Orchestrator",
        "desc":  "general research, web search, and math — multi-step reasoning",
    },
    "pydanticai_agent": {
        "url":   "http://localhost:8102",
        "label": "PydanticAI Extractor",
        "desc":  "structured data extraction and analysis",
    },
}
AGENT_KEYS = list(AGENTS.keys())
POLL_INTERVAL = 2   # seconds between status checks
POLL_TIMEOUT  = 120 # seconds before giving up on a result


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _post(url: str, body: dict, timeout: int = 10) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _get(url: str, timeout: int = 10) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


# ── Task queue + poll ─────────────────────────────────────────────────────────

def _queue_task(agent_key: str, goal: str, results: dict):
    """Queue one task and store the task_id (or error) in results."""
    cfg = AGENTS[agent_key]
    try:
        resp = _post(f"{cfg['url']}/tasks", {"goal": goal})
        results[agent_key] = {"task_id": resp["id"], "status": resp["status"], "error": None}
    except Exception as e:
        results[agent_key] = {"task_id": None, "status": "error", "error": str(e)}


def _poll_task(agent_key: str, task_id: str, results: dict):
    """Poll until done/failed/timeout, then store result in results."""
    cfg = AGENTS[agent_key]
    url = f"{cfg['url']}/tasks/{task_id}"
    deadline = time.monotonic() + POLL_TIMEOUT
    while time.monotonic() < deadline:
        try:
            t = _get(url)
            status = t.get("status", "")
            if status in ("done", "failed", "blocked"):
                results[agent_key] = t
                return
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)
    results[agent_key] = {"status": "timeout", "result": "", "error": "no result after 120s"}


def send_and_wait(agent_keys: list[str], goal: str) -> None:
    """Queue tasks in parallel, then poll for results and print them."""

    # Step 1: queue all tasks simultaneously
    queue_results: dict = {}
    threads = [
        threading.Thread(target=_queue_task, args=(k, goal, queue_results))
        for k in agent_keys
    ]
    for t in threads: t.start()
    for t in threads: t.join()

    # Show queue status
    print()
    queued = []
    for k in agent_keys:
        r = queue_results.get(k, {})
        if r.get("task_id"):
            print(f"  ✅  {AGENTS[k]['label']:<28}  queued  (id={r['task_id']})")
            queued.append((k, r["task_id"]))
        else:
            print(f"  ❌  {AGENTS[k]['label']:<28}  {r.get('error','failed to queue')}")

    if not queued:
        print("\n  No tasks queued. Are the agents running? (bash instrumentation_patches/start_awcp.sh)\n")
        return

    # Step 2: poll all queued tasks for results
    print()
    print("  Waiting for results (Ctrl+C to skip and check dashboard)...")
    print()

    poll_results: dict = {}
    poll_threads = [
        threading.Thread(target=_poll_task, args=(k, tid, poll_results))
        for k, tid in queued
    ]
    for t in poll_threads: t.start()

    # Animate while waiting
    spinner = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
    done_set: set = set()
    try:
        i = 0
        while len(done_set) < len(queued):
            for k, _ in queued:
                if k not in done_set and k in poll_results:
                    done_set.add(k)
                    r = poll_results[k]
                    status = r.get("status", "?")
                    result_text = (r.get("result") or r.get("error") or "").strip()
                    snippet = result_text[:180] + ("…" if len(result_text) > 180 else "")
                    icon = "✅" if status == "done" else "⚠️" if status == "blocked" else "❌"
                    print(" " * 90, end="\r")  # clear spinner line
                    print(f"  {icon}  {AGENTS[k]['label']} — {status}")
                    if snippet:
                        for line in snippet.splitlines()[:4]:
                            print(f"       {line}")
                    print()
            remaining = [(k,tid) for k,tid in queued if k not in done_set]
            if remaining:
                names = ", ".join(AGENTS[k]["label"] for k,_ in remaining)
                print(f"  {spinner[i % len(spinner)]}  Still running: {names}", end="\r", flush=True)
                i += 1
                time.sleep(0.3)
    except KeyboardInterrupt:
        print("\n\n  Skipped — check results in the dashboard ↓")

    for t in poll_threads: t.join(timeout=0)

    print(f"  Dashboard → http://localhost:5173")
    print()


# ── Interactive menu ──────────────────────────────────────────────────────────

def interactive_loop():
    print()
    print("  ╔══════════════════════════════════════════╗")
    print("  ║        AWCP Agent Task Runner            ║")
    print("  ╚══════════════════════════════════════════╝")
    print()

    while True:
        print("  Choose an agent:")
        for i, key in enumerate(AGENT_KEYS, 1):
            cfg = AGENTS[key]
            print(f"    {i}  {cfg['label']:<28} — {cfg['desc']}")
        print(f"    4  All agents                          — send same task to all 3")
        print(f"    q  Quit")
        print()

        choice = input("  Your choice: ").strip().lower()
        print()

        if choice in ("q", "quit", "exit"):
            print("  Bye!\n")
            break

        if choice == "4" or choice == "all":
            agent_keys = AGENT_KEYS
        elif choice == "1":
            agent_keys = [AGENT_KEYS[0]]
        elif choice == "2":
            agent_keys = [AGENT_KEYS[1]]
        elif choice == "3":
            agent_keys = [AGENT_KEYS[2]]
        elif choice in AGENT_KEYS:
            agent_keys = [choice]
        else:
            print(f"  ⚠️  Invalid choice '{choice}' — enter 1, 2, 3, 4, or q\n")
            continue

        goal = input("  Task: ").strip()
        if not goal:
            print("  ⚠️  Task cannot be empty.\n")
            continue

        send_and_wait(agent_keys, goal)

        again = input("  Send another task? [Enter=yes / q=quit]: ").strip().lower()
        print()
        if again in ("q", "quit", "n", "no"):
            print("  Bye!\n")
            break


# ── Command-line mode ─────────────────────────────────────────────────────────

def main():
    if len(sys.argv) >= 3:
        agent_arg = sys.argv[1]
        goal = " ".join(sys.argv[2:])
        if agent_arg == "all":
            agent_keys = AGENT_KEYS
        elif agent_arg in AGENTS:
            agent_keys = [agent_arg]
        else:
            print(f"Unknown agent '{agent_arg}'. Options: all, {', '.join(AGENT_KEYS)}")
            sys.exit(1)
        send_and_wait(agent_keys, goal)
    else:
        interactive_loop()


if __name__ == "__main__":
    main()
