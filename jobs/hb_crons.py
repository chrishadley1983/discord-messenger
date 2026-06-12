"""Hadley Bricks cron routes — local scheduling (migrated off Vercel).

Until Jun 2026 these ran as Vercel crons and burned ~75% of the free Fluid
CPU allowance (see docs/plans/vercel-fluid-cpu-migration.md). They now run
against the local NSSM production server (localhost:3000) on the same
schedule, with the reporting the Vercel versions never had:

- registered via _tracked_job in bot.py -> failures post to #alerts and
  land in job_history.db / the 06:50 system-health report
- each run logs the route's response summary
- a non-200, a connection failure (box mid-restart), or a "200 but
  error-shaped body" all raise -> tracked failure, never a silent OK

Auth: Authorization: Bearer ${CRON_SECRET} (verifyCronAuth), read from the
HB repo's apps/web/.env.local.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import httpx

from logger import logger

HB_BASE = os.environ.get("HB_LOCAL_URL", "http://localhost:3000")
HB_ENV_LOCAL = (
    Path(__file__).resolve().parents[2]
    / "hadley-bricks-inventory-management" / "apps" / "web" / ".env.local"
)


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
        raise RuntimeError("CRON_SECRET not found (env or HB apps/web/.env.local)")

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
    # routes report failures inside a 200 sometimes — surface those too
    if isinstance(body, dict) and (body.get("error") or body.get("success") is False):
        raise RuntimeError(f"{path} reported failure: {str(body)[:300]}")
    logger.info(f"HB cron {path} OK: {str(body)[:200]}")
    return body if isinstance(body, dict) else {"result": body}


async def hb_ebay_stock_sync(bot=None):
    """Daily eBay stock sync (was Vercel cron 06:00)."""
    await asyncio.to_thread(_run_cron_route, "/api/cron/ebay-stock-sync")


async def hb_bricqer_batch_sync(bot=None):
    """Daily Bricqer batch sync (was Vercel cron 06:30)."""
    await asyncio.to_thread(_run_cron_route, "/api/cron/bricqer-batch-sync")


async def hb_scanner_image_cleanup(bot=None):
    """Weekly scanner image cleanup (was Vercel cron Sun 03:00)."""
    await asyncio.to_thread(_run_cron_route, "/api/cron/scanner-image-cleanup")


def register_hb_crons(scheduler, bot=None):
    """Register the migrated HB crons.

    Times match the old vercel.json schedules (which Vercel ran in UTC);
    kept in UTC here so eBay/Bricqer-side expectations are unchanged.
    coalesce=True runs a missed job once on bot restart (overnight-reset
    scenario) instead of dropping it.
    """
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
    logger.info("HB crons registered locally (ebay-stock 06:00, bricqer 06:30, cleanup Sun 03:00 UTC)")
