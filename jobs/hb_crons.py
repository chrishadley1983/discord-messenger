"""Hadley Bricks cron routes — local scheduling (migrated off Vercel).

Phase 1 (12 Jun 2026): the 3 vercel.json crons. Phase 2 (same day, plan v2
section 6): the 5 GCP Cloud Scheduler jobs whose Vercel routes carried ~88%
of the measured Fluid CPU wall time. GCP originals are PAUSED (not deleted)
for instant rollback; a +5-day evidence check deletes them.

Hardenings (from the 12 Jun production validation workflow):
- _tracked_job registration (bot.py) -> failures alert #alerts
- embedded-failure detection: 200 {success:true} bodies carrying failure
  counters (usersFailed/failures/errors) RAISE
- startup catch-up for once-daily jobs whose slot passed while the bot was
  down (MemoryJobStore can't replay); multi-slot jobs self-heal next slot
- retry-once 15 min after a failure
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from logger import logger

HB_BASE = os.environ.get("HB_LOCAL_URL", "http://localhost:3000")
HB_ENV_LOCAL = (
    Path(__file__).resolve().parents[2]
    / "hadley-bricks-inventory-management" / "apps" / "web" / ".env.local"
)
JOB_DB = Path(__file__).resolve().parents[1] / "peter_dashboard" / "job_history.db"

# job_id -> spec
#   path:      HB cron route
#   trigger:   APScheduler cron kwargs (must include timezone)
#   catch_up:  (hour, minute, tzname) for once-daily jobs only — replay if
#              the slot passed today with no success; None = self-heals
#   timeout:   per-request timeout (full-sync runs ~166s, retrain ran 894s)
CRON_SPECS: dict[str, dict] = {
    # ── phase 1 (vercel.json crons) ───────────────────────────────────────
    "hb_ebay_stock_sync": {
        "path": "/api/cron/ebay-stock-sync",
        "trigger": {"hour": 6, "minute": 0, "timezone": "UTC"},
        "catch_up": (6, 0, "UTC"), "timeout": 320,
    },
    "hb_bricqer_batch_sync": {
        "path": "/api/cron/bricqer-batch-sync",
        "trigger": {"hour": 6, "minute": 30, "timezone": "UTC"},
        "catch_up": (6, 30, "UTC"), "timeout": 320,
    },
    "hb_scanner_image_cleanup": {
        "path": "/api/cron/scanner-image-cleanup",
        "trigger": {"day_of_week": "sun", "hour": 3, "minute": 0, "timezone": "UTC"},
        "catch_up": None, "timeout": 320,
    },
    # ── phase 2 (ex-GCP Cloud Scheduler; schedules preserved exactly) ────
    "hb_full_sync": {
        "path": "/api/cron/full-sync",
        "trigger": {"hour": "3,7,11,15,19,23", "minute": 45, "timezone": "UTC"},
        "catch_up": None,  # 6 slots/day — next slot covers a miss
        "timeout": 540,
    },
    "hb_ebay_fp_cleanup": {
        "path": "/api/cron/ebay-fp-cleanup",
        "trigger": {"hour": 4, "minute": "0,15,30,45", "timezone": "UTC"},
        "catch_up": None,  # 4 slots in one hour; low stakes if a day slips
        "timeout": 320,
    },
    "hb_investment_sync": {
        "path": "/api/cron/investment-sync",
        "trigger": {"hour": 7, "minute": 0, "timezone": "UTC"},
        "catch_up": (7, 0, "UTC"), "timeout": 420,
    },
    "hb_cost_allocation": {
        "path": "/api/cron/cost-allocation",
        "trigger": {"hour": 21, "minute": 15, "timezone": "Europe/London"},
        "catch_up": (21, 15, "Europe/London"), "timeout": 420,
    },
    "hb_retirement_sync": {
        "path": "/api/cron/retirement-sync",
        "trigger": {"hour": 6, "minute": 0, "timezone": "UTC"},
        "catch_up": (6, 0, "UTC"), "timeout": 320,
    },
    # Never completed on Vercel (work needs ~15+ min vs the 300s cap; 5/5
    # timeouts since Mar) — the investment dashboard reads 4-month-stale
    # predictions. Local next start has no platform duration cap.
    "hb_investment_retrain": {
        "path": "/api/cron/investment-retrain",
        "trigger": {"day": 1, "hour": 5, "minute": 0, "timezone": "UTC"},
        "catch_up": None, "timeout": 2400,
    },
}

# numeric body fields that indicate work failed inside a 200 response
FAILURE_COUNTER_KEYS = ("usersFailed", "failures", "errors", "storageErrors", "itemsFailed")

_scheduler = None  # set by register_hb_crons; used for retry scheduling


def _cron_secret() -> str:
    key = os.environ.get("CRON_SECRET", "")
    if key:
        return key
    if HB_ENV_LOCAL.exists():
        for line in HB_ENV_LOCAL.read_text().splitlines():
            if line.startswith("CRON_SECRET="):
                return line.split("=", 1)[1].strip().strip('"')
    return ""


def _run_cron_route(path: str, timeout: int = 320) -> dict:
    """Invoke one HB cron route; raise on anything that isn't a clean success."""
    secret = _cron_secret()
    if not secret:
        raise RuntimeError(
            f"CRON_SECRET not found in env or {HB_ENV_LOCAL} — "
            "has the hadley-bricks repo moved?")

    resp = httpx.get(
        f"{HB_BASE}{path}",
        headers={"Authorization": f"Bearer {secret}"},
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"{path} returned {resp.status_code}: {resp.text[:200]}")
    try:
        body = resp.json()
    except ValueError:
        body = {"raw": resp.text[:200]}

    if isinstance(body, dict):
        if body.get("error") or body.get("success") is False:
            raise RuntimeError(f"{path} reported failure: {str(body)[:300]}")
        embedded = {
            k: body[k] for k in FAILURE_COUNTER_KEYS
            if isinstance(body.get(k), (int, float)) and body[k] > 0
        }
        if embedded:
            raise RuntimeError(
                f"{path} returned success envelope but reported failures "
                f"{embedded}: {str(body)[:250]}")

    logger.info(f"HB cron {path} OK: {str(body)[:200]}")
    return body if isinstance(body, dict) else {"result": body}


