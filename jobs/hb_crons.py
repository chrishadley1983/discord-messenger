"""Hadley Bricks cron routes — local scheduling (migrated off Vercel).

Until Jun 2026 these ran as Vercel crons and were part of the Fluid CPU
burn (see docs/plans/vercel-fluid-cpu-migration.md). They now run against
the local NSSM production server (localhost:3000) on the same UTC schedule,
hardened per the production validation workflow of 12 Jun:

- _tracked_job registration (bot.py) -> failures alert #alerts + land in
  job_history / the 06:50 system-health report
- embedded-failure detection: a 200 {success:true} whose body carries
  failure counters (usersFailed/failures/errors) RAISES — the validation
  run caught ebay-stock-sync doing zero work behind a green envelope
- startup catch-up: MemoryJobStore can't replay runs missed while the bot
  was down (overnight-reset case); a one-shot check ~2 min after boot
  re-runs any cron whose UTC slot passed today without a success record
- retry-once: a failed run schedules a single retry 15 min later (the
  validation failure was a transient eBay 'fetch failed'); the original
  failure still alerts
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from logger import logger

HB_BASE = os.environ.get("HB_LOCAL_URL", "http://localhost:3000")
HB_ENV_LOCAL = (
    Path(__file__).resolve().parents[2]
    / "hadley-bricks-inventory-management" / "apps" / "web" / ".env.local"
)
JOB_DB = Path(__file__).resolve().parents[1] / "peter_dashboard" / "job_history.db"

# job_id -> (route path, UTC hour, UTC minute, day_of_week or None)
CRON_SPECS = {
    "hb_ebay_stock_sync": ("/api/cron/ebay-stock-sync", 6, 0, None),
    "hb_bricqer_batch_sync": ("/api/cron/bricqer-batch-sync", 6, 30, None),
    "hb_scanner_image_cleanup": ("/api/cron/scanner-image-cleanup", 3, 0, "sun"),
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
        # 200 {success:true} can still mean zero work done — surface embedded
        # failure counters (validation caught usersFailed:1/totalListings:0)
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
    path = CRON_SPECS[job_id][0]
    try:
        return _run_cron_route(path)
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
    """Single retry of a failed cron; logged under <job_id>_retry in history."""
    try:
        await asyncio.to_thread(_run_with_retry, job_id, True)
        logger.info(f"{job_id} retry succeeded")
    except Exception as e:
        logger.error(f"{job_id} retry also failed: {e}")


async def hb_ebay_stock_sync(bot=None):
    """Daily eBay stock sync (was Vercel cron 06:00 UTC)."""
    await asyncio.to_thread(_run_with_retry, "hb_ebay_stock_sync")


async def hb_bricqer_batch_sync(bot=None):
    """Daily Bricqer batch sync (was Vercel cron 06:30 UTC)."""
    await asyncio.to_thread(_run_with_retry, "hb_bricqer_batch_sync")


async def hb_scanner_image_cleanup(bot=None):
    """Weekly scanner image cleanup (was Vercel cron Sun 03:00 UTC)."""
    await asyncio.to_thread(_run_with_retry, "hb_scanner_image_cleanup")


def _succeeded_today(job_id: str, now_utc: datetime) -> bool:
    """True if job_history shows a success for job_id since UTC midnight."""
    if not JOB_DB.exists():
        return False
    day_start_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
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


async def catch_up_missed_runs():
    """Run any cron whose UTC slot passed today with no success recorded.

    Covers the MemoryJobStore gap: jobs registered after a boot have no
    memory of runs missed while the box was off (overnight-reset case).
    """
    now = datetime.now(timezone.utc)
    weekday = now.strftime("%a").lower()[:3]
    for job_id, (path, hour, minute, dow) in CRON_SPECS.items():
        if dow is not None and weekday != dow:
            continue
        slot = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now < slot + timedelta(minutes=5):
            continue  # slot not (comfortably) passed yet — scheduler owns it
        if _succeeded_today(job_id, now):
            continue
        logger.warning(f"catch-up: {job_id} missed its {hour:02d}:{minute:02d} UTC slot — running now")
        try:
            # call via module globals so the _tracked_job wrapper (bound by
            # bot.py) records the run in job_history and alerts on failure
            await globals()[job_id]()
            logger.info(f"catch-up: {job_id} completed")
        except Exception as e:
            logger.error(f"catch-up: {job_id} failed: {e}")


def register_hb_crons(scheduler, bot=None):
    """Register the migrated HB crons (UTC, matching the old Vercel times)."""
    global _scheduler
    _scheduler = scheduler

    scheduler.add_job(
        hb_ebay_stock_sync, "cron", hour=6, minute=0, timezone="UTC",
        id="hb_ebay_stock_sync", max_instances=1, coalesce=True,
        misfire_grace_time=3600 * 4, args=[bot],
    )
    scheduler.add_job(
        hb_bricqer_batch_sync, "cron", hour=6, minute=30, timezone="UTC",
        id="hb_bricqer_batch_sync", max_instances=1, coalesce=True,
        misfire_grace_time=3600 * 4, args=[bot],
    )
    scheduler.add_job(
        hb_scanner_image_cleanup, "cron", day_of_week="sun", hour=3, minute=0,
        timezone="UTC", id="hb_scanner_image_cleanup", max_instances=1,
        coalesce=True, misfire_grace_time=3600 * 8, args=[bot],
    )
    # one-shot catch-up shortly after boot (give NSSM/HadleyBricks time to be up)
    scheduler.add_job(
        catch_up_missed_runs, "date",
        run_date=datetime.now(timezone.utc) + timedelta(minutes=2),
        id="hb_crons_catch_up", replace_existing=True,
    )
    logger.info("HB crons registered locally (ebay-stock 06:00, bricqer 06:30, cleanup Sun 03:00 UTC; catch-up in 2 min)")
