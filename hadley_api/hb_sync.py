"""Fire-and-forget Hadley Bricks platform-sync trigger for the ``/hb`` proxy.

Why this exists (2026-09-04): Peter cannot call the HB order import directly.
``POST /api/cron/full-sync`` needs the ``CRON_SECRET`` bearer (not the
``x-api-key`` the proxy injects) and runs 100-285s, far past the proxy's 30s
timeout — so ``/hb/workflow/sync-all`` has 504'd on every call for months and
Peter has been guessing paths like ``/hb/orders/refresh`` (which land in the
session-gated ``orders/[id]`` route and 401).

``trigger()`` kicks the real cron route off in a background task and returns
202 immediately; ``status()`` reports the last run so Peter can poll instead of
guessing.  Pure helpers are kept free of FastAPI so they are unit-testable
without importing ``hadley_api.main``.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import httpx

log = logging.getLogger("hadley_api.hb_sync")

# Canonical trigger path plus every guess Peter has made in hadley_api.log.
# All of these forward to the same background full-sync.
TRIGGER_ALIASES: frozenset[str] = frozenset(
    {
        "sync/trigger",
        "sync",
        "sync/all",
        "sync/orders",
        "sync/amazon",
        "sync/ebay",
        "sync/full",
        "refresh",
        "orders/refresh",
        "orders/sync",
        "orders/sync/amazon",
        "orders/sync/ebay",
        "amazon/sync",
        "ebay/sync",
        "workflow/sync-all",
        "workflow/sync",
        "workflow/amazon-sync",
        "cron/full-sync",
    }
)
STATUS_ALIASES: frozenset[str] = frozenset({"sync/status", "sync/trigger/status"})

# Same lookup order as jobs/hb_crons.py: env first, then the HB app's .env.local.
HB_ENV_LOCAL = (
    Path(__file__).resolve().parents[2]
    / "hadley-bricks-inventory-management"
    / "apps"
    / "web"
    / ".env.local"
)
FULL_SYNC_PATH = "/api/cron/full-sync"
FULL_SYNC_TIMEOUT_S = 600.0  # measured 99-285s; the scheduled job allows 540s
EXPECTED_DURATION_S = 180


def normalise(path: str) -> str:
    """Trim slashes and lower-case so ``/Orders/Refresh/`` matches too."""
    return path.strip().strip("/").lower()


def is_trigger(path: str) -> bool:
    return normalise(path) in TRIGGER_ALIASES


def is_status(path: str) -> bool:
    return normalise(path) in STATUS_ALIASES


def cron_secret(env_local: Optional[Path] = None) -> str:
    """``CRON_SECRET`` from the environment, else parsed from the HB ``.env.local``."""
    key = os.environ.get("CRON_SECRET", "")
    if key:
        return key
    env_local = HB_ENV_LOCAL if env_local is None else env_local  # resolved at call time
    try:
        if env_local.exists():
            for line in env_local.read_text(encoding="utf-8").splitlines():
                if line.startswith("CRON_SECRET="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError as exc:  # unreadable file — report, don't crash the proxy
        log.warning("hb_sync: could not read %s: %s", env_local, exc)
    return ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_state: dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "http_status": None,
    "ok": None,
    "error": None,
    "summary": None,
    "runs": 0,
}
_task: Optional[asyncio.Task] = None


def _summarise(payload: Any) -> Any:
    """Keep the top-level counters, drop nested blobs.

    ``/api/cron/full-sync`` returns ``{success, duration, platformSyncs,
    stuckJobsFound, stuckJobsReset, weeklyStats}`` on success and
    ``{success: false, error}`` on failure (full-sync/route.ts).
    """
    if not isinstance(payload, dict):
        return str(payload)[:500]
    return {
        key: value
        for key, value in payload.items()
        if key
        in (
            "success",
            "duration",
            "platformSyncs",
            "stuckJobsFound",
            "stuckJobsReset",
            "error",
        )
    }


async def run_full_sync(base_url: str, secret: str) -> None:
    """POST the cron route and record the outcome in ``_state``."""
    # trigger() already stamped started_at when it scheduled us; only stamp
    # here when called directly (tests, future callers).
    _state.update(
        running=True,
        started_at=_state["started_at"] if _state["running"] else _now(),
        finished_at=None,
        http_status=None,
        ok=None,
        error=None,
        summary=None,
    )
    _state["runs"] += 1
    url = f"{base_url.rstrip('/')}{FULL_SYNC_PATH}"
    try:
        async with httpx.AsyncClient(timeout=FULL_SYNC_TIMEOUT_S) as client:
            resp = await client.post(url, headers={"Authorization": f"Bearer {secret}"})
        _state["http_status"] = resp.status_code
        try:
            body = resp.json()
        except ValueError:
            body = resp.text
        _state["summary"] = _summarise(body)
        _state["ok"] = resp.status_code == 200 and (
            not isinstance(body, dict) or body.get("success", True) is not False
        )
        if not _state["ok"]:
            _state["error"] = f"full-sync returned HTTP {resp.status_code}"
        log.info("hb_sync: full-sync finished http=%s ok=%s", resp.status_code, _state["ok"])
    except httpx.ConnectError:
        _state.update(ok=False, error="Hadley Bricks app is not running (port 3000)")
        log.warning("hb_sync: HB app unreachable at %s", url)
    except httpx.TimeoutException:
        _state.update(ok=False, error=f"full-sync did not finish within {int(FULL_SYNC_TIMEOUT_S)}s")
        log.warning("hb_sync: full-sync timed out after %ss", FULL_SYNC_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 — a background task must never raise
        _state.update(ok=False, error=f"{type(exc).__name__}: {exc}")
        log.exception("hb_sync: full-sync failed")
    finally:
        _state["running"] = False
        _state["finished_at"] = _now()


def status() -> dict[str, Any]:
    return {
        **_state,
        "poll": "/hb/sync/status",
        "hint": (
            "running=true: wait. ok=true: re-query /hb/picking-list/amazon or /hb/orders. "
            f"A run usually takes ~{EXPECTED_DURATION_S}s."
        ),
    }


Runner = Callable[[str, str], Awaitable[None]]


def trigger(
    base_url: str,
    *,
    secret: Optional[str] = None,
    runner: Optional[Runner] = None,
) -> tuple[int, dict[str, Any]]:
    """Start a background full-sync. Returns ``(http_status, json_body)``.

    202 when started (or already running: one sync at a time, so a second
    trigger just points at the in-flight run); 503 when no CRON_SECRET is
    available.  Must be called from inside a running event loop.
    """
    global _task
    key = cron_secret() if secret is None else secret
    if not key:
        return 503, {
            "accepted": False,
            "error": "CRON_SECRET not available to the Hadley API - cannot call /api/cron/full-sync",
            "fix": "set CRON_SECRET in Discord-Messenger/.env (copy from apps/web/.env.local) and restart HadleyAPI",
        }
    # Gate on the task object, not on _state["running"]: the flag is only set
    # once the task first runs, which is after this handler yields — two
    # triggers in the same tick would otherwise both start a full-sync.
    if _task is not None and not _task.done():
        return 202, {
            "accepted": True,
            "already_running": True,
            "started_at": _state["started_at"],
            "poll": "/hb/sync/status",
            "message": "A full sync is already in progress. Poll /hb/sync/status, then re-query orders.",
        }
    started_at = _now()
    _state.update(running=True, started_at=started_at, finished_at=None, ok=None, error=None)
    run = runner or run_full_sync  # resolved at call time so tests can patch the module attr
    _task = asyncio.get_running_loop().create_task(run(base_url, key))
    return 202, {
        "accepted": True,
        "already_running": False,
        "job": "full-sync",
        "started_at": started_at,
        "expected_duration_seconds": EXPECTED_DURATION_S,
        "poll": "/hb/sync/status",
        "message": (
            "Order import started in the background (eBay, Amazon, BrickLink, Brick Owl, Shopify). "
            f"Wait ~{EXPECTED_DURATION_S}s, check /hb/sync/status, then re-query "
            "/hb/picking-list/amazon or /hb/orders."
        ),
    }
