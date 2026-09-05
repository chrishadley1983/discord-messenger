"""Garmin activities → Supabase + cardio-log linking (Phase 2).

Pure matching logic lives at the top (testable without I/O); the async
functions below do the sync:

- ``sync_garmin_activities(days)`` pulls recent activities via garth and
  upserts ``garmin_activities``.
- ``link_and_backfill(days)`` links Peter-logged cardio sessions to the
  matching Garmin activity (same date, compatible modality) and copies HR /
  calories across; then creates ``source='garmin'`` cardio rows for
  watch-recorded activities nobody logged (so a recorded walk counts toward
  the 5 easy sessions). Strength activities link to the workout session of
  the same day.

Idempotent — safe to run every morning and on demand.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Garmin type_key -> our cardio modality. Anything not listed is ignored for
# cardio purposes (strength_training is handled separately).
GARMIN_TYPE_TO_MODALITY: dict[str, str] = {
    "stair_climbing": "stairmaster", "stair_stepper": "stairmaster", "indoor_climbing": "stairmaster",
    "indoor_cycling": "bike", "cycling": "bike", "virtual_ride": "bike", "road_biking": "bike",
    "treadmill_running": "treadmill", "indoor_running": "treadmill",
    "walking": "walk", "indoor_walking": "walk", "hiking": "walk", "casual_walking": "walk", "speed_walking": "walk",
    "running": "run", "trail_running": "run",
    "indoor_rowing": "rower", "rowing": "rower",
    "elliptical": "elliptical",
    "indoor_cardio": "other", "cardio": "other", "fitness_equipment": "other",
}
STRENGTH_TYPES = {"strength_training", "indoor_strength", "weight_training"}

# Modalities that are interchangeable when matching a log to an activity.
_COMPATIBLE = {
    "stairmaster": {"stairmaster", "other"},
    "bike": {"bike", "other"},
    "treadmill": {"treadmill", "walk", "run", "other"},
    "walk": {"walk", "treadmill", "other"},
    "rower": {"rower", "other"},
    "elliptical": {"elliptical", "other"},
    "other": {"other", "stairmaster", "bike", "treadmill", "walk", "rower", "elliptical"},
}

MIN_AUTO_CARDIO_MIN = 15   # don't auto-create cardio rows for tiny recorded activities


def activity_to_row(a: Any) -> dict | None:
    """garth Activity -> garmin_activities row."""
    try:
        st = a.start_time_local
        if isinstance(st, str):
            st = datetime.fromisoformat(st)
        type_key = a.activity_type.type_key if getattr(a, "activity_type", None) else "unknown"
        return {
            "activity_id": str(a.activity_id),
            "user_id": "chris",
            "start_time_local": st.isoformat(),
            "date": st.date().isoformat(),
            "activity_type": type_key,
            "name": getattr(a, "activity_name", None),
            "duration_s": int(a.duration) if getattr(a, "duration", None) else None,
            "moving_duration_s": int(a.moving_duration) if getattr(a, "moving_duration", None) else None,
            "distance_m": int(a.distance) if getattr(a, "distance", None) else None,
            "avg_hr": int(a.average_hr) if getattr(a, "average_hr", None) else None,
            "max_hr": int(a.max_hr) if getattr(a, "max_hr", None) else None,
            "calories": int(a.calories) if getattr(a, "calories", None) else None,
            "elevation_gain_m": int(a.elevation_gain) if getattr(a, "elevation_gain", None) else None,
            "steps": int(a.steps) if getattr(a, "steps", None) else None,
        }
    except Exception as e:
        logger.warning(f"activity_to_row failed: {e}")
        return None


def modality_for(activity_type: str) -> str | None:
    return GARMIN_TYPE_TO_MODALITY.get((activity_type or "").lower())


def match_activity(cardio: dict, activities: list[dict], used: set[str]) -> dict | None:
    """Best Garmin activity for a logged cardio session: same date, compatible
    modality, closest duration. ``used`` = activity ids already linked."""
    want = cardio.get("modality") or "other"
    cands = []
    for a in activities:
        if a["activity_id"] in used or str(a["date"]) != str(cardio["session_date"]):
            continue
        mod = modality_for(a["activity_type"])
        if mod is None or mod not in _COMPATIBLE.get(want, {want}):
            continue
        dur_gap = abs(int(a.get("duration_s") or 0) / 60 - int(cardio.get("duration_min") or 0)) if cardio.get("duration_min") else 0
        exact = 0 if mod == want else 1
        cands.append((exact, dur_gap, a))
    if not cands:
        return None
    cands.sort(key=lambda t: (t[0], t[1]))
    return cands[0][2]


def auto_cardio_row(a: dict, programme_id: str | None) -> dict | None:
    """Cardio row for a watch-recorded activity nobody logged."""
    mod = modality_for(a["activity_type"])
    if mod is None or mod == "run":
        return None
    minutes = int(round((a.get("duration_s") or 0) / 60))
    if minutes < MIN_AUTO_CARDIO_MIN:
        return None
    return {
        "user_id": "chris", "programme_id": programme_id, "session_date": str(a["date"]),
        "modality": mod, "intensity": "hard" if mod == "stairmaster" else "easy",
        "duration_min": minutes, "avg_hr": a.get("avg_hr"), "max_hr": a.get("max_hr"),
        "calories": a.get("calories"), "distance_m": a.get("distance_m"),
        "garmin_activity_id": a["activity_id"], "source": "garmin",
        "notes": f"Auto-imported from Garmin: {a.get('name') or a['activity_type']}",
    }


# ── I/O ───────────────────────────────────────────────────────────────

async def fetch_recent_activities(days: int = 7, limit: int = 60) -> list[dict]:
    """Pull recent activities from Garmin Connect (blocking garth, off-thread)."""
    import garth
    from domains.nutrition.services.garmin import _get_client

    _get_client()
    acts = await asyncio.to_thread(garth.Activity.list, limit)
    cutoff = datetime.now() - timedelta(days=days)
    rows = []
    for a in acts:
        row = activity_to_row(a)
        if not row:
            continue
        if datetime.fromisoformat(row["start_time_local"]).replace(tzinfo=None) < cutoff:
            continue
        rows.append(row)
    return rows


async def sync_garmin_activities(days: int = 7) -> dict:
    from domains.fitness import service as fit
    import httpx

    rows = await fetch_recent_activities(days)
    ok = 0
    headers = {**fit._write_headers(), "Prefer": "resolution=merge-duplicates"}
    async with httpx.AsyncClient(timeout=30) as c:
        for r in rows:
            resp = await c.post(f"{fit.SUPABASE_URL}/rest/v1/garmin_activities?on_conflict=activity_id",
                                headers=headers, json={k: v for k, v in r.items() if v is not None})
            if resp.status_code in (200, 201, 204):
                ok += 1
            else:
                logger.warning(f"garmin_activities upsert {r['activity_id']}: {resp.status_code} {resp.text[:160]}")
    logger.info(f"Garmin activities sync: {ok}/{len(rows)} upserted ({days}d window)")
    return {"fetched": len(rows), "upserted": ok}


async def get_activities(start: date, end: date) -> list[dict]:
    from domains.fitness import service as fit
    import httpx
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{fit.SUPABASE_URL}/rest/v1/garmin_activities", headers=fit._read_headers(),
                        params={"select": "*", "user_id": "eq.chris", "date": f"gte.{start.isoformat()}",
                                "and": f"(date.lte.{end.isoformat()})", "order": "start_time_local.desc"})
        r.raise_for_status()
        return r.json()


async def link_and_backfill(days: int = 7) -> dict:
    """Link logged cardio/strength to Garmin activities; auto-create cardio for unlogged ones."""
    from domains.fitness import service as fit
    import httpx

    today = fit._today()
    start = today - timedelta(days=days)
    acts = await get_activities(start, today)
    if not acts:
        return {"linked_cardio": 0, "linked_strength": 0, "created_cardio": 0, "activities": 0}
    cardio = await fit.get_cardio_in_range(start, today)
    workouts = await fit.get_sessions_in_range(start, today)
    programme = await fit.get_active_programme()
    used: set[str] = {c["garmin_activity_id"] for c in cardio if c.get("garmin_activity_id")}
    used |= {w["garmin_activity_id"] for w in workouts if w.get("garmin_activity_id")}

    linked_c = linked_s = created = 0
    async with httpx.AsyncClient(timeout=20) as c:
        # 1. link logged cardio
        for row in cardio:
            if row.get("garmin_activity_id"):
                continue
            a = match_activity(row, acts, used)
            if not a:
                continue
            patch = {"garmin_activity_id": a["activity_id"]}
            for k in ("avg_hr", "max_hr", "calories", "distance_m"):
                if row.get(k) is None and a.get(k) is not None:
                    patch[k] = a[k]
            if row.get("duration_min") is None and a.get("duration_s"):
                patch["duration_min"] = int(round(a["duration_s"] / 60))
            r = await c.patch(fit._url(fit.CARDIO_TABLE), headers=fit._write_headers(),
                              params={"id": f"eq.{row['id']}"}, json=patch)
            if r.status_code < 300:
                used.add(a["activity_id"]); linked_c += 1
        # 2. link strength sessions
        for w in workouts:
            if w.get("garmin_activity_id") or w["session_type"] in ("mobility", "rest", "cardio"):
                continue
            a = next((x for x in acts if x["activity_id"] not in used and str(x["date"]) == str(w["session_date"])
                      and x["activity_type"] in STRENGTH_TYPES), None)
            if not a:
                continue
            patch = {"garmin_activity_id": a["activity_id"]}
            if w.get("duration_min") is None and a.get("duration_s"):
                patch["duration_min"] = int(round(a["duration_s"] / 60))
            r = await c.patch(fit._url(fit.SESSIONS_TABLE), headers=fit._write_headers(),
                              params={"id": f"eq.{w['id']}"}, json=patch)
            if r.status_code < 300:
                used.add(a["activity_id"]); linked_s += 1
        # 3. auto-create cardio for unlogged recorded activities (only from the
        #    plan start onwards, so old history does not pollute the cardio log)
        plan, _row = await fit.get_plan_or_default()
        plan_start = str(plan.get("started") or "0000-00-00")
        for a in acts:
            if a["activity_id"] in used or str(a["date"]) < plan_start:
                continue
            row = auto_cardio_row(a, programme["id"] if programme else None)
            if not row:
                continue
            r = await c.post(fit._url(fit.CARDIO_TABLE), headers=fit._write_headers(), json=row)
            if r.status_code < 300:
                used.add(a["activity_id"]); created += 1
            else:
                logger.warning(f"auto cardio insert failed: {r.status_code} {r.text[:160]}")
    logger.info(f"Garmin link: cardio={linked_c} strength={linked_s} created={created}")
    return {"linked_cardio": linked_c, "linked_strength": linked_s, "created_cardio": created, "activities": len(acts)}


async def sync_and_link(days: int = 7) -> dict:
    out = {"sync": None, "link": None}
    try:
        out["sync"] = await sync_garmin_activities(days)
    except Exception as e:
        logger.warning(f"Garmin activities sync failed: {e}")
        out["sync"] = {"error": str(e)}
    try:
        out["link"] = await link_and_backfill(days)
    except Exception as e:
        logger.warning(f"Garmin link failed: {e}")
        out["link"] = {"error": str(e)}
    return out


async def link_cardio_row(row: dict) -> dict | None:
    """Try to link ONE freshly logged cardio row to an already-synced activity (no Garmin call)."""
    from domains.fitness import service as fit
    import httpx
    d = date.fromisoformat(str(row["session_date"]))
    acts = await get_activities(d, d)
    if not acts:
        return None
    cardio_same_day = await fit.get_cardio_in_range(d, d)
    used = {c["garmin_activity_id"] for c in cardio_same_day if c.get("garmin_activity_id") and c["id"] != row["id"]}
    a = match_activity(row, acts, used)
    if not a:
        return None
    patch = {"garmin_activity_id": a["activity_id"]}
    for k in ("avg_hr", "max_hr", "calories", "distance_m"):
        if row.get(k) is None and a.get(k) is not None:
            patch[k] = a[k]
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.patch(fit._url(fit.CARDIO_TABLE), headers=fit._write_headers(),
                          params={"id": f"eq.{row['id']}"}, json=patch)
        if r.status_code < 300:
            return {**row, **patch}
    return None
