"""Channel MCP-init watchdog — restart a session whose MCP servers never started.

Blind spot this closes (incident 2026-09-06/07): the WSL restart relaunched
jobs-channel cold, all four npx-launched MCP servers (supabase, playwright,
context7, searxng) timed out at startup, and the session ran a whole day with
``:8103/health`` green while every skill that needed an MCP tool silently had
none — two blank Vercel Usage reports before anyone noticed. Nothing polls for
this state: the health port is served by the channel's own Node process, not
by Claude, and the pane prints no marker.

The failure IS recorded in the session transcript the first time a turn asks
for tools, so every couple of minutes this:

  1. asks WSL to scan ``~/.claude/projects/-home-chris-hadley-peterbot`` for
     recent transcripts (``channel_mcp_scan.py``, run inside WSL, cached per
     file size+mtime),
  2. maps each channel to its CURRENT session's transcript — the newest file
     that identifies the channel and started after the tmux session was
     created (an older file is the previous session and must not count),
  3. if that transcript shows MCP startup failures and the channel is between
     turns, restarts it once (``force_restart_channel`` — cooldown-guarded,
     alerts #alerts), remembers the session id so it never loops, and stops
     after RESTART_BUDGET restarts per channel per RESTART_WINDOW_S (an npm
     registry outage would otherwise cause a restart after every first turn).

With ``MCP_TIMEOUT=120000`` in every launch.sh the relaunch has a warm npx
cache and a longer window, so one restart is normally enough.

Known limitation: if launch.sh's own crash loop relaunches claude inside the
same tmux session, the dead transcript stays "current" until the new claude's
first turn, so that fresh claude may be restarted once more. Harmless (a
second cold start) and rare.
"""
from __future__ import annotations

import json
import subprocess
import time

import httpx

from logger import logger

CHANNEL_PORTS: dict[str, int] = {
    "peter-channel": 8104,
    "whatsapp-channel": 8102,
    "jobs-channel": 8103,
    "jobs-channel-sonnet": 8105,
    "extract-channel": 8106,
}
TRANSCRIPT_DIR = "/home/chris_hadley/.claude/projects/-home-chris-hadley-peterbot"
SCAN_SCRIPT = "/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger/domains/peterbot/channel_mcp_scan.py"
SCAN_MAX_AGE_H = 36.0
# When the health endpoint can't tell us whether a turn is in flight, only act
# once the transcript has been quiet this long.
QUIET_SECONDS = 120
# tmux session_created vs transcript first timestamp: allow clock slop.
CREATED_SLOP_S = 5
# A health port can report "busy" forever (peter-channel counts a dropped
# message as never replied). A turn that runs a long tool writes nothing to the
# transcript while the tool executes, and jobs may legitimately run 10 min
# (JOB_TIMEOUT_MS), so only override a "busy" reading after a silence no real
# turn survives.
STALE_BUSY_S = 1800
# Restart budget per channel: beyond this, alert instead of cycling.
RESTART_BUDGET = 3
RESTART_WINDOW_S = 6 * 3600

# channel -> session_id we already restarted for (one restart per session).
_handled: dict[str, str] = {}
# channel -> epoch times of restarts we performed (budget).
_restarts: dict[str, list[float]] = {}


