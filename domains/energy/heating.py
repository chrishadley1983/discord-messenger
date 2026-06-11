"""Heating efficiency: gas use normalised by heating degree-days.

Raw gas kWh comparisons mislead — a cold week always burns more. Dividing
by heating degree-days (HDD, base 15.5°C UK convention, from the
open-meteo archive for Tonbridge) gives kWh-per-degree-day, which should
stay roughly constant for a given house+boiler. A sustained rise means the
heating system is working harder for the same warmth (boiler efficiency,
bleeding radiators, open windows...).

Summer weeks with ~no heating demand are reported as such, not as ratios
over near-zero HDD.
"""

from __future__ import annotations

from datetime import date, timedelta

import httpx

from logger import logger
from .config import SUPABASE_KEY, SUPABASE_URL

LAT, LON = 51.195, 0.273  # Tonbridge
HDD_BASE_C = 15.5
MIN_WEEK_HDD = 12.0  # below this the heating barely ran — ratio is noise

_SB_HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def _daily_mean_temps(start: date, end: date) -> dict[str, float]:
    resp = httpx.get(
        "https://archive-api.open-meteo.com/v1/archive",
        params={
            "latitude": LAT, "longitude": LON,
            "start_date": start.isoformat(), "end_date": end.isoformat(),
            "daily": "temperature_2m_mean", "timezone": "Europe/London",
        },
        timeout=30,
    )
    resp.raise_for_status()
    daily = resp.json().get("daily", {})
    return dict(zip(daily.get("time", []), daily.get("temperature_2m_mean", [])))


def _gas_kwh_by_day(start: date, end: date) -> dict[str, float]:
    resp = httpx.get(
        f"{SUPABASE_URL}/rest/v1/energy_daily_summary",
        headers=_SB_HEADERS,
        params={
            "select": "summary_date,total_kwh",
            "fuel_type": "eq.gas",
            "summary_date": f"gte.{start.isoformat()}",
            "and": f"(summary_date.lte.{end.isoformat()})",
        },
        timeout=20,
    )
    resp.raise_for_status()
    return {r["summary_date"]: float(r["total_kwh"]) for r in resp.json()}


def _hot_water_baseline(gas: dict[str, float]) -> float:
    """Daily non-heating gas (hot water/cooking) ~= 10th percentile day.

    Without subtracting this, summer ratios are dominated by hot water
    divided by tiny HDD and read as efficiency regressions.
    """
    values = sorted(gas.values())
    if not values:
        return 0.0
    return values[max(0, len(values) // 10 - 1)] if len(values) >= 10 else values[0]


def _ratio(temps: dict[str, float], gas: dict[str, float],
           start: date, end: date, baseline_kwh: float) -> tuple[float, float, int]:
    """(heating-only gas kWh, total HDD, days with both datapoints)."""
    kwh = hdd = 0.0
    days = 0
    d = start
    while d <= end:
        key = d.isoformat()
        if key in temps and key in gas and temps[key] is not None:
            kwh += max(0.0, gas[key] - baseline_kwh)
            hdd += max(0.0, HDD_BASE_C - float(temps[key]))
            days += 1
        d += timedelta(days=1)
    return kwh, hdd, days


def weekly_line() -> str | None:
    """One digest line comparing this week's kWh/HDD to the prior 4 weeks."""
    try:
        end = date.today() - timedelta(days=2)   # official data lags
        week_start = end - timedelta(days=6)
        base_start = week_start - timedelta(days=28)

        temps = _daily_mean_temps(base_start, end)
        gas = _gas_kwh_by_day(base_start, end)

        hw_base = _hot_water_baseline(gas)
        wk_kwh, wk_hdd, wk_days = _ratio(temps, gas, week_start, end, hw_base)
        base_kwh, base_hdd, base_days = _ratio(temps, gas, base_start,
                                               week_start - timedelta(days=1), hw_base)
        if wk_days < 4:
            return None  # not enough data to say anything

        if wk_hdd < MIN_WEEK_HDD:
            return (f"🌡️ Heating: barely needed this week "
                    f"({wk_hdd:.0f} degree-days) — gas {wk_kwh:.1f} kWh is "
                    f"hot water/cooking baseline.")

        wk_ratio = wk_kwh / wk_hdd
        if base_hdd < MIN_WEEK_HDD or base_days < 14:
            return (f"🌡️ Heating: {wk_ratio:.2f} kWh per degree-day this week "
                    f"({wk_kwh:.1f} kWh over {wk_hdd:.0f} HDD) — no baseline yet.")

        base_ratio = base_kwh / base_hdd
        if base_ratio <= 0:
            return (f"🌡️ Heating: {wk_ratio:.2f} kWh per degree-day this week "
                    f"— no usable baseline yet.")
        change = (wk_ratio - base_ratio) / base_ratio * 100
        # Only alarm on weeks with real heating demand — at <20 HDD the
        # denominators are small and the % swings wildly.
        flag = (" ⚠️ worth a look (radiators/boiler/windows?)"
                if change > 20 and wk_hdd >= 20 else "")
        return (f"🌡️ Heating efficiency: {wk_ratio:.2f} kWh/degree-day vs "
                f"{base_ratio:.2f} 4-week avg ({change:+.0f}%){flag}")
    except Exception as e:
        logger.warning(f"Heating efficiency line failed: {e}")
        return None
