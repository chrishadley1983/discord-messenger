"""Audible API client for Peter.

IMPORTANT: the `audible` pip package pins httpx<0.24, which conflicts with
anthropic/supabase and broke DiscordBot startup when installed into the
shared Pythons (2026-06-10). It must therefore NEVER be pip-installed here.
Instead every call shells out to domains/audible/_bridge.py running inside
the audible-mcp project's uv environment, whose lockfile resolves audible +
httpx 0.28 cleanly. Auth is the MCP's auth.json (single source, refreshed
tokens picked up per call).

All functions are sync (subprocess); call via asyncio.to_thread from async
contexts. Each call costs ~1-2s of uv/process startup — fine for the
nightly adapter, monthly recommender, and ad-hoc API requests.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Any, Optional

MCP_DIR = Path(
    os.environ.get(
        "AUDIBLE_MCP_DIR",
        r"C:\Users\Chris Hadley\claude-projects\MCPs\audible-mcp",
    )
)
AUTH_FILE = Path(os.environ.get("AUDIBLE_AUTH_FILE", str(MCP_DIR / "auth.json")))
UV_EXE = os.environ.get("UV_EXE", r"C:\Users\Chris Hadley\.local\bin\uv.exe")
BRIDGE = Path(__file__).resolve().parent / "_bridge.py"

_TIMEOUT_S = 120

# Serialise bridge calls: concurrent `uv run` invocations on the same project
# contend on uv's lock and emit cp1252-encoded warnings that used to crash the
# strict-utf8 reader thread (stdout=None -> TypeError). Calls are infrequent,
# so a process-wide lock is the simplest correct fix.
_bridge_lock = threading.Lock()


def _run(command: str, **args: Any):
    if not AUTH_FILE.exists():
        raise RuntimeError(
            f"Audible auth.json not found at {AUTH_FILE} — "
            "run `uv run auth_setup.py` in the audible-mcp project."
        )
    args["auth_file"] = str(AUTH_FILE)
    with _bridge_lock:
        proc = subprocess.run(
            [UV_EXE, "run", "--directory", str(MCP_DIR), "python", str(BRIDGE),
             command, json.dumps(args)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=_TIMEOUT_S,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
    if proc.returncode != 0:
        raise RuntimeError(
            f"audible bridge '{command}' failed (rc={proc.returncode}): "
            f"{(proc.stderr or '').strip()[-400:]}"
        )
    return json.loads(proc.stdout)


def get_library(num_results: int = 1000) -> list[dict[str, Any]]:
    """Full library, newest purchases first."""
    return _run("library", num_results=num_results)


def get_finished_books(since: Optional[str] = None) -> list[dict[str, Any]]:
    """Finished books, optionally only those purchased on/after `since`
    (ISO date). Audible exposes no per-book finished date, so purchase
    date is the best available ordering signal."""
    return _run("finished", since=since)


def get_in_progress() -> list[dict[str, Any]]:
    """Books started but not finished (1% < complete < 100%)."""
    return [
        b for b in get_library()
        if not b["is_finished"] and 1 < (b.get("percent_complete") or 0) < 100
    ]


def get_similar(asin: str, num_results: int = 10) -> list[dict[str, Any]]:
    """Catalogue titles similar to a given book ("more like this").

    Note: the account-level `recommendations` endpoint 404s (deprecated by
    Audible — also broken in the audible-mcp project), so per-book sims +
    catalogue search are the discovery surface.
    """
    return _run("similar", asin=asin, num_results=num_results)


def search_catalogue(keywords: str, num_results: int = 10) -> list[dict[str, Any]]:
    """Search the Audible catalogue (un-owned titles included)."""
    return _run("search", keywords=keywords, num_results=num_results)


def get_listening_stats() -> dict[str, Any]:
    """Monthly + total listening time."""
    return _run("stats")
