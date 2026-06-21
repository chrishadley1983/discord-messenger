"""WSL Claude Code auth watchdog — detect and auto-heal expired/corrupt OAuth.

All WSL channel sessions (peter/whatsapp/jobs/jobs-sonnet/extract) share ONE
OAuth credentials file: ``/home/chris_hadley/.claude/.credentials.json``.

Anthropic's OAuth rotates the refresh token on every refresh (each refresh
returns a *new* refresh token and invalidates the old one). With several Claude
Code instances sharing that single file, they normally refresh at staggered
times and it's fine — but when two refresh inside the same window the loser can
write back a file whose ``refreshToken`` is blank. Once the access token then
expires, no session can self-refresh and every one 401s::

    ● Please run /login · API Error: 401 Invalid authentication credentials

The HTTP ``/health`` endpoints stay green (the node MCP wrapper is alive — only
the Claude CLI *inside* the tmux is logged out), so the existing channel
watchdog (which only probes HTTP health) misses it entirely, and scheduled jobs
silently return "empty response". This is exactly the 2026-06-20 incident where
every morning job failed (see memory: incident-wsl-claude-token-expiry).

This watchdog closes that blind spot:

  1. Reads the on-disk WSL token. If its ``refreshToken`` is blank/missing or it
     has already expired, the file is corrupt and can't self-heal.
  2. Greps each channel's tmux pane for the 401 marker to find sessions that are
     actually locked out (a session can 401 on a stale in-memory token even when
     the file is fine — the cure for that is a restart so it reloads the file).
  3. Heals by copying Chris's *Windows* token — a single always-logged-in
     instance that refreshes cleanly — into WSL, then restarting the locked-out
     sessions so they reload it. If Windows is also logged out it alerts instead
     of copying garbage, since only a manual ``/login`` can fix that.

bot.py registers :func:`heal_channel_auth` on the 1-min channel-watchdog tick.
Run standalone for a read-only status report:  ``python -m domains.peterbot.channel_auth``
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass

try:
    from logger import logger
except Exception:  # pragma: no cover - allow standalone use without app logger
    import logging

    logger = logging.getLogger("channel_auth")

# --- Paths (all resolved inside WSL) -----------------------------------------
WSL_CREDS = "/home/chris_hadley/.claude/.credentials.json"
# Chris's Windows credentials, reached from WSL via the drvfs mount. His Windows
# Claude Code stays logged in (single instance, max sub) so this token refreshes
# reliably and always has a valid refreshToken.
WIN_CREDS = "/mnt/c/Users/Chris Hadley/.claude/.credentials.json"

_BASE = "/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger"
# Every persistent channel session that shares the OAuth file.
CHANNELS = [
    "peter-channel",
    "whatsapp-channel",
    "jobs-channel",
    "jobs-channel-sonnet",
    "extract-channel",
]

# 401 markers Claude Code prints when its token is dead.
_AUTH_FAIL_MARKERS = "Please run /login\\|401 Invalid authentication credentials"

# Don't restart the same session more than once per this window (give a fresh
# session time to cold-start before we'd consider touching it again). Mirrors
# bot.py's CHANNEL_RECYCLE_GRACE_SECONDS so the two watchdogs don't fight.
RESTART_COOLDOWN_SECONDS = 180
# Throttle Discord alerts so a stuck condition doesn't spam #alerts.
ALERT_THROTTLE_SECONDS = 1800

_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_ALERTS", "")

_lock = threading.Lock()
_last_restart_ts: dict[str, float] = {}
_last_alert_ts: dict[str, float] = {}


# --- WSL plumbing ------------------------------------------------------------
def _wsl(cmd: str, timeout: int = 20) -> subprocess.CompletedProcess:
    """Run a bash command inside the default WSL distro.

    bot.py runs on Windows under NSSM; everything auth-related lives in WSL, so
    we shell out exactly like _launch_channel_sessions() does. Called from
    Python (not Git Bash) so there's no MSYS path mangling to worry about.
    """
    return subprocess.run(
        ["wsl", "bash", "-lc", cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


@dataclass
class CredsHealth:
    expires_at: int          # epoch ms; 0 if unknown
    expired: bool
    has_refresh: bool
    readable: bool           # False if the file was missing / unparseable

    @property
    def corrupt(self) -> bool:
        """True when the file cannot self-heal: unreadable, no refresh token,
        or the access token has already expired."""
        return (not self.readable) or (not self.has_refresh) or self.expired


def _read_creds(path: str) -> CredsHealth:
    """Read a Claude OAuth credentials file inside WSL and report its health.

    Uses a python3 one-liner so we get robust JSON parsing rather than grep.
    The path may contain spaces (Windows mount) — it's a Python string literal
    inside the single-quoted ``python3 -c`` body, so that's fine.
    """
    code = (
        "import json,time;"
        f"o=json.load(open(\"{path}\")).get(\"claudeAiOauth\",{{}});"
        "e=int(o.get(\"expiresAt\",0) or 0);"
        "print(e, 1 if e and e<time.time()*1000 else 0, 1 if o.get(\"refreshToken\") else 0)"
    )
    try:
        r = _wsl(f"python3 -c '{code}'")
    except Exception as exc:
        logger.warning(f"channel_auth: failed to read {path}: {exc}")
        return CredsHealth(0, False, False, readable=False)

    if r.returncode != 0:
        logger.debug(f"channel_auth: read {path} rc={r.returncode} err={r.stderr.strip()}")
        return CredsHealth(0, False, False, readable=False)
    try:
        exp_s, expired_s, refresh_s = r.stdout.split()
        return CredsHealth(
            expires_at=int(exp_s),
            expired=expired_s == "1",
            has_refresh=refresh_s == "1",
            readable=True,
        )
    except ValueError:
        logger.debug(f"channel_auth: unexpected creds output for {path}: {r.stdout!r}")
        return CredsHealth(0, False, False, readable=False)


def _sessions_with_401() -> list[str]:
    """Return channel sessions whose tmux pane currently shows a 401 marker.

    One WSL round-trip greps the tail of every pane; only the recent screen is
    checked (`tail -40`) so a 401 that has already scrolled off after recovery
    doesn't produce a false positive.
    """
    names = " ".join(CHANNELS)
    script = (
        f"for s in {names}; do "
        f"tmux capture-pane -p -J -t \"$s\" 2>/dev/null | tail -40 | "
        f"grep -q \"{_AUTH_FAIL_MARKERS}\" && echo \"$s\"; "
        f"done"
    )
    try:
        r = _wsl(script)
    except Exception as exc:
        logger.warning(f"channel_auth: 401 scan failed: {exc}")
        return []
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip() in CHANNELS]


def _sync_creds_from_windows() -> bool:
    """Copy the Windows OAuth token into WSL (preserving 0600). Returns success."""
    cmd = (
        f"cp \"{WIN_CREDS}\" \"{WSL_CREDS}\" && chmod 600 \"{WSL_CREDS}\" && echo OK"
    )
    try:
        r = _wsl(cmd)
    except Exception as exc:
        logger.error(f"channel_auth: creds sync failed: {exc}")
        return False
    ok = r.returncode == 0 and "OK" in r.stdout
    if not ok:
        logger.error(f"channel_auth: creds sync rc={r.returncode} err={r.stderr.strip()}")
    return ok


def _restart_session(name: str) -> bool:
    """Kill + relaunch one channel tmux session via its launch.sh.

    Same mechanism bot.py._launch_channel_sessions() uses, so a freshly
    relaunched session loads the (now-good) credentials file on startup. The
    launch.sh while-loop is killed with the session, so no stray process leaks.
    """
    script = f"{_BASE}/{name}/launch.sh"
    cmd = (
        f"tmux kill-session -t {name} 2>/dev/null; sleep 1; "
        f"tmux new-session -d -s {name} -c \"$HOME/peterbot\" 'bash \"{script}\"'"
    )
    try:
        _wsl(cmd, timeout=30)
        logger.warning(f"channel_auth: restarted '{name}' to reload credentials")
        return True
    except Exception as exc:
        logger.error(f"channel_auth: failed to restart '{name}': {exc}")
        return False


def _alert(key: str, msg: str) -> None:
    """Throttled fire-and-forget Discord post (one per `key` per window)."""
    now = time.time()
    with _lock:
        if now - _last_alert_ts.get(key, 0.0) < ALERT_THROTTLE_SECONDS:
            return
        _last_alert_ts[key] = now
    if not _WEBHOOK:
        return

    def _send():
        try:
            import httpx

            httpx.post(_WEBHOOK, json={"content": msg[:1900]}, timeout=10)
        except Exception:
            pass

    threading.Thread(target=_send, daemon=True).start()


def heal_channel_auth(mark_relaunched=None) -> dict:
    """Detect and heal expired/corrupt WSL Claude auth. Idempotent; safe on a timer.

    Args:
        mark_relaunched: optional callable(name) invoked for every session this
            function restarts, so bot.py's channel watchdog can record the
            relaunch time and not immediately recycle a cold-starting session.

    Returns a small status dict (handy for the standalone CLI and tests).
    """
    wsl = _read_creds(WSL_CREDS)
    locked = _sessions_with_401()

    # Fast path: file is fine and nobody is locked out — nothing to do.
    if not wsl.corrupt and not locked:
        return {"action": "none", "wsl": wsl, "locked": []}

    # Something is wrong. We can only fix it if the Windows token is itself good.
    win = _read_creds(WIN_CREDS)
    if win.corrupt:
        _alert(
            "both-down",
            ":rotating_light: **WSL Claude auth is broken and the Windows token "
            "is also invalid.** Scheduled jobs / channels are failing. Run "
            "`/login` in Claude Code on Windows to restore both — WSL pulls its "
            "token from there.",
        )
        logger.error(
            "channel_auth: WSL creds bad AND Windows creds bad — manual /login required "
            f"(wsl corrupt={wsl.corrupt}, locked={locked})"
        )
        return {"action": "blocked-windows-down", "wsl": wsl, "win": win, "locked": locked}

    synced = False
    if wsl.corrupt:
        synced = _sync_creds_from_windows()
        if synced:
            logger.warning(
                "channel_auth: re-synced WSL credentials from Windows "
                f"(was readable={wsl.readable}, has_refresh={wsl.has_refresh}, expired={wsl.expired})"
            )

    # Restart only the sessions actually locked out, respecting the per-session
    # cooldown so we never thrash one that's still cold-starting.
    now = time.time()
    restarted: list[str] = []
    for name in locked:
        with _lock:
            if now - _last_restart_ts.get(name, 0.0) < RESTART_COOLDOWN_SECONDS:
                continue
            _last_restart_ts[name] = now
        if _restart_session(name):
            restarted.append(name)
            if mark_relaunched:
                try:
                    mark_relaunched(name)
                except Exception:
                    pass

    if synced or restarted:
        bits = []
        if synced:
            bits.append("re-synced the OAuth token from Windows")
        if restarted:
            bits.append("restarted " + ", ".join(f"`{n}`" for n in restarted))
        _alert(
            "healed",
            ":wrench: **Auto-healed WSL Claude auth.** "
            + "; ".join(bits)
            + ". Scheduled jobs / channels should be back to normal.",
        )
        logger.warning(
            f"channel_auth: healed (synced={synced}, restarted={restarted})"
        )

    return {
        "action": "healed",
        "wsl": wsl,
        "synced": synced,
        "restarted": restarted,
        "locked": locked,
    }


def _status_report() -> str:
    wsl = _read_creds(WSL_CREDS)
    win = _read_creds(WIN_CREDS)
    locked = _sessions_with_401()

    def _fmt(h: CredsHealth) -> str:
        if not h.readable:
            return "UNREADABLE"
        hrs = (h.expires_at - time.time() * 1000) / 3_600_000 if h.expires_at else 0
        return (
            f"readable={h.readable} expired={h.expired} has_refresh={h.has_refresh} "
            f"hours_left={hrs:.2f} corrupt={h.corrupt}"
        )

    return (
        "=== channel_auth status ===\n"
        f"WSL creds    : {_fmt(wsl)}\n"
        f"Windows creds: {_fmt(win)}\n"
        f"Sessions 401 : {locked or 'none'}\n"
        f"Webhook set  : {bool(_WEBHOOK)}\n"
    )


if __name__ == "__main__":
    import sys

    if "--heal" in sys.argv:
        print(_status_report())
        print("Running heal...")
        result = heal_channel_auth()
        print(f"Result: action={result.get('action')} "
              f"synced={result.get('synced')} restarted={result.get('restarted')}")
    else:
        print(_status_report())
        print("(read-only; pass --heal to actually sync + restart)")
