"""Home environment sensors (Zigbee2MQTT bridge on the dashboard Pi).

The Pi at 192.168.0.110 runs a zigbee2mqtt -> HTTP bridge on :5001 exposing
per-room sensors (temperature, humidity, occupancy, illuminance, battery,
link quality). Until now only ``domains.energy.events`` read this bridge, and
only for the lounge motion sensor's occupancy — so Peter had no route to the
temperature/humidity readings and (correctly) told Chris he couldn't see them.

This module surfaces the full sensor set to the Hadley API (``/home/sensors``)
and runs a reachability + low-battery watchdog, because the Pi has dropped off
WiFi silently before with no alert (it also hosts the pocket-money IHD
dashboard on :3000, so when it dies, both go dark).
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

import httpx

from logger import logger

# zigbee2mqtt HTTP bridge on the dashboard Pi (same box as the pocket-money
# IHD dashboard on :3000). An identifier, not a secret. domains.energy.events
# hard-codes the same root for its occupancy read.
BRIDGE_URL = os.environ.get("ZIGBEE_BRIDGE_URL", "http://192.168.0.110:5001")

HADLEY_ALERT_URL = "http://localhost:8100/alert"

# Watchdog state (single bot process owns the scheduler)
_fail_count = 0
DOWN_ALERT_AFTER = 3        # consecutive failed polls before alerting (~15 min @ 5-min cadence)
LOW_BATTERY_PCT = 15        # alert when a sensor drops below this

# Prefixes stripped from the bridge's device keys to derive a friendly room
# label, e.g. "sensor_kitchen" -> "Kitchen", "motion_lounge" -> "Lounge".
_PREFIXES = ("sensor_", "motion_", "temp_", "climate_", "th_")


def _friendly_room(key: str) -> str:
    name = key
    for p in _PREFIXES:
        if name.startswith(p):
            name = name[len(p):]
            break
    return name.replace("_", " ").strip().title() or key


def _reshape(raw: dict) -> list[dict]:
    """Bridge's {device_key: {temperature, humidity, ...}} -> friendly rows.

    Generic on purpose: any new sensor paired to the bridge shows up
    automatically with a sensible room name and only its populated fields.
    """
    out = []
    for key, v in (raw or {}).items():
        if not isinstance(v, dict):
            continue
        out.append({
            "id": key,
            "room": _friendly_room(key),
            "temperature_c": v.get("temperature"),
            "humidity_pct": v.get("humidity"),
            "occupancy": v.get("occupancy"),
            "illuminance_lux": v.get("illuminance"),
            "battery_pct": v.get("battery"),
            "link_quality": v.get("linkquality"),
        })
    # Rooms reporting a temperature first (the common question), then the rest;
    # alphabetical within each group for a stable, readable order.
    out.sort(key=lambda s: (s["temperature_c"] is None, s["room"]))
    return out


def get_sensors() -> dict:
    """Fetch and reshape the live sensor set. Raises on bridge failure."""
    resp = httpx.get(BRIDGE_URL, timeout=8)
    resp.raise_for_status()
    sensors = _reshape(resp.json())
    return {
        "sensors": sensors,
        "count": len(sensors),
        "bridge": BRIDGE_URL,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def _resolve_device(room_or_device: str) -> str:
    """Accept a device id ('sensor_bedroom') or a friendly room ('bedroom')."""
    key = (room_or_device or "").strip()
    if not key:
        return ""
    if any(key.startswith(p) for p in _PREFIXES):
        return key
    try:
        for s in get_sensors()["sensors"]:
            if s["room"].lower() == key.lower() or s["id"].lower() == key.lower():
                return s["id"]
    except Exception:
        pass
    return key


def get_history(room_or_device: str, hours: int = 24, kind: str = "readings") -> dict:
    """Time-series for one device from the bridge's /history store (~30 days).

    kind="readings" → temperature/humidity points; kind="motion" → motion events.
    """
    device = _resolve_device(room_or_device)
    resp = httpx.get(f"{BRIDGE_URL}/history",
                     params={"device": device, "hours": hours, "type": kind},
                     timeout=12)
    resp.raise_for_status()
    points = resp.json() or []
    return {
        "device": device,
        "room": _friendly_room(device) if device else None,
        "hours": hours,
        "kind": kind,
        "count": len(points),
        "points": points,
    }


def get_trend(days: int = 7) -> dict:
    """Per-room daily min/max/avg temp + humidity, with a vs-prior-day delta.

    Only rooms that report a temperature are included (the lounge motion sensor
    has no temperature history). Backed by the bridge's ~30-day /history store.
    """
    hours = max(1, days) * 24
    rooms = []
    for s in get_sensors()["sensors"]:
        if s["temperature_c"] is None:
            continue
        points = get_history(s["id"], hours=hours)["points"]
        by_day: dict[str, dict] = {}
        for p in points:
            day = (p.get("ts") or "")[:10]
            if not day:
                continue
            bucket = by_day.setdefault(day, {"temps": [], "hums": []})
            if p.get("temperature") is not None:
                bucket["temps"].append(float(p["temperature"]))
            if p.get("humidity") is not None:
                bucket["hums"].append(float(p["humidity"]))
        daily = []
        for day in sorted(by_day):
            temps = by_day[day]["temps"]
            hums = by_day[day]["hums"]
            daily.append({
                "date": day,
                "temp_min": round(min(temps), 1) if temps else None,
                "temp_max": round(max(temps), 1) if temps else None,
                "temp_avg": round(sum(temps) / len(temps), 1) if temps else None,
                "humidity_avg": round(sum(hums) / len(hums), 1) if hums else None,
                "samples": len(temps),
            })
        delta = None
        if (len(daily) >= 2 and daily[-1]["temp_avg"] is not None
                and daily[-2]["temp_avg"] is not None):
            delta = round(daily[-1]["temp_avg"] - daily[-2]["temp_avg"], 1)
        rooms.append({
            "room": s["room"],
            "id": s["id"],
            "current_c": s["temperature_c"],
            "current_humidity_pct": s["humidity_pct"],
            "daily": daily,
            "avg_change_vs_prev_day_c": delta,
        })
    return {
        "days": days,
        "rooms": rooms,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _post_alert(message: str, source: str, throttle_minutes: int) -> None:
    try:
        httpx.post(
            HADLEY_ALERT_URL,
            headers={"x-api-key": os.environ.get("HADLEY_AUTH_KEY", "")},
            json={"message": message, "source": source,
                  "throttle_minutes": throttle_minutes},
            timeout=10,
        )
    except Exception as e:
        logger.debug(f"home-sensors alert post failed: {e}")


def watchdog_once() -> dict:
    """One reachability + low-battery check (sync; callers wrap in to_thread)."""
    global _fail_count
    try:
        data = get_sensors()
    except Exception as e:
        _fail_count += 1
        # Fire exactly once on crossing the threshold; /alert throttling guards
        # against re-posting while it stays down.
        if _fail_count == DOWN_ALERT_AFTER:
            _post_alert(
                f"Home sensor bridge unreachable ({BRIDGE_URL}) for "
                f"~{DOWN_ALERT_AFTER * 5} min — temperature/humidity sensors and "
                f"the pocket-money dashboard (same Pi) are likely offline. "
                f"Check the Pi's WiFi.",
                source="home-sensors",
                throttle_minutes=120,
            )
        logger.debug(f"home-sensors watchdog fail ({_fail_count}): {e}")
        return {"ok": False, "error": str(e)[:120]}

    _fail_count = 0
    low = [s for s in data["sensors"]
           if isinstance(s["battery_pct"], (int, float)) and s["battery_pct"] < LOW_BATTERY_PCT]
    if low:
        names = ", ".join(f"{s['room']} ({s['battery_pct']}%)" for s in low)
        _post_alert(
            f"Low battery on home sensor(s): {names} — replace soon.",
            source="home-sensors-battery",
            throttle_minutes=1440,
        )
    return {"ok": True, "count": data["count"], "low_battery": len(low)}


def register_monitor(scheduler, minutes: int = 5) -> None:
    """Register the bridge reachability + low-battery watchdog as infra."""

    async def _job():
        await asyncio.to_thread(watchdog_once)

    scheduler.add_job(
        _job, "interval", minutes=minutes,
        id="home_sensors_watchdog", max_instances=1,
        coalesce=True, replace_existing=True,
    )
    logger.info(f"Home-sensors watchdog registered (every {minutes}m)")
