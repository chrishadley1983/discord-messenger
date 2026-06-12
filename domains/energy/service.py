"""Read-model helpers behind the /energy/* Hadley API endpoints.

All functions are sync (httpx) — callers wrap in asyncio.to_thread.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import httpx

from .config import SUPABASE_KEY, SUPABASE_URL

_SB_HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def _sb_get(table: str, params: dict) -> list[dict]:
    resp = httpx.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=_SB_HEADERS,
                     params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _rate_windows(hours_back: int = 72) -> list[dict]:
    """Electricity unit-rate windows covering recent days.

    energy_tariffs stores time-WINDOWED rows (each row one peak/off-peak
    window with its rate and valid_from/valid_to) — the windows themselves
    encode the tariff boundaries in real wall-clock time, so no separate
    off-peak hour logic (which was BST-shifted) is needed.
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).isoformat()
    rows = _sb_get("energy_tariffs", {
        "select": "value_inc_vat,valid_from,valid_to",
        "fuel_type": "eq.electricity",
        "rate_type": "eq.unit",
        "valid_from": f"gte.{since}",
        "order": "valid_from.asc",
        "limit": "500",
    })
    return [
        {"from": r["valid_from"], "to": r.get("valid_to"),
         "rate": float(r["value_inc_vat"])}
        for r in rows
    ]


def _rate_for(ts_iso: str, windows: list[dict]) -> float | None:
    """Rate (p/kWh) whose window contains the timestamp."""
    ts = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
    for w in windows:
        w_from = datetime.fromisoformat(w["from"].replace("Z", "+00:00"))
        w_to = (datetime.fromisoformat(w["to"].replace("Z", "+00:00"))
                if w.get("to") else None)
        if w_from <= ts and (w_to is None or ts < w_to):
            return w["rate"]
    # Rates not synced this far yet — reuse the same wall-clock window from
    # the most recent day that has one (tariff pattern repeats daily).
    for shift_h in (24, 48):
        shifted = (ts - timedelta(hours=shift_h)).isoformat()
        for w in windows:
            w_from = datetime.fromisoformat(w["from"].replace("Z", "+00:00")).isoformat()
            w_to = (datetime.fromisoformat(w["to"].replace("Z", "+00:00")).isoformat()
                    if w.get("to") else None)
            if w_from <= shifted and (w_to is None or shifted < w_to):
                return w["rate"]
    return None


def _is_offpeak_rate(rate: float | None, windows: list[dict]) -> bool:
    if rate is None or not windows:
        return False
    return rate <= min(w["rate"] for w in windows) + 0.01


def _latest_telemetry_sample() -> dict:
    """Newest raw sample from the poller's local log — no Kraken call.

    The bot's 30s poller is the single Kraken consumer; a second direct
    query from this endpoint caused KT-CT-1199 rate limiting. Reading the
    log tail gives <=40s freshness for free.
    """
    import json
    from .config import TELEMETRY_LOG
    try:
        with open(TELEMETRY_LOG, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 4096))
            lines = f.read().decode("utf-8", errors="ignore").strip().splitlines()
        for line in reversed(lines):
            try:
                s = json.loads(line)
                if s.get("readAt") and s.get("demand") is not None:
                    return s
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return {}


def live_status() -> dict:
    """Current demand from the poller's telemetry log + today from energy_live."""
    now = datetime.now(timezone.utc)
    sample = _latest_telemetry_sample()
    current = {"readAt": sample.get("readAt"), "demand": sample.get("demand")}
    # stale if the poller hasn't written for 3+ minutes
    samples = []
    if current["readAt"]:
        age = (now - datetime.fromisoformat(
            current["readAt"].replace("Z", "+00:00"))).total_seconds()
        if age < 180:
            samples = [current]

    today = today_curve()
    windows = _rate_windows()
    current_rate = _rate_for(now.isoformat(), windows)

    read_at = current.get("readAt")
    age_seconds = None
    if read_at:
        age_seconds = int((now - datetime.fromisoformat(
            read_at.replace("Z", "+00:00"))).total_seconds())

    return {
        "demand_w": float(current["demand"]) if current.get("demand") is not None else None,
        "read_at": read_at,  # UTC — present as UK local or use age_seconds
        "age_seconds": age_seconds,
        "stale": not samples,
        "today_kwh": today["total_kwh"],
        "today_cost_pounds": today["est_cost_pounds"],
        "current_rate_p_per_kwh": current_rate,
        "offpeak_now": _is_offpeak_rate(current_rate, windows),
    }


