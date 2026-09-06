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
     sessions so they reload it. If the Windows access token has merely
     *expired* (valid refresh token still present — the normal overnight state,
     since nothing on Windows runs Claude while Chris sleeps), it first forces
     a refresh by running a cheap headless ``claude -p`` on Windows, which
     makes the CLI mint a fresh access token and rewrite the file. Only if
     Windows is *unrefreshable* (unreadable / no refresh token / refresh call
     fails) does it alert, since only a manual ``/login`` can fix that — and
     even then, when no session is actually locked out and the static token
     still authenticates, the alert is a low-key maintenance note rather than
     a 🚨 (the 2026-08-09 overnight storm paged Chris seven times about
     credential files nothing was reading).

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
# Static long-lived OAuth token (claude setup-token) sourced by every channel's
# launch.sh via scripts/claude-oauth-env.sh. While this file is non-empty,
# CLAUDE_CODE_OAUTH_TOKEN overrides .credentials.json entirely — so if the
# token inside it gets REVOKED (e.g. Chris does a fresh interactive /login
# elsewhere, which invalidates the prior grant), restarting a session just
# re-sources the same dead token and it 401s again on the next message
# (2026-07-21 incident: 6 crash-loops in ~90 min while the watchdog "healed"
# credentials.json that nothing was reading).
STATIC_TOKEN_FILE = "/mnt/c/Users/Chris Hadley/.claude-code-oauth-token"

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
# Standing "static token missing" condition: probe every 30 min, re-alert every
# 6 h. The quarantine path removes the token file by design, but that degraded
# mode must not persist silently — after the 2026-07-21 quarantine it sat
# unprovisioned for days while WSL sessions shared the rotating credentials
# chain with Windows Claude Code, logging the Windows/VS Code side out every
# morning via the refresh race (2026-07-23).
STATIC_TOKEN_CHECK_SECONDS = 1800
STATIC_TOKEN_ALERT_SECONDS = 6 * 3600
# Active Windows-token refresh (a real Haiku call): don't hammer it if the
# refresh keeps failing — one attempt per this window.
WINDOWS_REFRESH_COOLDOWN_SECONDS = 600
# The benign stale-creds condition (files expired, channels fine on the static
# token) is a maintenance note, not an incident — alert at most every 6 h.
STALE_CREDS_ALERT_SECONDS = 6 * 3600

_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_ALERTS", "")

_lock = threading.Lock()
_last_restart_ts: dict[str, float] = {}
_last_alert_ts: dict[str, float] = {}
_last_static_probe_ts = 0.0
_last_win_refresh_ts = 0.0
# Cache of the last static-token live test (ts, result) — a stale 401 marker
# can sit in a pane's tail for many ticks and each test is a real API call.
_last_token_test: tuple[float, "bool | None"] = (0.0, None)
TOKEN_TEST_CACHE_SECONDS = 600


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


def _wsl_reachable(timeout: int = 10) -> bool:
    """True when a trivial command completes inside WSL within ``timeout``."""
    try:
        r = _wsl("echo ok", timeout=timeout)
    except Exception:
        return False
    return r.returncode == 0 and "ok" in (r.stdout or "")


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
    # Unrolled per-channel (no shell variables): wsl.exe pipes the command line
    # through an intermediate WSL shell that expands $vars BEFORE bash -lc runs,
    # so a `for s in ...; echo "$s"` loop always echoed empty strings and this
    # scan returned [] even with a 401 on screen (2026-07-16 incident).
    script = "; ".join(
        f"tmux capture-pane -p -J -t {name} 2>/dev/null | tail -40 | "
        f"grep -q \"{_AUTH_FAIL_MARKERS}\" && echo {name}"
        for name in CHANNELS
    )
    try:
        r = _wsl(script)
    except Exception as exc:
        logger.warning(f"channel_auth: 401 scan failed: {exc}")
        return []
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip() in CHANNELS]


def _static_token_present() -> bool:
    """True if the static-token file exists and is non-empty (i.e. launch.sh
    will export CLAUDE_CODE_OAUTH_TOKEN from it on the next restart)."""
    try:
        r = _wsl(f"[ -s \"{STATIC_TOKEN_FILE}\" ] && echo YES || echo NO")
        return "YES" in r.stdout
    except Exception as exc:
        logger.warning(f"channel_auth: static-token check failed: {exc}")
        return False


