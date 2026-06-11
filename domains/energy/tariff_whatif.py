"""Monthly tariff what-if: replay actual usage under Octopus Agile.

Answers "would Agile beat Intelligent Go for our usage shape?" with real
data: last month's actual half-hourly electricity consumption is costed
under (a) what we actually paid (energy_daily_summary) and (b) Agile's
half-hourly rates for the same region/period. Posted to #energy by the
monthly billing job; callable on demand.

Caveats stated in the output: standing charges differ slightly between
products, and Intelligent Go's cheap EV dispatch slots only exist BECAUSE
of that tariff — on Agile the same charging would float to Agile's cheap
overnight prices, which the replay captures naturally.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

UK = ZoneInfo("Europe/London")

import httpx

from logger import logger
from .config import (
    DISCORD_ENERGY_WEBHOOK,
    OCTOPUS_API_KEY,
    OCTOPUS_REST_BASE,
    SUPABASE_KEY,
    SUPABASE_URL,
)

AGILE_PRODUCT = "AGILE-24-10-01"
AGILE_TARIFF = f"E-1R-{AGILE_PRODUCT}-J"  # region J (South East)

_SB_HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def _month_bounds(target: date | None = None) -> tuple[date, date]:
    """Previous complete calendar month (start, exclusive end)."""
    today = target or date.today()
    first_this = today.replace(day=1)
    last_month_end = first_this
    last_month_start = (first_this - timedelta(days=1)).replace(day=1)
    return last_month_start, last_month_end


def _fetch_agile_rates(start: date, end: date) -> dict[str, float]:
    """Agile unit rates keyed by interval-start ISO (UTC)."""
    rates: dict[str, float] = {}
    url = (f"{OCTOPUS_REST_BASE}/products/{AGILE_PRODUCT}/electricity-tariffs/"
           f"{AGILE_TARIFF}/standard-unit-rates/")
    params = {
        "period_from": f"{start.isoformat()}T00:00Z",
        "period_to": f"{end.isoformat()}T00:00Z",
        "page_size": "1500",
    }
    auth = (OCTOPUS_API_KEY, "")
    while url:
        resp = httpx.get(url, params=params, auth=auth, timeout=30)
        resp.raise_for_status()
        body = resp.json()
        for r in body.get("results", []):
            rates[r["valid_from"]] = float(r["value_inc_vat"])
        url = body.get("next")
        params = None  # next URL already carries the query
    return rates


def _fetch_consumption_utc(start: datetime, end: datetime) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        resp = httpx.get(
            f"{SUPABASE_URL}/rest/v1/energy_consumption",
            headers=_SB_HEADERS,
            params={
                "select": "interval_start,consumption_kwh",
                "fuel_type": "eq.electricity",
                "interval_start": f"gte.{start.isoformat()}",
                "and": f"(interval_start.lt.{end.isoformat()})",
                "order": "interval_start.asc",
                "limit": "1000",
                "offset": str(offset),
            },
            timeout=30,
        )
        resp.raise_for_status()
        batch = resp.json()
        rows.extend(batch)
        if len(batch) < 1000:
            return rows
        offset += 1000


def _actual_cost_pence(start: date, end: date) -> float:
    resp = httpx.get(
        f"{SUPABASE_URL}/rest/v1/energy_daily_summary",
        headers=_SB_HEADERS,
        params={
            "select": "cost_pence",
            "fuel_type": "eq.electricity",
            "summary_date": f"gte.{start.isoformat()}",
            "and": f"(summary_date.lt.{end.isoformat()})",
        },
        timeout=20,
    )
    resp.raise_for_status()
    return sum(float(r["cost_pence"]) for r in resp.json())


def compare_last_month() -> dict:
    """Replay last month's usage under Agile; return the comparison."""
    start, end = _month_bounds()
    # Use LOCAL month boundaries as UTC instants — the actual-cost summaries
    # are local-dated, and during BST a naive UTC month window shifts 1h of
    # EV off-peak charging in/out of the comparison.
    start_utc = datetime(start.year, start.month, start.day, tzinfo=UK).astimezone(timezone.utc)
    end_utc = datetime(end.year, end.month, end.day, tzinfo=UK).astimezone(timezone.utc)
    consumption = _fetch_consumption_utc(start_utc, end_utc)
    if not consumption:
        return {"error": f"no consumption data for {start} - {end}"}

    agile = _fetch_agile_rates(start, end)
    matched = unmatched = 0
    agile_cost = 0.0
    for c in consumption:
        # normalise interval_start to the UTC key format Agile rates use
        ts = datetime.fromisoformat(c["interval_start"].replace("Z", "+00:00"))
        k = ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rate = agile.get(k)
        if rate is None:
            unmatched += 1
            continue
        matched += 1
        agile_cost += float(c["consumption_kwh"]) * rate

    if matched and unmatched / (matched + unmatched) > 0.05:
        return {"error": f"only {matched}/{matched + unmatched} intervals had Agile "
                         f"rates — comparison would be misleading, skipping"}

    actual_cost = _actual_cost_pence(start, end)
    total_kwh = sum(float(c["consumption_kwh"]) for c in consumption)

    return {
        "month": start.strftime("%B %Y"),
        "total_kwh": round(total_kwh, 1),
        "actual_unit_cost_pounds": round(actual_cost / 100, 2),
        "agile_unit_cost_pounds": round(agile_cost / 100, 2),
        "delta_pounds": round((agile_cost - actual_cost) / 100, 2),
        "intervals": len(consumption),
        "matched": matched,
        "unmatched": unmatched,
    }


def post_comparison() -> dict:
    """Run the comparison and post to #energy. Returns the result."""
    result = compare_last_month()
    if "error" in result:
        logger.warning(f"Tariff what-if: {result['error']}")
        return result

    delta = result["delta_pounds"]
    verdict = (
        f"Agile would have cost **£{abs(delta):.2f} {'more' if delta > 0 else 'less'}**"
        if abs(delta) >= 0.5 else "Effectively a dead heat"
    )
    msg = (
        f"**Tariff What-If — {result['month']}** (unit costs, excl. standing charge)\n"
        f"Usage: {result['total_kwh']} kWh\n"
        f"Intelligent Go (actual): £{result['actual_unit_cost_pounds']:.2f}\n"
        f"Agile (replayed): £{result['agile_unit_cost_pounds']:.2f}\n"
        f"{verdict} on your actual usage shape.\n"
        f"-# Note: EV dispatch slots exist because of Intelligent Go; on Agile the same "
        f"charging would float to cheap overnight slots, which this replay prices at "
        f"Agile's real half-hourly rates. {result['unmatched']} of {result['intervals']} "
        f"intervals had no Agile rate published."
    )
    if DISCORD_ENERGY_WEBHOOK:
        try:
            httpx.post(DISCORD_ENERGY_WEBHOOK, json={"content": msg}, timeout=15)
        except Exception as e:
            logger.warning(f"Tariff what-if webhook post failed: {e}")
    return result
