"""
Octopus Energy daily sync: pulls half-hourly consumption data,
calculates costs using tariff rates, and stores daily summaries.

Run daily ~10AM (data available next morning).
First run backfills 90 days of history.
"""
import json
import os
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

import httpx
from supabase import create_client

from .config import (
    COMPLETE_DAY_INTERVALS,
    SUPABASE_URL, SUPABASE_KEY,
    OCTOPUS_API_KEY, OCTOPUS_REST_BASE, OCTOPUS_GRAPHQL_URL,
    ELECTRICITY_MPAN, ELECTRICITY_SERIAL,
    GAS_MPRN, GAS_SERIAL,
    ELECTRICITY_PRODUCT, ELECTRICITY_TARIFF,
    GAS_PRODUCT, GAS_TARIFF,
    OFFPEAK_START_HOUR, OFFPEAK_START_MIN,
    OFFPEAK_END_HOUR, OFFPEAK_END_MIN,
    GAS_M3_TO_KWH, EV_OFFPEAK_THRESHOLD_KWH,
    DISCORD_ENERGY_WEBHOOK,
)


def fetch_consumption(fuel: str, period_from: str, period_to: str) -> list[dict]:
    """Fetch half-hourly consumption from REST API."""
    if fuel == "electricity":
        url = f"{OCTOPUS_REST_BASE}/electricity-meter-points/{ELECTRICITY_MPAN}/meters/{ELECTRICITY_SERIAL}/consumption/"
    else:
        url = f"{OCTOPUS_REST_BASE}/gas-meter-points/{GAS_MPRN}/meters/{GAS_SERIAL}/consumption/"

    all_results = []
    params = {
        "period_from": period_from,
        "period_to": period_to,
        "order_by": "period",
        "page_size": 25000,
    }

    resp = httpx.get(url, auth=(OCTOPUS_API_KEY, ""), params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    all_results.extend(data.get("results", []))

    # Handle pagination (unlikely with page_size=25000 but be safe)
    while data.get("next"):
        resp = httpx.get(data["next"], auth=(OCTOPUS_API_KEY, ""), timeout=60)
        resp.raise_for_status()
        data = resp.json()
        all_results.extend(data.get("results", []))

    return all_results


def fetch_tariff_rates(fuel: str, rate_type: str, period_from: str, period_to: str) -> list[dict]:
    """Fetch tariff rates from REST API."""
    if fuel == "electricity":
        url = f"{OCTOPUS_REST_BASE}/products/{ELECTRICITY_PRODUCT}/electricity-tariffs/{ELECTRICITY_TARIFF}/{rate_type}/"
    else:
        url = f"{OCTOPUS_REST_BASE}/products/{GAS_PRODUCT}/gas-tariffs/{GAS_TARIFF}/{rate_type}/"

    all_results = []
    params = {
        "period_from": period_from,
        "period_to": period_to,
        "page_size": 1500,
    }

    resp = httpx.get(url, auth=(OCTOPUS_API_KEY, ""), params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    all_results.extend(data.get("results", []))

    while data.get("next"):
        resp = httpx.get(data["next"], auth=(OCTOPUS_API_KEY, ""), timeout=60)
        resp.raise_for_status()
        data = resp.json()
        all_results.extend(data.get("results", []))

    return all_results


def fetch_standing_charges(fuel: str) -> list[dict]:
    """Fetch current standing charges."""
    if fuel == "electricity":
        url = f"{OCTOPUS_REST_BASE}/products/{ELECTRICITY_PRODUCT}/electricity-tariffs/{ELECTRICITY_TARIFF}/standing-charges/"
    else:
        url = f"{OCTOPUS_REST_BASE}/products/{GAS_PRODUCT}/gas-tariffs/{GAS_TARIFF}/standing-charges/"

    resp = httpx.get(url, auth=(OCTOPUS_API_KEY, ""), params={"page_size": 5}, timeout=30)
    resp.raise_for_status()
    return resp.json().get("results", [])


def is_offpeak(interval_start_iso: str) -> bool:
    """Check if a half-hour interval falls in the fixed Intelligent Go off-peak
    window (23:30-05:30 local time).

    Octopus returns consumption timestamps with a local offset, so ``dt.hour``
    is the local wall-clock hour — this matches the local cheap window directly.
    """
    dt = datetime.fromisoformat(interval_start_iso.replace("Z", "+00:00"))
    h, m = dt.hour, dt.minute
    # Off-peak: 23:30 to 05:30 local
    if h > OFFPEAK_START_HOUR or (h == OFFPEAK_START_HOUR and m >= OFFPEAK_START_MIN):
        return True
    if h < OFFPEAK_END_HOUR or (h == OFFPEAK_END_HOUR and m < OFFPEAK_END_MIN):
        return True
    return False


def is_offpeak_interval(interval_start_iso: str, dispatches: dict | None = None) -> bool:
    """Off-peak if inside the fixed Intelligent Go window OR an Octopus EV
    dispatch slot.

    Intelligent Octopus Go "bump charges" the car outside 23:30-05:30 (e.g. a
    cheap daytime slot it dispatches) and still bills those half-hours at the
    off-peak rate. A clock-only check therefore misattributes daytime EV
    charging as peak — the cause of "EV (peak: 22.4, off-peak: 5.1)" on a day
    the car actually charged cheaply during the day.
    """
    if is_offpeak(interval_start_iso):
        return True
    if dispatches:
        from .dispatches import in_dispatch_window
        dt = datetime.fromisoformat(interval_start_iso.replace("Z", "+00:00"))
        if in_dispatch_window(dt, dispatches):
            return True
    return False


def get_rate_for_interval(interval_start_iso: str, rates: list[dict], fuel: str) -> float:
    """Find the applicable rate (inc VAT, pence/kWh) for a given interval."""
    dt = datetime.fromisoformat(interval_start_iso.replace("Z", "+00:00"))

    for rate in rates:
        valid_from = datetime.fromisoformat(rate["valid_from"].replace("Z", "+00:00"))
        valid_to = rate.get("valid_to")
        if valid_to:
            valid_to = datetime.fromisoformat(valid_to.replace("Z", "+00:00"))
            if valid_from <= dt < valid_to:
                return rate["value_inc_vat"]
        elif valid_from <= dt:
            return rate["value_inc_vat"]

    # Fallback: return most recent rate
    if rates:
        return rates[0]["value_inc_vat"]
    return 0.0


def get_standing_charge_for_date(d: date, charges: list[dict]) -> float:
    """Find applicable standing charge (inc VAT, pence/day) for a date."""
    dt = datetime.combine(d, datetime.min.time()).replace(
        tzinfo=__import__("datetime").timezone.utc
    )
    for charge in charges:
        valid_from = datetime.fromisoformat(charge["valid_from"].replace("Z", "+00:00"))
        valid_to = charge.get("valid_to")
        if valid_to:
            valid_to = datetime.fromisoformat(valid_to.replace("Z", "+00:00"))
            if valid_from <= dt < valid_to:
                return charge["value_inc_vat"]
        elif valid_from <= dt:
            return charge["value_inc_vat"]
    if charges:
        return charges[0]["value_inc_vat"]
    return 0.0


def store_consumption(sb, readings: list[dict], fuel: str):
    """Store half-hourly readings in energy_consumption table."""
    if not readings:
        return 0

    rows = []
    for r in readings:
        kwh = r["consumption"]
        raw = None
        if fuel == "gas":
            raw = kwh  # Store original m³ value
            kwh = kwh * GAS_M3_TO_KWH  # Convert to kWh

        rows.append({
            "fuel_type": fuel,
            "interval_start": r["interval_start"],
            "interval_end": r["interval_end"],
            "consumption_kwh": round(kwh, 4),
            "consumption_raw": round(raw, 4) if raw is not None else None,
        })

    # Upsert in batches of 500
    stored = 0
    for i in range(0, len(rows), 500):
        batch = rows[i:i + 500]
        sb.table("energy_consumption").upsert(
            batch, on_conflict="fuel_type,interval_start"
        ).execute()
        stored += len(batch)

    return stored


def store_tariff_rates(sb, rates: list[dict], fuel: str, rate_type: str, product_code: str, tariff_code: str):
    """Store tariff rates in energy_tariffs table.

    Gas rates come in DD and non-DD variants with the same valid_from.
    We prefer DIRECT_DEBIT rates and deduplicate by valid_from.
    """
    # Deduplicate: prefer DIRECT_DEBIT, then first seen
    seen = {}
    for r in rates:
        key = r["valid_from"]
        method = r.get("payment_method", "")
        if key not in seen or method == "DIRECT_DEBIT":
            seen[key] = r

    rows = []
    for r in seen.values():
        rows.append({
            "fuel_type": fuel,
            "rate_type": rate_type,
            "value_inc_vat": r["value_inc_vat"],
            "valid_from": r["valid_from"],
            "valid_to": r.get("valid_to"),
            "product_code": product_code,
            "tariff_code": tariff_code,
        })

    if rows:
        sb.table("energy_tariffs").upsert(
            rows, on_conflict="fuel_type,rate_type,valid_from"
        ).execute()

    return len(rows)


def calculate_daily_summary(
    readings: list[dict], fuel: str, rates: list[dict], standing_charge_pence: float,
    dispatches: dict | None = None,
) -> dict:
    """Calculate daily summary from half-hourly readings.

    ``dispatches`` (Octopus planned/completed EV charge slots) lets off-peak
    attribution count daytime smart-charge slots correctly; without it, the
    classification falls back to the fixed clock window only.
    """
    total_kwh = 0.0
    peak_kwh = 0.0
    offpeak_kwh = 0.0
    cost_pence = 0.0

    # Intelligent Go bills dispatched daytime EV slots at the off-peak unit
    # rate, but the published rate schedule only encodes the fixed 23:30-05:30
    # window. So for any slot we classify as off-peak (clock OR dispatch) we
    # cost the cheapest unit rate of the day. For clock-window slots this is a
    # no-op (they already resolve to the cheap rate); it corrects daytime
    # dispatch slots that would otherwise be billed at the peak rate, keeping
    # the £ consistent with the off-peak kWh split.
    offpeak_rate = None
    if fuel == "electricity" and rates:
        offpeak_rate = min(
            (rt["value_inc_vat"] for rt in rates if rt.get("value_inc_vat") is not None),
            default=None,
        )

    for r in readings:
        kwh = r["consumption"]
        if fuel == "gas":
            kwh *= GAS_M3_TO_KWH

        total_kwh += kwh
        rate = get_rate_for_interval(r["interval_start"], rates, fuel)

        if fuel == "electricity":
            if is_offpeak_interval(r["interval_start"], dispatches):
                offpeak_kwh += kwh
                if offpeak_rate is not None:
                    rate = offpeak_rate
            else:
                peak_kwh += kwh

        cost_pence += kwh * rate

    is_ev = fuel == "electricity" and offpeak_kwh > EV_OFFPEAK_THRESHOLD_KWH

    return {
        "total_kwh": round(total_kwh, 4),
        "peak_kwh": round(peak_kwh, 4) if fuel == "electricity" else 0,
        "offpeak_kwh": round(offpeak_kwh, 4) if fuel == "electricity" else 0,
        "cost_pence": round(cost_pence, 2),
        "standing_charge_pence": round(standing_charge_pence, 2),
        "total_cost_pence": round(cost_pence + standing_charge_pence, 2),
        "is_ev_charge_day": is_ev,
    }


def store_daily_summaries(sb, summaries: dict[str, dict], fuel: str):
    """Store daily summaries in energy_daily_summary table."""
    rows = []
    for day_str, summary in summaries.items():
        rows.append({
            "summary_date": day_str,
            "fuel_type": fuel,
            "total_kwh": summary["total_kwh"],
            "peak_kwh": summary["peak_kwh"],
            "offpeak_kwh": summary["offpeak_kwh"],
            "cost_pence": summary["cost_pence"],
            "standing_charge_pence": summary["standing_charge_pence"],
            "total_cost_pence": summary["total_cost_pence"],
            "is_ev_charge_day": summary["is_ev_charge_day"],
            "updated_at": datetime.now(tz=__import__("datetime").timezone.utc).isoformat(),
        })

    if rows:
        sb.table("energy_daily_summary").upsert(
            rows, on_conflict="summary_date,fuel_type"
        ).execute()

    return len(rows)


def store_dispatches(sb, dispatches: list[dict]) -> int:
    """Persist completed EV dispatch slots (best-effort).

    completedDispatches age out of the Octopus API within a day or two, so
    storing them builds a durable record for auditing the off-peak split and
    reclassifying days later. Never raises — a missing table or insert error
    just means no audit row, not a failed sync.
    """
    # Dedup by start_at within the batch (keep last): Octopus can return the
    # same slot twice, and Postgres rejects an upsert that touches one
    # conflict target row more than once in a single command.
    by_start: dict[str, dict] = {}
    for d in dispatches:
        if not d.get("start") or not d.get("end"):
            continue
        by_start[d["start"]] = {
            "start_at": d["start"],
            "end_at": d["end"],
            "kwh": d.get("kwh") or 0,
            "source": d.get("source"),
        }
    rows = list(by_start.values())
    if not rows:
        return 0
    try:
        sb.table("energy_dispatches").upsert(rows, on_conflict="start_at").execute()
        return len(rows)
    except Exception as e:
        print(f"    dispatch store skipped ({e})")
        return 0


def get_last_sync_date(sb, fuel: str) -> date | None:
    """Get the most recent date we have consumption data for."""
    result = (
        sb.table("energy_daily_summary")
        .select("summary_date")
        .eq("fuel_type", fuel)
        .order("summary_date", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return date.fromisoformat(result.data[0]["summary_date"])
    return None


def check_spike_alerts(sb, summaries: dict) -> list[str]:
    """Check if yesterday's usage was anomalously high vs 30-day average.

    For electricity, EV charge days are excluded from the average baseline
    and only non-EV days trigger spike alerts.
    """
    alerts = []

    for fuel, latest in summaries.items():
        # Get 30-day history
        thirty_days_ago = (date.today() - timedelta(days=31)).isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        history = (
            sb.table("energy_daily_summary")
            .select("total_kwh, is_ev_charge_day")
            .eq("fuel_type", fuel)
            .gte("summary_date", thirty_days_ago)
            .lt("summary_date", yesterday)
            .execute()
        )

        if len(history.data) < 7:
            continue  # Not enough history

        if fuel == "electricity" and not latest.get("is_ev_charge_day"):
            # Compare non-EV days only
            non_ev = [r["total_kwh"] for r in history.data if not r["is_ev_charge_day"]]
            if not non_ev:
                continue
            avg = sum(non_ev) / len(non_ev)
        else:
            vals = [r["total_kwh"] for r in history.data]
            avg = sum(vals) / len(vals)

        if fuel == "electricity" and latest.get("is_ev_charge_day"):
            continue  # Don't alert on EV charge days

        if avg > 0 and latest["total_kwh"] > avg * 2:
            emoji = "\u26a1" if fuel == "electricity" else "\U0001f525"
            alerts.append(
                f"\u26a0\ufe0f **{fuel.title()} Spike** {emoji}\n"
                f"Yesterday: {latest['total_kwh']:.1f} kWh vs 30-day avg: {avg:.1f} kWh "
                f"(**{latest['total_kwh'] / avg:.1f}x** normal)"
            )

    return alerts


def get_monthly_prediction(sb) -> str | None:
    """Calculate month-to-date spend and project full month cost."""
    today = date.today()
    first_of_month = today.replace(day=1)
    days_elapsed = (today - first_of_month).days
    if days_elapsed < 3:
        return None  # Too early in month

    days_in_month = (first_of_month.replace(month=first_of_month.month % 12 + 1, day=1) - timedelta(days=1)).day if first_of_month.month < 12 else 31

    # Get MTD totals
    mtd = (
        sb.table("energy_daily_summary")
        .select("fuel_type, total_cost_pence")
        .gte("summary_date", first_of_month.isoformat())
        .execute()
    )

    if not mtd.data:
        return None

    mtd_total = sum(r["total_cost_pence"] for r in mtd.data)
    projected = mtd_total * (days_in_month / days_elapsed)

    # Get last month's total
    last_month_start = (first_of_month - timedelta(days=1)).replace(day=1)
    last_month = (
        sb.table("energy_daily_summary")
        .select("total_cost_pence")
        .gte("summary_date", last_month_start.isoformat())
        .lt("summary_date", first_of_month.isoformat())
        .execute()
    )
    last_month_total = sum(r["total_cost_pence"] for r in last_month.data) if last_month.data else None

    mtd_gbp = mtd_total / 100
    proj_gbp = projected / 100
    line = f"\U0001f4c8 **Month Projection**: \u00a3{mtd_gbp:.2f} spent so far ({days_elapsed} days) \u2192 tracking to **\u00a3{proj_gbp:.0f}**"

    if last_month_total:
        lm_gbp = last_month_total / 100
        diff = proj_gbp - lm_gbp
        pct = (diff / lm_gbp) * 100 if lm_gbp > 0 else 0
        arrow = "\u2b06\ufe0f" if diff > 0 else "\u2b07\ufe0f"
        line += f" (last month: \u00a3{lm_gbp:.0f}, {arrow} {abs(pct):.0f}%)"

    return line


def post_discord_summary(sb, summaries: dict):
    """Post daily sync summary to Discord #energy channel."""
    lines = [f"**Energy Update** \u2014 {date.today().strftime('%a %d %b')}\n"]

    for fuel in ["electricity", "gas"]:
        if fuel not in summaries:
            continue
        s = summaries[fuel]
        cost_gbp = s["total_cost_pence"] / 100
        emoji = "\u26a1" if fuel == "electricity" else "\U0001f525"
        line = f"{emoji} **{fuel.title()}**: {s['total_kwh']:.1f} kWh = **\u00a3{cost_gbp:.2f}**"
        if fuel == "electricity" and s.get("is_ev_charge_day"):
            line += " \U0001f50c EV"
        if fuel == "electricity" and s.get("offpeak_kwh", 0) > 0:
            line += f" (peak: {s['peak_kwh']:.1f}, off-peak: {s['offpeak_kwh']:.1f})"
        lines.append(line)

    # Monthly prediction
    prediction = get_monthly_prediction(sb)
    if prediction:
        lines.append("")
        lines.append(prediction)

    # Spike alerts
    alerts = check_spike_alerts(sb, summaries)
    if alerts:
        lines.append("")
        lines.extend(alerts)

    message = "\n".join(lines)

    try:
        httpx.post(DISCORD_ENERGY_WEBHOOK, json={"content": message}, timeout=10)
    except Exception as e:
        print(f"Discord webhook error: {e}")


def sync_fuel(sb, fuel: str, from_date: date, to_date: date):
    """Sync consumption and calculate daily summaries for a fuel type."""
    # Fetch from a day earlier than requested: Octopus returns local-offset
    # timestamps and days are grouped by LOCAL date, so during BST a
    # period_from of T00:00Z clips the first local hour of from_date —
    # producing a 46-interval "complete" day that overwrote correct
    # summaries (caught by the Jun 2026 validation review).
    period_from = f"{(from_date - timedelta(days=1)).isoformat()}T00:00Z"
    period_to = f"{to_date.isoformat()}T00:00Z"

    print(f"\n  [{fuel.upper()}] Fetching {from_date} to {to_date}...")

    # Fetch consumption
    readings = fetch_consumption(fuel, period_from, period_to)
    print(f"    {len(readings)} half-hourly readings")

    if not readings:
        print("    No data available yet")
        return None

    # Store raw readings
    stored = store_consumption(sb, readings, fuel)
    print(f"    Stored {stored} readings")

    # Fetch tariff rates
    rates = fetch_tariff_rates(fuel, "standard-unit-rates", period_from, period_to)
    print(f"    {len(rates)} tariff rate periods")

    # Store tariff rates
    store_tariff_rates(
        sb, rates, fuel, "unit",
        ELECTRICITY_PRODUCT if fuel == "electricity" else GAS_PRODUCT,
        ELECTRICITY_TARIFF if fuel == "electricity" else GAS_TARIFF,
    )

    # Fetch standing charges
    standing_charges = fetch_standing_charges(fuel)

    # Fetch Octopus EV dispatch slots — ground truth for off-peak attribution.
    # Intelligent Go dispatches the car outside 23:30-05:30 and bills those
    # slots at the off-peak rate, so a clock-only split misattributes daytime
    # charging as peak. completedDispatches only covers the last day or two, so
    # this corrects the most-recent days the incremental sync re-summarises;
    # older backfill days fall back to the fixed clock window. Best-effort —
    # a dispatch fetch/store failure must never block the consumption sync.
    dispatches = None
    if fuel == "electricity":
        try:
            from .dispatches import get_dispatches
            dispatches = get_dispatches()
            completed = dispatches.get("completed", [])
            print(f"    {len(completed)} completed dispatch slot(s)")
            stored_d = store_dispatches(sb, completed)
            if stored_d:
                print(f"    Stored {stored_d} dispatch slot(s)")
        except Exception as e:
            print(f"    dispatch fetch failed ({e}) — clock-only off-peak split")
            dispatches = None

    # Group readings by day and calculate summaries
    by_day: dict[str, list] = {}
    for r in readings:
        day = r["interval_start"][:10]
        by_day.setdefault(day, []).append(r)

    # The EARLIEST local day in any fetch window is potentially clipped at
    # its start (Octopus groups by local date but period_from is UTC), so it
    # must never be (re)summarised — round 2 of the validation review showed
    # the previous fix just moved the clip-corruption one day earlier.
    sacrificial = (from_date - timedelta(days=1)).isoformat()
    if by_day and min(by_day) <= sacrificial:
        del by_day[min(by_day)]

    daily_summaries = {}
    skipped_partial = 0
    for day_str, day_readings in sorted(by_day.items()):
        # Only finalise complete days — a partial day (data still arriving)
        # summarised as if real produced the "0.5 kWh" dashboard garbage of
        # Jun 2026. Incomplete days are picked up on a later sync because
        # get_last_sync_date then stays at the last complete day.
        if len(day_readings) < COMPLETE_DAY_INTERVALS:
            skipped_partial += 1
            continue
        d = date.fromisoformat(day_str)
        sc = get_standing_charge_for_date(d, standing_charges)
        summary = calculate_daily_summary(day_readings, fuel, rates, sc, dispatches)
        daily_summaries[day_str] = summary
    if skipped_partial:
        print(f"    Skipped {skipped_partial} incomplete day(s) (awaiting full data)")

    # Store daily summaries
    stored_days = store_daily_summaries(sb, daily_summaries, fuel)
    print(f"    {stored_days} daily summaries")

    # Return most recent day's summary for Discord
    if daily_summaries:
        latest_day = max(daily_summaries.keys())
        return daily_summaries[latest_day]
    return None


def main():
    if not SUPABASE_KEY:
        print("ERROR: SUPABASE_SERVICE_ROLE_KEY not found")
        sys.exit(1)

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    today = date.today()

    print(f"Octopus Energy Sync - {today}")

    # Determine sync range per fuel
    latest_summaries = {}
    for fuel in ["electricity", "gas"]:
        last_sync = get_last_sync_date(sb, fuel)
        if last_sync:
            # Sync from last known date (re-sync last day in case of late data)
            from_date = last_sync
        else:
            # First run: backfill 90 days
            from_date = today - timedelta(days=90)
            print(f"  [{fuel.upper()}] First run - backfilling from {from_date}")

        # Data typically available up to yesterday
        to_date = today

        summary = sync_fuel(sb, fuel, from_date, to_date)
        if summary:
            latest_summaries[fuel] = summary

    # Post to Discord (only latest day's data)
    if latest_summaries:
        post_discord_summary(sb, latest_summaries)
        print("\nPosted summary to Discord #energy")

    print("\nDone.")


if __name__ == "__main__":
    main()
