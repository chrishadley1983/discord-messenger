"""Mood tracking service — daily mood score (1-10) with optional note."""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from domains.accountability.db import headers, read_headers, table_url

logger = logging.getLogger(__name__)
UK_TZ = ZoneInfo("Europe/London")
TABLE = "mood_entries"


def _today() -> str:
    return datetime.now(UK_TZ).date().isoformat()


async def log_mood(score: int, note: str | None = None, log_date: str | None = None) -> dict | None:
    """Log or update today's mood. Upserts on (user_id, date)."""
    target_date = log_date or _today()
    payload = {"score": score, "date": target_date, "user_id": "chris"}
    if note:
        payload["note"] = note

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            h = headers(returning=True)
            h["Prefer"] = "return=representation,resolution=merge-duplicates"
            resp = await client.post(
                table_url(TABLE), headers=h,
                params={"on_conflict": "user_id,date"},
                json=payload,
            )
            if resp.status_code in (200, 201):
                rows = resp.json()
                return rows[0] if rows else None
            logger.error(f"Log mood failed ({resp.status_code}): {resp.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"Log mood error: {e}")
        return None


async def get_mood_today() -> dict | None:
    """Get today's mood entry."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                table_url(TABLE), headers=read_headers(),
                params={"user_id": "eq.chris", "date": f"eq.{_today()}", "select": "*"},
            )
            if resp.status_code == 200:
                rows = resp.json()
                return rows[0] if rows else None
            return None
    except Exception as e:
        logger.error(f"Get mood today error: {e}")
        return None


async def get_mood_history(days: int = 31) -> list[dict]:
    """Get mood entries for the last N days."""
    from datetime import date
    cutoff = (datetime.now(UK_TZ).date() - timedelta(days=days)).isoformat()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                table_url(TABLE), headers=read_headers(),
                params={
                    "user_id": "eq.chris",
                    "date": f"gte.{cutoff}",
                    "select": "*",
                    "order": "date.desc",
                },
            )
            return resp.json() if resp.status_code == 200 else []
    except Exception as e:
        logger.error(f"Get mood history error: {e}")
        return []


async def get_mood_summary() -> dict:
    """Today's mood + 7-day trend + average."""
    today = await get_mood_today()
    history = await get_mood_history(days=7)

    scores = [h["score"] for h in history if h.get("score")]
    week_avg = round(sum(scores) / len(scores), 1) if scores else None

    # Trend: compare last 3 days avg to previous 3 days
    recent = scores[:3]
    older = scores[3:6]
    if recent and older:
        trend = "up" if sum(recent) / len(recent) > sum(older) / len(older) + 0.5 else \
                "down" if sum(recent) / len(recent) < sum(older) / len(older) - 0.5 else "flat"
    else:
        trend = "flat"

    return {
        "today": today,
        "week_avg": week_avg,
        "trend": trend,
        "history_7": history[:7],
    }
