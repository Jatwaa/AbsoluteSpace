#!/usr/bin/env python3
"""
AbsoluteSpace — one-click launcher.

Detects the operating system, makes sure the backend dependencies and the
built frontend are in place, then starts the game server (which serves both the
API and the web UI on one port) and opens it in your browser.

Run it directly:   python start.py
Or use the platform shim:  Start.bat (Windows) · Start.command (macOS) · start.sh (Linux)
"""

from __future__ import annotations
import os
import sys
import platform
import shutil
import subprocess
import threading
import time
import urllib.request

# Never crash on console encoding (Windows cp1252 etc.).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}"
ROOT = os.path.dirname(os.path.abspath(__file__))
FRONTEND = os.path.join(ROOT, "frontend")
DIST_INDEX = os.path.join(FRONTEND, "dist", "index.html")


# ── output (ASCII-only so it works in every terminal) ─────────────────────────
def say(msg): print(f"  {msg}", flush=True)
def step(msg): print(f"\n>> {msg}", flush=True)
def ok(msg): print(f"  [OK] {msg}", flush=True)
def warn(msg): print(f"  [..] {msg}", flush=True)
def die(msg, code=1):
    print(f"\n[ERROR] {msg}\n", flush=True)
    if os.name == "nt":
        try:
            input("Press Enter to close...")
        except EOFError:
            pass
    sys.exit(code)


def detect_os() -> str:
    sysname = platform.system()
    return {"Windows": "Windows", "Darwin": "macOS (Apple)", "Linux": "Linux"}.get(
        sysname, sysname or "Unknown")


# ── backend dependencies ──────────────────────────────────────────────────────
def ensure_backend_deps():
    step("Checking backend dependencies (Python)...")
    try:
        import fastapi, uvicorn  # noqa: F401
        import pydantic
        if int(pydantic.VERSION.split(".")[0]) < 2:
            raise ImportError("pydantic v2 required")
        ok("Backend dependencies present.")
        return
    except Exception:
        warn("Installing backend dependencies... (first run only)")
    req = os.path.join(ROOT, "requirements-web.txt")
    cmd = [sys.executable, "-m", "pip", "install", "-q", "-r", req]
    if subprocess.call(cmd) != 0:
        die("Failed to install Python dependencies. Try:\n"
            f"    {sys.executable} -m pip install -r requirements-web.txt")
    ok("Backend dependencies installed.")


# ── frontend build ────────────────────────────────────────────────────────────
def ensure_frontend_build():
    step("Checking web UI build...")
    if os.path.isfile(DIST_INDEX):
        ok("Web UI already built.")
        return

    npm = shutil.which("npm")
    if not npm:
        die("The web UI has not been built and Node.js/npm was not found.\n"
            "  Install Node.js 18+ from https://nodejs.org, then run Start again.\n"
            "  (Node is only needed once, to build the interface.)")

    if not os.path.isdir(os.path.join(FRONTEND, "node_modules")):
        warn("Installing web UI packages... (first run only, this can take a minute)")
        if subprocess.call([npm, "install"], cwd=FRONTEND) != 0:
            die("`npm install` failed in the frontend directory.")

    warn("Building the web UI...")
    if subprocess.call([npm, "run", "build"], cwd=FRONTEND) != 0:
        die("`npm run build` failed.")
    if not os.path.isfile(DIST_INDEX):
        die("Build finished but frontend/dist/index.html is missing.")
    ok("Web UI built.")


# ── browser opener (waits for the server to answer) ──────────────────────────
def open_when_ready():
    for _ in range(120):  # up to ~60s
        try:
            with urllib.request.urlopen(URL, timeout=1) as r:
                if r.status < 500:
                    break
        except Exception:
            time.sleep(0.5)
    import webbrowser
    print(f"\n  >> Opening {URL} in your browser.", flush=True)
    print("     Open it in more windows/tabs to play multiplayer.", flush=True)
    print("     Press Ctrl+C in this window to stop the server.\n", flush=True)
    try:
        webbrowser.open(URL)
    except Exception:
        say(f"Could not auto-open a browser - visit {URL} manually.")


def main():
    os.chdir(ROOT)
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    print("=" * 56)
    print("  ABSOLUTESPACE - launcher")
    print("=" * 56)
    say(f"Operating system : {detect_os()}")
    say(f"Python           : {platform.python_version()} ({sys.executable})")

    ensure_backend_deps()
    ensure_frontend_build()

    step("Starting the game server...")
    # Import after deps are guaranteed.
    import uvicorn
    from backend.server import app

    threading.Thread(target=open_when_ready, daemon=True).start()
    try:
        uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
    except KeyboardInterrupt:
        pass
    print("\n  Server stopped. Goodbye, Director.")


# (console output is intentionally ASCII-only for cross-terminal safety)


if __name__ == "__main__":
    main()