def today_curve() -> dict:
    """Today's 1-minute curve + totals from energy_live, cost-estimated."""
    day_start = datetime.now(timezone.utc).astimezone().replace(
        hour=0, minute=0, second=0, microsecond=0)
    rows = _sb_get("energy_live", {
        "select": "minute_start,demand_w_avg,demand_w_max,consumption_wh",
        "minute_start": f"gte.{day_start.isoformat()}",
        "order": "minute_start.asc",
        "limit": "1500",
    })
    total_wh = sum(float(r.get("consumption_wh") or 0) for r in rows)
    windows = _rate_windows()
    fallback = max((w["rate"] for w in windows), default=27.0)
    cost = 0.0
    for r in rows:
        rate = _rate_for(r["minute_start"], windows)
        cost += float(r.get("consumption_wh") or 0) / 1000 * (rate if rate is not None else fallback)

    return {
        "date": day_start.date().isoformat(),
        "minutes": len(rows),
        "total_kwh": round(total_wh / 1000, 2),
        "est_cost_pounds": round(cost / 100, 2),
        "peak_demand_w": max((float(r["demand_w_max"] or 0) for r in rows), default=0),
        "curve": [
            {"t": r["minute_start"], "w": r["demand_w_avg"]}
            for r in rows
        ],
    }


def recent_summary(days: int = 7) -> list[dict]:
    """Recent complete daily summaries, plus a PROVISIONAL electricity row
    for any trailing day the official feed hasn't published yet.

    The official half-hourly feed lags 1-2 days; provisional rows are
    synthesised at read time from Home Mini minute data (never written to
    the table) and flagged "provisional": true so consumers can label them.
    The official sync replaces them in responses automatically once it
    catches up. Electricity only — the Mini telemetry doesn't cover gas.
    """
    since = (date.today() - timedelta(days=days)).isoformat()
    rows = _sb_get("energy_daily_summary", {
        "select": "summary_date,fuel_type,total_kwh,peak_kwh,offpeak_kwh,"
                  "total_cost_pence,standing_charge_pence,is_ev_charge_day",
        "summary_date": f"gte.{since}",
        "order": "summary_date.desc",
    })
    for r in rows:
        r["provisional"] = False

    # Official rows include the daily standing charge; provisional rows must
    # too or mixed aggregations under-count ~60p/day. Borrow the most recent
    # official electricity value.
    standing = next(
        (float(r.get("standing_charge_pence") or 0) for r in rows
         if r["fuel_type"] == "electricity"), 60.0)

    have_elec = {r["summary_date"] for r in rows if r["fuel_type"] == "electricity"}
    windows = _rate_windows(hours_back=24 * (days + 1))
    fallback = max((w["rate"] for w in windows), default=27.0)

    provisional = []
    for back in range(1, min(days, 3) + 1):
        day = date.today() - timedelta(days=back)
        if day.isoformat() in have_elec:
            continue
        day_start = datetime.combine(day, datetime.min.time()).astimezone()
        day_end = day_start + timedelta(days=1)
        mins = _sb_get("energy_live", {
            "select": "minute_start,consumption_wh",
            "minute_start": f"gte.{day_start.isoformat()}",
            "and": f"(minute_start.lt.{day_end.isoformat()})",
            "limit": "1500",
        })
        # Only synthesise when telemetry covers most of the day — a few
        # hours of minutes would masquerade as a tiny full day.
        if len(mins) < 1200:
            continue
        kwh = sum(float(m.get("consumption_wh") or 0) for m in mins) / 1000
        cost = sum(
            float(m.get("consumption_wh") or 0) / 1000
            * (_rate_for(m["minute_start"], windows) or fallback)
            for m in mins
        )
        provisional.append({
            "summary_date": day.isoformat(),
            "fuel_type": "electricity",
            "total_kwh": round(kwh, 2),
            "peak_kwh": None,
            "offpeak_kwh": None,
            "total_cost_pence": round(cost + standing, 1),
            "standing_charge_pence": round(standing, 1),
            "is_ev_charge_day": None,
            "provisional": True,
        })

    return sorted(provisional + rows, key=lambda r: r["summary_date"], reverse=True)
