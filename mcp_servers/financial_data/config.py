"""Configuration, env vars, date-range helpers, and constants."""

from __future__ import annotations

import calendar
import os
from datetime import date, timedelta
from typing import Final

# ---------------------------------------------------------------------------
# Supabase
# ---------------------------------------------------------------------------
SUPABASE_URL: Final[str] = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: Final[str] = os.getenv("SUPABASE_KEY", "")  # anon key (default schema)
SUPABASE_SERVICE_ROLE_KEY: Final[str] = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
HB_INVENTORY_USER_ID: Final[str] = os.getenv("HB_INVENTORY_USER_ID", "")

# Prefer service-role key (bypasses RLS) → fall back to anon key
API_KEY: Final[str] = SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY


# ---------------------------------------------------------------------------
# eBay order statuses that count as "completed sales"
# ---------------------------------------------------------------------------
EBAY_SALE_STATUSES: Final[list[str]] = ["SALE"]
BRICKLINK_SALE_STATUSES: Final[list[str]] = [
    "COMPLETED", "RECEIVED", "SHIPPED", "PACKED", "READY", "PAID",
]
BRICKOWL_SALE_STATUSES: Final[list[str]] = ["Shipped", "Received", "Completed"]


# ---------------------------------------------------------------------------
# Date-range helpers
# ---------------------------------------------------------------------------
def get_date_range(
    period: str,
    custom_start: str | None = None,
    custom_end: str | None = None,
) -> tuple[str, str]:
    """Return (start_iso, end_iso) for a named period.

    Supported periods: this_month, last_month, this_quarter, last_quarter,
    this_year, last_year, all_time, custom.
    """
    today = date.today()
    y, m = today.year, today.month

    if period == "this_month":
        start = date(y, m, 1)
        end = date(y, m, calendar.monthrange(y, m)[1])

    elif period == "last_month":
        lm = m - 1 if m > 1 else 12
        ly = y if m > 1 else y - 1
        start = date(ly, lm, 1)
        end = date(ly, lm, calendar.monthrange(ly, lm)[1])

    elif period == "this_quarter":
        qs = ((m - 1) // 3) * 3 + 1
        qe = qs + 2
        start = date(y, qs, 1)
        end = date(y, qe, calendar.monthrange(y, qe)[1])

    elif period == "last_quarter":
        cqs = ((m - 1) // 3) * 3 + 1
        lqs = cqs - 3
        ly = y
        if lqs < 1:
            lqs += 12
            ly -= 1
        lqe = lqs + 2
        start = date(ly, lqs, 1)
        end = date(ly, lqe, calendar.monthrange(ly, lqe)[1])

    elif period == "this_year":
        start = date(y, 1, 1)
        end = date(y, 12, 31)

    elif period == "last_year":
        start = date(y - 1, 1, 1)
        end = date(y - 1, 12, 31)

    elif period == "custom" and custom_start and custom_end:
        start = date.fromisoformat(custom_start)
        end = date.fromisoformat(custom_end)

    else:  # all_time
        start = date(2000, 1, 1)
        end = date(2100, 12, 31)

    return start.isoformat(), end.isoformat()


def month_range(year: int, month: int) -> tuple[str, str]:
    """Return (first_day, last_day) ISO strings for a given year/month."""
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    return start.isoformat(), end.isoformat()
