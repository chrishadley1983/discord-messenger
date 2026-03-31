"""Daily journal service — one free-text entry per day (upsert)."""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from domains.accountability.db import headers, read_headers, table_url

logger = logging.getLogger(__name__)
UK_TZ = ZoneInfo("Europe/London")
TABLE = "journal_entries"


def _today() -> str:
    return datetime.now(UK_TZ).date().isoformat()


async def save_journal(content: str, log_date: str | None = None) -> dict | None:
    """Save or update today's journal entry. Upserts on (user_id, date)."""
    target_date = log_date or _today()
    payload = {"content": content, "date": target_date, "user_id": "chris"}

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
            logger.error(f"Save journal failed ({resp.status_code}): {resp.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"Save journal error: {e}")
        return None


async def get_journal_today() -> dict | None:
    """Get today's journal entry."""
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
        logger.error(f"Get journal today error: {e}")
        return None


async def get_journal_history(days: int = 7) -> list[dict]:
    """Get journal entries for the last N days."""
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
        logger.error(f"Get journal history error: {e}")
        return []