def _wsl(cmd: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["wsl", "bash", "-lc", cmd],
        capture_output=True, text=True, timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def scan_transcripts() -> list[dict] | None:
    """Run the scanner inside WSL. None when WSL is unreachable (skip the tick)."""
    try:
        r = _wsl(f"python3 '{SCAN_SCRIPT}' '{TRANSCRIPT_DIR}' {SCAN_MAX_AGE_H}", timeout=60)
    except Exception as exc:
        logger.warning(f"mcp_watchdog: transcript scan failed: {exc}")
        return None
    if r.returncode != 0:
        logger.warning(f"mcp_watchdog: scanner rc={r.returncode}: {r.stderr.strip()[:200]}")
        return None
    try:
        return json.loads(r.stdout or "[]")
    except ValueError:
        logger.warning(f"mcp_watchdog: scanner output not JSON: {r.stdout[:120]!r}")
        return None


def tmux_session_created() -> dict[str, float]:
    """name -> epoch seconds the tmux session was created (missing = not running)."""
    out: dict[str, float] = {}
    try:
        r = _wsl("tmux list-sessions -F '#{session_name} #{session_created}' 2>/dev/null")
    except Exception as exc:
        logger.warning(f"mcp_watchdog: tmux query failed: {exc}")
        return out
    for line in (r.stdout or "").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in CHANNEL_PORTS:
            try:
                out[parts[0]] = float(parts[1])
            except ValueError:
                pass
    return out


def channel_busy(name: str) -> bool | None:
    """True/False from the channel's /health counters; None when unknowable."""
    port = CHANNEL_PORTS.get(name)
    if not port:
        return None
    try:
        data = httpx.get(f"http://localhost:{port}/health", timeout=3).json()
        if "messages_in" in data and "messages_out" in data:
            return int(data["messages_in"]) != int(data["messages_out"])
        for key in ("pending_jobs", "pending"):
            if key in data:
                return int(data[key]) > 0
    except Exception:
        return None
    return None


def budget_ok(history: list[float], now: float,
              limit: int = RESTART_BUDGET, window_s: float = RESTART_WINDOW_S) -> bool:
    """Pure: True while fewer than ``limit`` restarts happened in the window."""
    return sum(1 for t in history if now - t < window_s) < limit


def decide(
    scan: list[dict],
    created: dict[str, float],
    busy: dict[str, bool | None],
    handled: dict[str, str],
    now: float,
    quiet_s: int = QUIET_SECONDS,
) -> list[dict]:
    """Pure: which channels to restart, and why. Each result:
    {channel, session_id, servers, reason}."""
    actions: list[dict] = []
    for name in CHANNEL_PORTS:
        if name not in created:
            continue  # tmux session not running — the launch watchdog owns that
        since = created[name] - CREATED_SLOP_S
        mine = [r for r in scan
                if r.get("channel") == name and r.get("first_ts") and r["first_ts"] >= since]
        if not mine:
            continue  # fresh session with no transcript yet, or previous session's file
        cur = max(mine, key=lambda r: r.get("mtime", 0))
        if not cur.get("mcp_failed"):
            continue
        sid = cur.get("session_id", cur.get("file", ""))
        if handled.get(name) == sid:
            continue
        b = busy.get(name)
        silent_for = now - float(cur.get("mtime", 0))
        if b is True and silent_for < STALE_BUSY_S:
            continue  # a turn is in flight — try again next tick
        if b is None and silent_for < quiet_s:
            continue  # can't see turns; wait for the transcript to go quiet
        actions.append({
            "channel": name, "session_id": sid,
            "servers": list(cur.get("failed_servers") or []),
            "reason": f"MCP servers failed to start in session {sid[:8]}: "
                      f"{', '.join(cur.get('failed_servers') or ['unknown'])}",
        })
    return actions


def check_and_restart(mark_relaunched=None) -> dict:
    """One tick. Safe on a timer; never raises."""
    scan = scan_transcripts()
    if scan is None:
        return {"action": "skipped", "why": "scan unavailable"}
    created = tmux_session_created()
    busy = {name: channel_busy(name) for name in CHANNEL_PORTS if name in created}
    now = time.time()
    actions = decide(scan, created, busy, _handled, now)
    restarted: list[str] = []
    for a in actions:
        name = a["channel"]
        hist = _restarts.setdefault(name, [])
        if not budget_ok(hist, now):
            try:
                from domains.peterbot.channel_auth import _alert
                _alert(f"mcp-budget-{name}",
                       f":warning: **`{name}` keeps starting without its MCP servers** "
                       f"({', '.join(a['servers']) or 'unknown'}) — {RESTART_BUDGET} restarts in "
                       f"{RESTART_WINDOW_S // 3600} h, so I've stopped cycling it. Check npm/npx "
                       "reachability in WSL (`claude mcp list` in ~/peterbot).",
                       throttle=RESTART_WINDOW_S)
            except Exception:
                pass
            _handled[name] = a["session_id"]  # don't re-evaluate this session every tick
            logger.warning(f"mcp_watchdog: restart budget exhausted for '{name}' — alert only")
            continue
        try:
            from domains.peterbot.channel_auth import force_restart_channel
            ok = force_restart_channel(
                name, mark_relaunched=mark_relaunched,
                reason=(f":electric_plug: **Restarted `{name}` — its MCP servers never started** "
                        f"({', '.join(a['servers']) or 'unknown'} timed out at launch), so every "
                        "skill needing those tools was silently blind. Fresh session should connect."),
            )
        except Exception as exc:
            logger.warning(f"mcp_watchdog: restart of '{name}' failed: {exc}")
            ok = False
        # Only a performed restart marks the session handled: a cooldown-skipped
        # attempt is retried next tick while it's still the same dead session.
        if ok:
            _handled[name] = a["session_id"]
            hist.append(now)
            restarted.append(name)
            logger.warning(f"mcp_watchdog: {a['reason']} — restarted '{name}'")
    return {"action": "restarted" if restarted else "none", "restarted": restarted,
            "candidates": [a["channel"] for a in actions]}