def _run_with_retry(job_id: str, is_retry: bool = False) -> dict:
    spec = CRON_SPECS[job_id]
    try:
        return _run_cron_route(spec["path"], timeout=spec["timeout"])
    except Exception:
        if not is_retry and _scheduler is not None:
            when = datetime.now(timezone.utc) + timedelta(minutes=15)
            _scheduler.add_job(
                _retry_job, "date", run_date=when, args=[job_id],
                id=f"{job_id}_retry", replace_existing=True,
            )
            logger.warning(f"{job_id} failed — one retry scheduled for {when:%H:%M} UTC")
        raise


async def _retry_job(job_id: str):
    """Single retry of a failed cron.

    Recorded in job_history under the same job_id so _succeeded_recently
    sees a successful retry and catch-up doesn't double-run the job after
    a later same-day bot restart.
    """
    from peter_dashboard.api.jobs import record_job_complete, record_job_start
    exec_id = record_job_start(job_id)
    try:
        await asyncio.to_thread(_run_with_retry, job_id, True)
        record_job_complete(job_id, True, output="retry succeeded", execution_id=exec_id)
        logger.info(f"{job_id} retry succeeded")
    except Exception as e:
        record_job_complete(job_id, False, error=f"retry failed: {e}", execution_id=exec_id)
        logger.error(f"{job_id} retry also failed: {e}")


def _make_job(job_id: str):
    async def _job(bot=None):
        await asyncio.to_thread(_run_with_retry, job_id)
    _job.__name__ = job_id
    return _job


