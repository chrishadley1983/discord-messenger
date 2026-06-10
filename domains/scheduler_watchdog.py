"""APScheduler watchdog — alert on jobs that hang or get repeatedly missed.

Catches the class of failure where a job enters its run, never returns, and
APScheduler then silently skips every subsequent tick because of
`max_instances=1`. Without this, a wedged job is invisible in Discord until
someone reads the logs (e.g. prolific monitor stuck May 14-18 2026).

Listens for two scheduler events:
- EVENT_JOB_MAX_INSTANCES — fired every time a tick is dropped because the
  previous invocation is still running (i.e. probably hung).
- EVENT_JOB_MISSED — fired when a tick was missed past `misfire_grace_time`.

Posts to DISCORD_WEBHOOK_ALERTS once per job after a threshold of consecutive
skips, then throttles to one alert per job per hour so we don't spam.
Counter is reset whenever the job successfully executes.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field

import httpx
from apscheduler.events import (
    EVENT_JOB_EXECUTED,
    EVENT_JOB_MAX_INSTANCES,
    EVENT_JOB_MISSED,
    JobEvent,
    JobExecutionEvent,
    JobSubmissionEvent,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from logger import logger

_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_ALERTS", "")

ALERT_AFTER_CONSECUTIVE_SKIPS = 3
ALERT_THROTTLE_SECONDS = 3600


@dataclass
class _JobState:
    consecutive_skips: int = 0
    first_skip_ts: float = 0.0
    last_alert_ts: float = 0.0
    last_reason: str = ""


_state: dict[str, _JobState] = {}
_lock = threading.Lock()


def _post_to_discord(content: str) -> None:
    """Fire-and-forget Discord webhook post, never blocks the scheduler."""
    if not _WEBHOOK:
        return

    def _send():
        try:
            httpx.post(_WEBHOOK, json={"content": content}, timeout=10)
        except Exception:
            pass

    threading.Thread(target=_send, daemon=True).start()


def _on_skip(event: JobEvent | JobSubmissionEvent, reason: str) -> None:
    job_id = event.job_id
    now = time.time()

    with _lock:
        state = _state.setdefault(job_id, _JobState())
        if state.consecutive_skips == 0:
            state.first_skip_ts = now
        state.consecutive_skips += 1
        state.last_reason = reason

        should_alert = (
            state.consecutive_skips >= ALERT_AFTER_CONSECUTIVE_SKIPS
            and (now - state.last_alert_ts) > ALERT_THROTTLE_SECONDS
        )
        if should_alert:
            state.last_alert_ts = now
            stuck_for_s = int(now - state.first_skip_ts)
            count = state.consecutive_skips

    if should_alert:
        stuck_for_str = (
            f"{stuck_for_s // 60}m {stuck_for_s % 60}s" if stuck_for_s >= 60 else f"{stuck_for_s}s"
        )
        msg = (
            f":rotating_light: **Scheduler job wedged: `{job_id}`**\n"
            f"Reason: `{reason}` x{count} consecutive (first skip {stuck_for_str} ago).\n"
            f"Likely cause: the previous invocation is hung. Check logs, restart `DiscordBot` if needed."
        )
        logger.error(
            f"Scheduler watchdog: {job_id} skipped {count}x ({reason}) over {stuck_for_str} — alerting Discord"
        )
        _post_to_discord(msg)


def _on_success(event: JobExecutionEvent) -> None:
    job_id = event.job_id
    with _lock:
        state = _state.get(job_id)
        if state and state.consecutive_skips > 0:
            recovered_after = state.consecutive_skips
            state.consecutive_skips = 0
            state.first_skip_ts = 0.0
            state.last_reason = ""
        else:
            recovered_after = 0

    if recovered_after >= ALERT_AFTER_CONSECUTIVE_SKIPS:
        msg = f":white_check_mark: Scheduler job `{job_id}` recovered after {recovered_after} consecutive skips."
        logger.info(f"Scheduler watchdog: {job_id} recovered after {recovered_after} skips")
        _post_to_discord(msg)


def register(scheduler: AsyncIOScheduler) -> None:
    """Attach the watchdog listeners to a started APScheduler instance."""
    if not _WEBHOOK:
        logger.warning("Scheduler watchdog: DISCORD_WEBHOOK_ALERTS not set — alerts disabled")

    scheduler.add_listener(lambda e: _on_skip(e, "max_instances_reached"), EVENT_JOB_MAX_INSTANCES)
    scheduler.add_listener(lambda e: _on_skip(e, "missed"), EVENT_JOB_MISSED)
    scheduler.add_listener(_on_success, EVENT_JOB_EXECUTED)
    logger.info(
        f"Scheduler watchdog registered "
        f"(alert after {ALERT_AFTER_CONSECUTIVE_SKIPS} consecutive skips, "
        f"throttle {ALERT_THROTTLE_SECONDS // 60}m)"
    )
