#!/usr/bin/env python3
"""
start_all.py — Launch all MANTHAN.AI services in dependency order.

Startup order:
  Tier 1 — Agents   : Heimdall :8001, ARIA :8002, SAGE :8003,
                       VALKYRIE :8004, SPYDER :8005, RAVEN :8006
  Tier 2 — Backend  : FastAPI  :8000
  Tier 3 — Frontend : Vite     :5173

Each service logs to logs/<name>.log.
Press Ctrl+C to stop everything.
"""

import os
import sys
import time
import signal
import subprocess
from pathlib import Path

ROOT  = Path(__file__).parent.resolve()
LOGS  = ROOT / "logs"
LOGS.mkdir(exist_ok=True)

PYTHON = sys.executable                                 # same interpreter as launcher
NPM    = "npm.cmd" if sys.platform == "win32" else "npm"

# ── Service registry ───────────────────────────────────────────────────────────
# Fields: name, cwd (relative to ROOT), cmd, health_url (None = skip check), log

TIER1_AGENTS = [
    {
        "name":   "Heimdall",
        "cwd":    "Agents/Guardrail",
        "cmd":    [PYTHON, "watchman.py"],
        "health": "http://localhost:8001/health",
        "log":    "heimdall.log",
    },
    {
        "name":   "ARIA",
        "cwd":    "Agents/IntentClassifier",
        "cmd":    [PYTHON, "aria.py"],
        "health": "http://localhost:8002/health",
        "log":    "aria.log",
    },
    {
        "name":   "SAGE",
        "cwd":    "Agents/SQLGenerator",
        "cmd":    [PYTHON, "sage.py"],
        "health": "http://localhost:8003/health",
        "log":    "sage.log",
    },
    {
        "name":   "VALKYRIE",
        "cwd":    "Agents/SQLValidator",
        "cmd":    [PYTHON, "valkyrie.py"],
        "health": "http://localhost:8004/health",
        "log":    "valkyrie.log",
    },
    {
        "name":   "SPYDER",
        "cwd":    "Agents/Synthesizer/backend",
        "cmd":    [PYTHON, "-m", "uvicorn", "main:app",
                   "--host", "0.0.0.0", "--port", "8005", "--reload"],
        "health": "http://localhost:8005/api/health",
        "log":    "spyder.log",
    },
    {
        "name":   "RAVEN",
        "cwd":    "Agents/VectorDBagent",
        "cmd":    [PYTHON, "-m", "uvicorn", "raven:app",
                   "--host", "0.0.0.0", "--port", "8006", "--reload"],
        "health": "http://localhost:8006/health",
        "log":    "raven.log",
    },
]

TIER2_BACKEND = {
    "name":   "Backend",
    "cwd":    "backend",
    "cmd":    [PYTHON, "-m", "uvicorn", "app.main:app",
               "--reload", "--port", "8000"],
    "health": "http://localhost:8000/docs",   # /docs returns 200 when app is ready
    "log":    "backend.log",
}

TIER3_FRONTEND = {
    "name":   "Frontend",
    "cwd":    "frontend",
    "cmd":    [NPM, "run", "dev"],
    "health": None,                           # no health endpoint — wait fixed time
    "log":    "frontend.log",
}

# ── Running process registry (proc, log_file_handle, name) ────────────────────
_procs: list[tuple] = []


# ── Helpers ───────────────────────────────────────────────────────────────────

def _free_ports(ports: list[int]) -> None:
    """Kill any processes that currently hold the given ports."""
    for port in ports:
        try:
            if sys.platform == "win32":
                r = subprocess.run(
                    ["netstat", "-ano"],
                    capture_output=True, text=True,
                )
                for line in r.stdout.splitlines():
                    cols = line.split()
                    if len(cols) >= 5 and f":{port}" in cols[1] and cols[3] == "LISTENING":
                        pid = cols[4]
                        subprocess.run(
                            ["taskkill", "/F", "/PID", pid],
                            capture_output=True,
                        )
                        print(f"  Cleared port {port} (killed PID {pid})")
                        break
            else:
                r = subprocess.run(
                    ["lsof", "-ti", f"tcp:{port}"],
                    capture_output=True, text=True,
                )
                for pid in r.stdout.strip().splitlines():
                    subprocess.run(["kill", "-9", pid], capture_output=True)
                    print(f"  Cleared port {port} (killed PID {pid})")
        except Exception as e:
            print(f"  Port {port} cleanup skipped: {e}")


def _colour(code: str, text: str) -> str:
    """ANSI colour if terminal supports it."""
    if sys.stdout.isatty():
        return f"\033[{code}m{text}\033[0m"
    return text

