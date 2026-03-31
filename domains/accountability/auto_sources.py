"""Auto-update engine for accountability goals.

Extensible registry mapping auto_source keys to Supabase queries.
Adding a new data source = adding one dict entry to AUTO_SOURCE_REGISTRY.
"""

import logging
import os
from datetime import date, datetime, timezone

import httpx

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")


# ── Source Registry ──────────────────────────────────────────────────────
# Each entry defines how to fetch a single value from Supabase.
#
# Keys:
#   table     — Supabase table name
#   column    — Column to extract the value from
#   date_col  — Column used for date filtering
#   filter    — Additional PostgREST query params
#   agg       — Aggregation strategy:
#                "latest"    → most recent row's value
#                "sum_today" → sum of all rows for target date

AUTO_SOURCE_REGISTRY = {
    "garmin_steps": {
        "table": "garmin_daily_summary",
        "column": "steps",
        "date_col": "date",
        "filter": {"user_id": "eq.chris"},
        "agg": "latest",
    },
    "garmin_sleep": {
        "table": "garmin_daily_summary",
        "column": "sleep_hours",
        "date_col": "date",
        "filter": {"user_id": "eq.chris"},
        "agg": "latest",
    },
    "nutrition_calories": {
        "table": "nutrition_logs",
        "column": "calories",
        "date_col": "logged_at",
        "filter": {},
        "agg": "sum_today",
    },
    "nutrition_water": {
        "table": "nutrition_logs",
        "column": "water_ml",
        "date_col": "logged_at",
        "filter": {},
        "agg": "sum_today",
    },
    "nutrition_protein": {
        "table": "nutrition_logs",
        "column": "protein_g",
        "date_col": "logged_at",
        "filter": {},
        "agg": "sum_today",
    },
    "weight": {
        "table": "weight_readings",
        "column": "weight_kg",
        "date_col": "measured_at",
        "filter": {"user_id": "eq.chris"},
        "agg": "latest",
    },
}


def _read_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }


async def fetch_auto_value(source_key: str, target_date: str | None = None) -> float | None:
    """Fetch a single value from Supabase based on the registry config.

    Args:
        source_key: Key in AUTO_SOURCE_REGISTRY
        target_date: ISO date string (defaults to today)

    Returns:
        The fetched value, or None if unavailable
    """
    config = AUTO_SOURCE_REGISTRY.get(source_key)
    if not config:
        logger.warning(f"Unknown auto_source: {source_key}")
        return None

    if not SUPABASE_URL or not SUPABASE_KEY:
        return None

    from zoneinfo import ZoneInfo
    uk_today = datetime.now(ZoneInfo("Europe/London")).date()
    target = target_date or uk_today.isoformat()
    table = config["table"]
    column = config["column"]
    agg = config["agg"]
    url = f"{SUPABASE_URL}/rest/v1/{table}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if agg == "latest":
                # Get most recent row for the target date
                date_col = config["date_col"]
                params = {
                    "select": column,
                    "order": f"{date_col}.desc",
                    "limit": "1",
                    **config.get("filter", {}),
                }
                # DATE columns use eq, TIMESTAMP columns need a range
                if date_col == "date":
                    params[date_col] = f"eq.{target}"
                else:
                    from datetime import timedelta
                    next_day = (date.fromisoformat(target) + timedelta(days=1)).isoformat()
                    params["and"] = f"({date_col}.gte.{target}T00:00:00,{date_col}.lt.{next_day}T00:00:00)"
                resp = await client.get(url, headers=_read_headers(), params=params)

                if resp.status_code == 200:
                    rows = resp.json()
                    if rows:
                        val = rows[0].get(column)
                        return float(val) if val is not None else None
                return None

            elif agg == "sum_today":
                # Sum all rows for target date using date range filter
                date_col = config["date_col"]
                from datetime import timedelta
                next_day_str = (date.fromisoformat(target) + timedelta(days=1)).isoformat()

                # Select both value column and date column for client-side verification
                select_cols = f"{column},{date_col}"

                if date_col == "date":
                    # DATE column: exact match
                    params = {
                        "select": select_cols,
                        date_col: f"eq.{target}",
                        **config.get("filter", {}),
                    }
                else:
                    # TIMESTAMP column: use PostgREST 'and' filter for range
                    params = {
                        "select": select_cols,
                        "and": f"({date_col}.gte.{target}T00:00:00,{date_col}.lt.{next_day_str}T00:00:00)",
                        **config.get("filter", {}),
                    }

                resp = await client.get(url, headers=_read_headers(), params=params)

                if resp.status_code == 200:
                    rows = resp.json()
                    if not rows:
                        return None
                    total = sum(float(row.get(column, 0) or 0) for row in rows)
                    return total
                return None

    except Exception as e:
        logger.error(f"Auto-fetch error for {source_key}: {e}")
        return None


async def run_auto_updates(target_date: str | None = None) -> dict:
    """Run auto-updates for all active goals with an auto_source.

    Returns:
        Summary dict with updated count and any errors
    """
    from domains.accountability.service import get_goals, log_progress

    from zoneinfo import ZoneInfo
    uk_today = datetime.now(ZoneInfo("Europe/London")).date()
    target = target_date or uk_today.isoformat()
    goals = await get_goals(status="active")
    auto_goals = [g for g in goals if g.get("auto_source")]

    updated = 0
    skipped = 0
    errors = []

    for goal in auto_goals:
        source_key = goal["auto_source"]
        try:
            value = await fetch_auto_value(source_key, target)
            if value is None:
                skipped += 1
                continue

            entry = await log_progress(
                goal_id=goal["id"],
                value=value,
                source=source_key.split("_")[0],  # e.g. "garmin", "nutrition", "weight"
                log_date=target,
            )
            if entry:
                updated += 1
                logger.info(f"Auto-updated {goal['title']}: {value} from {source_key}")
            else:
                skipped += 1
        except Exception as e:
            errors.append(f"{goal['title']}: {e}")
            logger.error(f"Auto-update error for {goal['title']}: {e}")

    return {
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "date": target,
    }
