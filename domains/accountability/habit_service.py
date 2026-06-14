"""Private habit accountability tracker.

Single-habit daily Y/N log with streak computation. SENSITIVE: the habit
itself is never named here or in any output — only streak numbers. The
habit-checkin / habit-weekly skills consume get_habit_status(); the
conversational Y/N reply path calls log_habit().

Table: public.habit_log (log_date date PK, result 'Y'/'N', day_number int).
Day 0 = 2026-06-12 (no check-in). Day 1 = 2026-06-13 (first check-in).
"""

import logging
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
UK_TZ = ZoneInfo("Europe/London")

HABIT_TABLE = "habit_log"
START_DATE = date(2026, 6, 12)  # Day 0 — no check-in needed


def _today() -> date:
    return datetime.now(UK_TZ).date()


def _read_headers() -> dict:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def _write_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation,resolution=merge-duplicates",
    }


def _url() -> str:
    return f"{SUPABASE_URL}/rest/v1/{HABIT_TABLE}"


def _day_number(d: date) -> int:
    return (d - START_DATE).days


async def _fetch_rows() -> list[dict]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _url(),
                headers=_read_headers(),
                params={"select": "log_date,result,day_number", "order": "log_date.asc"},
            )
            if resp.status_code == 200:
                return resp.json()
            logger.error(f"habit fetch failed: {resp.status_code} {resp.text[:160]}")
    except Exception as e:
        logger.error(f"habit fetch error: {e}")
    return []


def _compute(rows: list[dict]) -> dict:
    """Derive streak/score stats from raw log rows."""
    today = _today()
    parsed: list[tuple[str, str]] = []
    for r in rows:
        ld = r.get("log_date")
        res = (r.get("result") or "").upper()
        if ld and res in ("Y", "N"):
            parsed.append((str(ld)[:10], res))
    parsed.sort()
    by_date = {d: res for d, res in parsed}

    total_yes = sum(1 for _, res in parsed if res == "Y")
    total_no = sum(1 for _, res in parsed if res == "N")
    total_days = len(parsed)

    # Longest run of consecutive-calendar-day Y results.
    longest = run = 0
    prev_d: date | None = None
    for d_str, res in parsed:
        d = date.fromisoformat(d_str)
        if res == "Y":
            run = run + 1 if (prev_d is not None and (d - prev_d).days == 1) else 1
            longest = max(longest, run)
        else:
            run = 0
        prev_d = d

    # Current streak: consecutive Y ending today (or counting back from today).
    current = 0
    cursor = today
    while by_date.get(cursor.isoformat()) == "Y":
        current += 1
        cursor -= timedelta(days=1)

    day_number = _day_number(today)
    pct = round(total_yes / total_days * 100) if total_days else 0

    # Last 7 calendar days, oldest -> newest ('Y' / 'N' / None for no entry).
    week_results = [
        by_date.get((today - timedelta(days=i)).isoformat()) for i in range(6, -1, -1)
    ]
    week_number = (day_number - 1) // 7 + 1 if day_number >= 1 else 0

    return {
        "day_number": day_number,
        "current_streak": current,
        "longest_streak": longest,
        "total_yes": total_yes,
        "total_no": total_no,
        "total_days": total_days,
        "last_result": parsed[-1][1] if parsed else None,
        "percentage": pct,
        "start_date": START_DATE.isoformat(),
        "logged_today": today.isoformat() in by_date,
        "week_results": week_results,
        "week_number": week_number,
    }


async def get_habit_status() -> dict:
    """Current habit stats computed live from the log."""
    return _compute(await _fetch_rows())


async def log_habit(result: str, log_date: str | None = None) -> dict | None:
    """Upsert a Y/N result for a date (defaults to today). Returns saved row."""
    res = (result or "").strip().upper()
    if res in ("YES", "Y"):
        res = "Y"
    elif res in ("NO", "N"):
        res = "N"
    else:
        raise ValueError("result must be Y or N")
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    d = log_date or _today().isoformat()
    payload = {
        "log_date": d,
        "result": res,
        "day_number": _day_number(date.fromisoformat(d)),
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _url() + "?on_conflict=log_date",
                headers=_write_headers(),
                json=payload,
            )
            if resp.status_code in (200, 201):
                rows = resp.json()
                return rows[0] if rows else payload
            logger.error(f"habit log failed: {resp.status_code} {resp.text[:160]}")
    except Exception as e:
        logger.error(f"habit log error: {e}")
    return None