# Public job callables — bot.py rebinds these via _tracked_job before
# register_hb_crons runs, so keep them as real module attributes.
hb_ebay_stock_sync = _make_job("hb_ebay_stock_sync")
hb_bricqer_batch_sync = _make_job("hb_bricqer_batch_sync")
hb_scanner_image_cleanup = _make_job("hb_scanner_image_cleanup")
hb_full_sync = _make_job("hb_full_sync")
hb_ebay_fp_cleanup = _make_job("hb_ebay_fp_cleanup")
hb_investment_sync = _make_job("hb_investment_sync")
hb_cost_allocation = _make_job("hb_cost_allocation")
hb_retirement_sync = _make_job("hb_retirement_sync")
hb_investment_retrain = _make_job("hb_investment_retrain")


def _succeeded_recently(job_id: str, now_utc: datetime, hours: float = 25.0) -> bool:
    """True if job_history shows a success in the trailing window.

    Trailing 25h (not "since midnight"): an outage straddling local
    midnight would otherwise permanently drop a run — cost-allocation at
    21:15 London had the narrowest window.
    """
    if not JOB_DB.exists():
        return False
    day_start_utc = now_utc - timedelta(hours=hours)
    try:
        con = sqlite3.connect(JOB_DB)
        rows = list(con.execute(
            "SELECT started_at FROM job_executions "
            "WHERE job_id = ? AND status = 'success' ORDER BY id DESC LIMIT 10",
            (job_id,),
        ))
        con.close()
    except sqlite3.Error as e:
        logger.warning(f"catch-up: job_history read failed: {e}")
        return True  # fail safe: don't double-run when we can't tell
    for (started,) in rows:
        try:
            dt = datetime.fromisoformat(started)
            if dt.astimezone(timezone.utc) >= day_start_utc:
                return True
        except ValueError:
            continue
    return False


async def _wait_for_hb(max_wait_s: int = 240) -> bool:
    """Wait for localhost:3000 to serve before catch-up fires 4 routes at a
    cold boot (NSSM next start can lag the bot; a crash-looping server
    would otherwise produce an immediate 4-alert burst)."""
    deadline = datetime.now(timezone.utc) + timedelta(seconds=max_wait_s)
    while datetime.now(timezone.utc) < deadline:
        try:
            r = await asyncio.to_thread(
                httpx.get, f"{HB_BASE}/api/health", timeout=5)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        await asyncio.sleep(10)
    logger.warning("catch-up: HB server not ready after %ss", max_wait_s)
    return False


async def catch_up_missed_runs():
    """Run any once-daily cron whose slot passed with no recent success."""
    if not await _wait_for_hb():
        return
    now = datetime.now(timezone.utc)
    for job_id, spec in CRON_SPECS.items():
        cu = spec.get("catch_up")
        if not cu:
            continue
        hour, minute, tzname = cu
        local_now = now.astimezone(ZoneInfo(tzname))
        slot_local = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if local_now < slot_local:
            # today's slot still ahead — but check YESTERDAY's slot wasn't
            # dropped by an outage straddling midnight
            slot_local -= timedelta(days=1)
        if _succeeded_recently(job_id, now):
            continue
        logger.warning(
            f"catch-up: {job_id} missed its {hour:02d}:{minute:02d} {tzname} slot — running now")
        try:
            # via module globals so the _tracked_job wrapper records the run
            await globals()[job_id]()
            logger.info(f"catch-up: {job_id} completed")
        except Exception as e:
            logger.error(f"catch-up: {job_id} failed: {e}")


def register_hb_crons(scheduler, bot=None, only: set[str] | None = None):
    """Register the migrated HB crons (schedules preserved from origin)."""
    global _scheduler
    _scheduler = scheduler

    for job_id, spec in CRON_SPECS.items():
        if only is not None and job_id not in only:
            continue
        scheduler.add_job(
            globals()[job_id], "cron", id=job_id,
            max_instances=1, coalesce=True,
            misfire_grace_time=3600 * 2, args=[bot],
            **spec["trigger"],
        )
    scheduler.add_job(
        catch_up_missed_runs, "date",
        run_date=datetime.now(timezone.utc) + timedelta(minutes=2),
        id="hb_crons_catch_up", replace_existing=True,
    )
    logger.info(f"HB crons registered locally: {len(CRON_SPECS)} jobs + catch-up in 2 min")
