"""Evolution API WhatsApp watchdog — auto-restart on hangs, alert on device-removed.

Catches two distinct failure modes that both surface as "WhatsApp Send Failed":

1. **Hung process** — the Evolution Node.js process freezes (event loop stalled,
   container still 'Up' but API hangs or returns empty replies). Docker can't
   see it because the container has no healthcheck. Fix: docker restart — the
   WhatsApp session persists in evolution_postgres so no QR is needed.

2. **device_removed (401)** — the linked device was revoked from the phone.
   A restart will NOT fix this; only a fresh QR scan will. We detect the
   `disconnectionReasonCode == 401` and alert Discord instead of restart-looping.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from logger import logger

EVOLUTION_URL = os.environ.get("EVOLUTION_API_URL", "http://localhost:8085")
EVOLUTION_API_KEY = os.environ.get("EVOLUTION_API_KEY", "peter-whatsapp-2026-hadley")
EVOLUTION_INSTANCE = os.environ.get("EVOLUTION_INSTANCE", "peter-whatsapp")
CONTAINER_NAME = os.environ.get("EVOLUTION_CONTAINER", "evolution_api")
_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_ALERTS", "")

PROBE_TIMEOUT_S = 5
POST_RESTART_WAIT_S = 25
MAX_RESTARTS_PER_WINDOW = 2
RESTART_WINDOW_S = 30 * 60
ALERT_THROTTLE_S = 30 * 60

_recent_restarts: list[float] = []
_last_alert_ts: float = 0.0
_lock = threading.Lock()


def _post_to_discord(content: str) -> None:
    if not _WEBHOOK:
        return

    def _send():
        try:
            httpx.post(_WEBHOOK, json={"content": content}, timeout=10)
        except Exception:
            pass

    threading.Thread(target=_send, daemon=True).start()


def _alert(msg: str) -> None:
    global _last_alert_ts
    now = time.time()
    with _lock:
        if (now - _last_alert_ts) < ALERT_THROTTLE_S:
            return
        _last_alert_ts = now
    logger.error(f"WhatsApp watchdog alert: {msg}")
    _post_to_discord(msg)


def _probe_state() -> tuple[str, str | None]:
    """Return (state, error). state is 'open', 'closed', 'connecting',
    'unknown', or 'unreachable'. error is a short tag for logs/alerts."""
    url = f"{EVOLUTION_URL}/instance/connectionState/{EVOLUTION_INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY}
    try:
        r = httpx.get(url, headers=headers, timeout=PROBE_TIMEOUT_S)
    except httpx.TimeoutException:
        return "unreachable", "timeout"
    except httpx.RequestError as e:
        return "unreachable", f"request_error:{type(e).__name__}"

    if r.status_code != 200:
        return "unreachable", f"http_{r.status_code}"
    try:
        state = r.json().get("instance", {}).get("state", "unknown")
    except ValueError:
        return "unreachable", "bad_json"
    return state, None


def _fetch_disconnection_reason() -> int | None:
    """Return disconnectionReasonCode from fetchInstances, or None on failure."""
    url = f"{EVOLUTION_URL}/instance/fetchInstances"
    headers = {"apikey": EVOLUTION_API_KEY}
    try:
        r = httpx.get(url, headers=headers, timeout=PROBE_TIMEOUT_S)
        if r.status_code != 200:
            return None
        for inst in r.json():
            if inst.get("name") == EVOLUTION_INSTANCE:
                return inst.get("disconnectionReasonCode")
    except (httpx.RequestError, ValueError):
        return None
    return None


def _restart_container() -> bool:
    try:
        result = subprocess.run(
            ["docker", "restart", CONTAINER_NAME],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            logger.warning(f"WhatsApp watchdog: restarted container {CONTAINER_NAME}")
            return True
        logger.error(
            f"WhatsApp watchdog: docker restart failed (rc={result.returncode}): "
            f"{result.stderr.strip()[:200]}"
        )
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.error(f"WhatsApp watchdog: docker restart errored: {e}")
        return False


def _restart_count_in_window() -> int:
    now = time.time()
    with _lock:
        _recent_restarts[:] = [t for t in _recent_restarts if (now - t) < RESTART_WINDOW_S]
        return len(_recent_restarts)


def _record_restart() -> None:
    with _lock:
        _recent_restarts.append(time.time())


def check_and_recover() -> None:
    """Run one probe-restart-verify cycle. Safe to call on a timer."""
    state, err = _probe_state()
    if state == "open":
        return

    reason_code = _fetch_disconnection_reason()
    if reason_code == 401:
        _alert(
            ":rotating_light: **WhatsApp device removed (401)**\n"
            f"State: `{state}` — phone revoked the linked device. "
            "Auto-restart will not fix this; re-pair via QR: "
            f"`curl {EVOLUTION_URL}/instance/connect/{EVOLUTION_INSTANCE} "
            f"-H 'apikey: ...'` and scan with WhatsApp > Linked Devices."
        )
        return

    prior_restarts = _restart_count_in_window()
    if prior_restarts >= MAX_RESTARTS_PER_WINDOW:
        _alert(
            f":rotating_light: **WhatsApp watchdog backing off**\n"
            f"State: `{state}` ({err or 'no error'}); already restarted "
            f"{prior_restarts}x in last {RESTART_WINDOW_S // 60}m. "
            f"Disconnection reason: `{reason_code}`. Manual investigation needed."
        )
        return

    logger.warning(
        f"WhatsApp watchdog: state={state} err={err} reason={reason_code} — restarting container"
    )
    if not _restart_container():
        _alert(
            f":rotating_light: **WhatsApp watchdog: docker restart failed** "
            f"(state was `{state}`, err `{err}`). Check NSSM/Docker."
        )
        return

    _record_restart()
    time.sleep(POST_RESTART_WAIT_S)

    new_state, new_err = _probe_state()
    if new_state == "open":
        logger.info(f"WhatsApp watchdog: recovered after restart (state=open)")
        _post_to_discord(
            f":white_check_mark: WhatsApp auto-recovered: Evolution API was "
            f"`{state}` ({err or 'no error'}), restarted, now `open`."
        )
    else:
        _alert(
            f":warning: **WhatsApp watchdog: restart did not restore connection**\n"
            f"State after restart: `{new_state}` ({new_err or 'no error'}). "
            f"Will retry on next tick (up to {MAX_RESTARTS_PER_WINDOW} per "
            f"{RESTART_WINDOW_S // 60}m before backoff)."
        )


def register(scheduler: AsyncIOScheduler, *, minutes: int = 2) -> None:
    """Register the watchdog as a recurring APScheduler job."""
    if not _WEBHOOK:
        logger.warning("WhatsApp watchdog: DISCORD_WEBHOOK_ALERTS not set — alerts disabled")

    scheduler.add_job(
        check_and_recover,
        "interval",
        minutes=minutes,
        id="whatsapp_watchdog",
        max_instances=1,
        replace_existing=True,
    )
    logger.info(f"WhatsApp watchdog registered (every {minutes} min)")