OK   = _colour("32", "✅")
WAIT = _colour("33", "⏳")
FAIL = _colour("31", "❌")
RUN  = _colour("36", "🚀")
STOP = _colour("35", "⛔")


def _poll_health(url: str, name: str, timeout: int = 1200, interval: int = 2) -> bool:
    """
    Poll url until the server responds (any HTTP status < 500 counts as 'up').
    Returns True on success, False on timeout.
    """
    import urllib.request
    import urllib.error

    deadline = time.time() + timeout
    print(f"  {WAIT} {name}: waiting for {url}", end="", flush=True)

    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=3).read()
            print(f"  {OK}")
            return True
        except urllib.error.HTTPError as e:
            if e.code < 500:            # 4xx = server up, just rejected the request
                print(f"  {OK} ({e.code})")
                return True
        except Exception:
            pass
        print(".", end="", flush=True)
        time.sleep(interval)

    print(f"  {FAIL} timed out after {timeout}s")
    return False


def _launch(svc: dict) -> subprocess.Popen:
    """Spawn a service, redirect stdout+stderr to its log file."""
    cwd      = ROOT / svc["cwd"]
    log_path = LOGS / svc["log"]
    log_fh   = open(log_path, "a", encoding="utf-8", buffering=1)

    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    log_fh.write(f"\n{'='*60}\n[{ts}] Starting {svc['name']}\n{'='*60}\n")
    log_fh.flush()

    kwargs: dict = dict(cwd=str(cwd), stdout=log_fh, stderr=log_fh)

    # On Windows, prevent Ctrl+C from reaching child processes directly —
    # we send the signal ourselves in shutdown().
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(svc["cmd"], **kwargs)
    _procs.append((proc, log_fh, svc["name"]))

    print(f"  {RUN} {svc['name']} — pid {proc.pid} → logs/{svc['log']}")
    return proc


def _shutdown():
    """Terminate all processes in reverse launch order."""
    print(f"\n{STOP} Shutting down all services…")
    for proc, log_fh, name in reversed(_procs):
        try:
            if proc.poll() is None:
                print(f"  Stopping {name} (pid={proc.pid})")
                if sys.platform == "win32":
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    print(f"  Force-killing {name}")
                    proc.kill()
        except Exception as ex:
            print(f"  Error stopping {name}: {ex}")
        try:
            log_fh.close()
        except Exception:
            pass
    print(f"{OK} All services stopped.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    banner = "  MANTHAN.AI — Full Stack Launcher"
    print("=" * 60)
    print(banner)
    print(f"  Logs directory : {LOGS}")
    print(f"  Python         : {PYTHON}")
    print("=" * 60)

    # ── Pre-flight: clear any stale processes on agent ports ─────────────────
    agent_ports = [8001, 8002, 8003, 8004, 8005, 8006, 8000,5173]
    print(f"\n[Pre-flight] Clearing stale processes on ports {agent_ports}…")
    _free_ports(agent_ports)

    # ── Tier 1: Agents ────────────────────────────────────────────────────────
    print(f"\n[Tier 1] Launching {len(TIER1_AGENTS)} agent(s)…")
    for svc in TIER1_AGENTS:
        _launch(svc)

    print(f"\n[Tier 1] Health checks (agents may take ~30s to warm up models)…")
    for svc in TIER1_AGENTS:
        ok = _poll_health(svc["health"], svc["name"])
        if not ok:
            print(f"  ⚠️  {svc['name']} unhealthy — proceeding anyway (check logs/{svc['log']})")

    # ── Tier 2: Backend ───────────────────────────────────────────────────────
    print(f"\n[Tier 2] Launching backend…")
    _launch(TIER2_BACKEND)
    _poll_health(TIER2_BACKEND["health"], TIER2_BACKEND["name"])

    # ── Tier 3: Frontend ──────────────────────────────────────────────────────
    print(f"\n[Tier 3] Launching frontend…")
    _launch(TIER3_FRONTEND)
    print(f"  {WAIT} Waiting 8s for Vite to compile…")
    time.sleep(8)
    print(f"  {OK} Frontend → http://localhost:5173")

    print("\n" + "=" * 60)
    print(f"  {OK} All services running.")
    print("  Press Ctrl+C to stop everything.")
    print("=" * 60 + "\n")

    # ── Monitor: warn if any process dies unexpectedly ────────────────────────
    try:
        while True:
            time.sleep(5)
            for proc, _fh, name in _procs:
                if proc.poll() is not None:
                    print(f"  ⚠️  {name} exited (code {proc.returncode})"
                          f" — check logs/{name.lower()}.log")
    except KeyboardInterrupt:
        pass
    finally:
        _shutdown()


if __name__ == "__main__":
    main()