def _static_token_auth_ok() -> bool | None:
    """Live-test the static token: does it actually authenticate?

    Returns True (token works), False (definitive auth failure — revoked or
    invalid), None (couldn't determine: timeout, network trouble, no token).

    Why: the pane-401 scan can't tell a logged-out CLI from a Claude turn whose
    *tool output* happens to contain 401/auth-error text. On 2026-07-23 the
    Heartbeat job printed such text while the WSL creds file expired in the
    same minute, and the watchdog quarantined a perfectly valid token —
    putting jobs-channel back on the shared credentials chain and logging
    Chris's Windows Claude Code out hours later. A ~1p Haiku call is cheap
    insurance against destroying a good token; it runs only when locked
    sessions are found with the token present (rare), throttled below.
    """
    cmd = (
        f'TOK="$(tr -d "\\r\\n" < "{STATIC_TOKEN_FILE}" 2>/dev/null)"; '
        'if [ -z "$TOK" ]; then echo __NO_TOKEN__; exit 0; fi; '
        'CLAUDE_CODE_OAUTH_TOKEN="$TOK" timeout 90 claude -p "reply OK" '
        "--model claude-haiku-4-5-20251001 < /dev/null 2>&1"
    )
    try:
        r = _wsl(cmd, timeout=120)
    except Exception as exc:
        logger.warning(f"channel_auth: static-token live test errored: {exc}")
        return None
    out = (r.stdout + r.stderr).lower()
    if "__no_token__" in out:
        return None
    auth_fail = (
        "401" in out
        or "revoked" in out
        or "please run /login" in out
        or "invalid authentication" in out
    )
    if auth_fail:
        return False
    if r.returncode == 0 and r.stdout.strip():
        return True
    logger.warning(
        f"channel_auth: static-token live test inconclusive rc={r.returncode} "
        f"out={r.stdout.strip()[:200]!r}"
    )
    return None


def _cached_static_token_ok() -> "bool | None":
    """:func:`_static_token_auth_ok` behind the shared cache — each test is a
    real API call, and a verdict from the last few minutes is plenty."""
    global _last_token_test
    now = time.time()
    with _lock:
        ts, ok = _last_token_test
        if now - ts < TOKEN_TEST_CACHE_SECONDS:
            return ok
    ok = _static_token_auth_ok()
    with _lock:
        _last_token_test = (now, ok)
    return ok


def _quarantine_static_token() -> bool:
    """Rename the static-token file aside so launch.sh falls back to
    .credentials.json (which this watchdog keeps synced from Windows).

    Called when sessions are 401ing WITH the static token in play — that means
    the token has been revoked server-side and no number of session restarts
    can fix it. Falling back to the rotating credentials file restores service
    (at the cost of re-exposing the refresh race this token was built to
    avoid) until Chris mints a fresh token with `claude setup-token`.
    """
    cmd = (
        f"mv \"{STATIC_TOKEN_FILE}\" "
        f"\"{STATIC_TOKEN_FILE}.revoked-$(date +%Y%m%d-%H%M%S)\" && echo OK"
    )
    try:
        r = _wsl(cmd)
    except Exception as exc:
        logger.error(f"channel_auth: static-token quarantine failed: {exc}")
        return False
    ok = r.returncode == 0 and "OK" in r.stdout
    if ok:
        logger.warning(
            "channel_auth: quarantined REVOKED static OAuth token "
            f"({STATIC_TOKEN_FILE}) — sessions fall back to .credentials.json"
        )
    else:
        logger.error(
            f"channel_auth: static-token quarantine rc={r.returncode} err={r.stderr.strip()}"
        )
    return ok


def _windows_claude_exe() -> str | None:
    """Locate the Windows claude CLI. The NSSM service PATH often lacks
    user-level bin dirs (same failure as the surge deploy incident), so fall
    back to the native-install location."""
    import shutil

    exe = shutil.which("claude") or shutil.which("claude.exe")
    if exe:
        return exe
    cand = os.path.join(os.path.expanduser("~"), ".local", "bin", "claude.exe")
    return cand if os.path.exists(cand) else None


def _refresh_windows_token() -> bool:
    """Force the Windows OAuth access token to refresh. Returns success.

    The Windows credentials file regularly holds an *expired* access token with
    a perfectly valid refresh token: access tokens live 8 h, Chris stops using
    Claude in the evening, and nothing on Windows runs it overnight — so an
    evening-minted token dies in the small hours with no process around to
    renew it. The CLI refreshes lazily on use, so a cheap headless Haiku call
    makes it mint a fresh access token and rewrite ``.credentials.json``,
    which the heal path can then sync into WSL. Without this the watchdog sat
    blocked for 3.5 h on 2026-08-09 waiting for *something else* to refresh.

    Runs on Windows (bot.py's host) with ``CLAUDE_CODE_OAUTH_TOKEN`` stripped
    from the environment — with that var set the CLI would authenticate via
    the static token and never touch the credentials file.
    """
    global _last_win_refresh_ts
    now = time.time()
    with _lock:
        if now - _last_win_refresh_ts < WINDOWS_REFRESH_COOLDOWN_SECONDS:
            return False
        _last_win_refresh_ts = now

    exe = _windows_claude_exe()
    if not exe:
        logger.warning("channel_auth: no Windows claude CLI found — cannot active-refresh token")
        return False

    # Strip every competing auth source so the CLI authenticates via the
    # claude.ai login in .credentials.json — the file we're trying to refresh.
    # With any of these set they take precedence and the file is never touched
    # (the bot's env carries an ANTHROPIC_API_KEY that 401s the CLI outright).
    _auth_vars = {"CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"}
    env = {k: v for k, v in os.environ.items() if k not in _auth_vars}
    try:
        import tempfile

        # Neutral cwd: launched inside a project dir the CLI loads CLAUDE.md /
        # memory / plugins and a "reply OK" turn can blow past 2 minutes.
        r = subprocess.run(
            [exe, "-p", "reply OK", "--model", "claude-haiku-4-5-20251001"],
            capture_output=True,
            text=True,
            timeout=240,
            env=env,
            cwd=tempfile.gettempdir(),
            stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as exc:
        logger.warning(f"channel_auth: Windows token refresh call errored: {exc}")
        return False

    ok = r.returncode == 0 and bool(r.stdout.strip())
    if ok:
        logger.warning("channel_auth: actively refreshed the Windows OAuth token via headless claude")
    else:
        logger.warning(
            f"channel_auth: Windows token refresh failed rc={r.returncode} "
            f"out={(r.stdout + r.stderr).strip()[:200]!r}"
        )
    return ok


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


def force_restart_channel(name: str, mark_relaunched=None) -> bool:
    """Reactively restart one wedged channel session (cooldown-guarded).

    The pane-401 / corrupt-file detection in :func:`heal_channel_auth` cannot
    see a channel that is *wedged* — a stuck or silently-401'd Claude turn that
    keeps the HTTP server green and prints no ``/login`` marker, yet returns an
    empty response for every job (the 2026-06-22 incident: three LLM jobs each
    burned the full 20-min ``JOB_TIMEOUT_SECONDS`` before failing). The
    scheduler calls this the moment a channel job comes back empty twice, so the
    *next* scheduled job runs on a fresh session instead of every job hanging.

    Best-effort: returns False (never raises) on unknown name or cooldown so it
    is safe to fire-and-forget from the hot job path. Shares ``_last_restart_ts``
    with the proactive watchdog so the two never thrash the same session.
    """
    if name not in CHANNELS:
        logger.warning(f"channel_auth: refusing to restart unknown channel '{name}'")
        return False
    now = time.time()
    with _lock:
        if now - _last_restart_ts.get(name, 0.0) < RESTART_COOLDOWN_SECONDS:
            logger.info(f"channel_auth: reactive restart of '{name}' skipped (cooldown)")
            return False
        _last_restart_ts[name] = now
    ok = _restart_session(name)
    if ok:
        if mark_relaunched:
            try:
                mark_relaunched(name)
            except Exception:
                pass
        _alert(
            f"wedge-{name}",
            f":wrench: **Restarted wedged `{name}`.** It returned an empty "
            "response with no 401 marker (stuck/locked Claude turn). The next "
            "scheduled job should recover.",
        )
        logger.warning(f"channel_auth: reactively restarted wedged '{name}'")
    return ok


def _warn_if_static_token_missing() -> None:
    """Standing-condition alert: no static OAuth token is provisioned.

    Without it every WSL channel session falls back to the rotating
    ``.credentials.json`` chain shared with Chris's Windows Claude Code, and
    the overnight refresh race logs the Windows/VS Code side out each morning.
    Probes at most every STATIC_TOKEN_CHECK_SECONDS (one extra WSL round-trip),
    alerts at most every STATIC_TOKEN_ALERT_SECONDS.
    """
    global _last_static_probe_ts
    now = time.time()
    with _lock:
        if now - _last_static_probe_ts < STATIC_TOKEN_CHECK_SECONDS:
            return
        _last_static_probe_ts = now
    if _static_token_present():
        return
    logger.warning(
        "channel_auth: static OAuth token file missing — running in degraded "
        "shared-credentials mode (Windows morning-logout risk)"
    )
    _alert(
        "static-token-missing",
        ":warning: **No static Claude OAuth token is provisioned** (file "
        "missing or quarantined). All WSL channel sessions are sharing the "
        "rotating credentials chain with Windows Claude Code — the overnight "
        "refresh race will log the Windows/VS Code side out every morning. "
        "Fix: run `claude setup-token` in a normal Windows terminal, then in "
        "WSL: `scripts/set-claude-oauth-token.sh '<token>'`.",
        throttle=STATIC_TOKEN_ALERT_SECONDS,
    )


def _alert(key: str, msg: str, throttle: float = ALERT_THROTTLE_SECONDS) -> None:
    """Throttled fire-and-forget Discord post (one per `key` per window)."""
    now = time.time()
    with _lock:
        if now - _last_alert_ts.get(key, 0.0) < throttle:
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
    # If WSL itself is wedged every ``wsl`` call times out, every credential
    # read comes back "unreadable" (= corrupt) and the tick misdiagnoses a
    # healthy token chain as "WSL creds bad AND Windows creds bad — manual
    # /login required" (2026-09-06 01:29–01:36, Wi-Fi roam → WSL2 hang).
    # Recovering WSL is the WSL Watchdog scheduled task's job; skip the tick.
    if not _wsl_reachable():
        logger.warning(
            "channel_auth: WSL unreachable (probe timed out) — skipping auth "
            "tick; WSL Watchdog owns recovery"
        )
        return {
            "action": "wsl-unreachable",
            "wsl": CredsHealth(0, False, False, readable=False),
            "locked": [],
        }

    _warn_if_static_token_missing()

    wsl = _read_creds(WSL_CREDS)
    locked = _sessions_with_401()

    # Fast path: file is fine and nobody is locked out — nothing to do.
    if not wsl.corrupt and not locked:
        return {"action": "none", "wsl": wsl, "locked": []}

    # Something is wrong. We can only fix it if the Windows token is itself good.
    win = _read_creds(WIN_CREDS)

    # Expired-but-refreshable is the normal overnight state (8 h access token,
    # nobody using Claude on Windows) — don't wait for something else to renew
    # it, force the refresh ourselves and re-read.
    if win.readable and win.has_refresh and win.expired:
        if _refresh_windows_token():
            win = _read_creds(WIN_CREDS)

    if win.corrupt:
        # No session actually locked out + the static token (which is what the
        # channels really authenticate with) still works → nothing is failing.
        # Stale credential files are a maintenance note, not an incident.
        if not locked and _static_token_present() and _cached_static_token_ok() is not False:
            logger.warning(
                "channel_auth: WSL+Windows credential files stale but no session "
                "is locked out and the static token is healthy — benign, will "
                "retry the active refresh"
            )
            _alert(
                "stale-creds-benign",
                ":warning: **Claude OAuth credential files are stale** (Windows "
                "+ WSL access tokens expired and the automatic refresh hasn't "
                "succeeded yet). **Channels are unaffected** — they run on the "
                "static token and no session is locked out. I'll keep retrying; "
                "if this persists all day, run any `claude` command on Windows "
                "to renew.",
                throttle=STALE_CREDS_ALERT_SECONDS,
            )
            return {"action": "stale-creds-benign", "wsl": wsl, "win": win, "locked": locked}

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

    # Locked-out sessions while the static token is in play mean the token
    # itself has been REVOKED (fresh interactive login elsewhere invalidated
    # the grant). Restarting sessions without removing it just re-sources the
    # same dead token — the 2026-07-21 crash-loop. But VERIFY before
    # quarantining: the pane scan also matches auth-error text inside tool
    # output, and on 2026-07-23 that false positive destroyed a valid token.
    # A session whose env token verifiably authenticates cannot actually be
    # logged out, so on a confirmed-good token we skip quarantine AND restarts.
    quarantined = False
    if locked and _static_token_present():
        token_ok = _cached_static_token_ok()
        if token_ok is True:
            logger.warning(
                f"channel_auth: pane 401 markers in {locked} but the static "
                "token authenticates — spurious match (tool output), no action"
            )
            return {
                "action": "false-positive-401",
                "wsl": wsl,
                "locked": locked,
                "token_ok": True,
            }
        if token_ok is None:
            # Can't verify (network blip / timeout). Never destroy the token
            # on uncertainty — leave it for the next tick and just restart the
            # locked sessions below, which is safe either way.
            logger.warning(
                f"channel_auth: {locked} show 401 but static-token test was "
                "inconclusive — skipping quarantine, restarting sessions only"
            )
        else:
            quarantined = _quarantine_static_token()
        if quarantined:
            _alert(
                "static-token-revoked",
                ":rotating_light: **The static Claude OAuth token was revoked** "
                "(usually caused by a fresh `/login` somewhere else on the "
                "account). I've quarantined it so the channels fall back to the "
                "regular credentials file and service recovers. To restore the "
                "static token (recommended — it prevents the multi-session "
                "refresh race): run `claude setup-token` on Windows, then "
                "`scripts/set-claude-oauth-token.sh <token>`. "
                "**Any messages sent to Peter in the last few minutes were "
                "likely lost — please resend.**",
            )

    synced = False
    if wsl.corrupt or quarantined:
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
        if quarantined:
            bits.append("quarantined the revoked static token")
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
        "quarantined_static_token": quarantined,
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
        f"Static token : {'present' if _static_token_present() else 'MISSING (degraded shared-credentials mode)'}\n"
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
