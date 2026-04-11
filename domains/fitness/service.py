"""Fitness domain service.

CRUD for programmes, workouts, mobility sessions, weekly check-ins, plus
aggregation queries for the daily dashboard and Sunday review.

All DB access goes via httpx + PostgREST against Supabase, matching the
pattern used by `domains/accountability/service.py`.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

import httpx

from domains.fitness.trend import compute_trend, TrendResult
from domains.fitness.tdee import compute_tdee
from domains.fitness.programme_generator import (
    generate_week,
    generate_programme,
    session_to_dict,
    PrescribedSession,
)

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
UK_TZ = ZoneInfo("Europe/London")

PROGRAMMES_TABLE = "fitness_programmes"
EXERCISES_TABLE = "fitness_exercises"
SESSIONS_TABLE = "fitness_workout_sessions"
SETS_TABLE = "fitness_workout_sets"
MOBILITY_TABLE = "fitness_mobility_sessions"
CHECKINS_TABLE = "fitness_weekly_checkins"


def _today() -> date:
    return datetime.now(UK_TZ).date()


def _read_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }


def _write_headers() -> dict:
    return {
        **_read_headers(),
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _url(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"


# ══════════════════════════════════════════════════════════════════════
# PROGRAMMES
# ══════════════════════════════════════════════════════════════════════


async def get_active_programme() -> dict | None:
    """Return the currently active programme (or None)."""
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(
            _url(PROGRAMMES_TABLE),
            headers=_read_headers(),
            params={
                "select": "*",
                "status": "eq.active",
                "user_id": "eq.chris",
                "order": "start_date.desc",
                "limit": "1",
            },
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if rows else None


async def create_programme(
    name: str,
    start_date: str,
    start_weight_kg: float,
    target_weight_kg: float,
    tdee_kcal: int,
    daily_calorie_target: int,
    daily_protein_g: int,
    duration_weeks: int = 13,
    split: str = "5x_short",
    daily_steps_target: int = 12000,
    weekly_strength_sessions: int = 5,
    notes: str | None = None,
) -> dict:
    """Insert a new programme row. Does NOT archive existing programmes."""
    start = date.fromisoformat(start_date)
    end = start + timedelta(weeks=duration_weeks)
    body = {
        "name": name,
        "split": split,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "duration_weeks": duration_weeks,
        "start_weight_kg": start_weight_kg,
        "target_weight_kg": target_weight_kg,
        "tdee_kcal": tdee_kcal,
        "daily_calorie_target": daily_calorie_target,
        "daily_protein_g": daily_protein_g,
        "daily_steps_target": daily_steps_target,
        "weekly_strength_sessions": weekly_strength_sessions,
        "notes": notes,
    }
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.post(_url(PROGRAMMES_TABLE), headers=_write_headers(), json=body)
        resp.raise_for_status()
        return resp.json()[0]


async def abandon_active_programmes() -> int:
    """Mark all active programmes as abandoned. Returns count changed."""
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.patch(
            _url(PROGRAMMES_TABLE),
            headers=_write_headers(),
            params={"status": "eq.active", "user_id": "eq.chris"},
            json={"status": "abandoned"},
        )
        if resp.status_code in (200, 204):
            return len(resp.json()) if resp.content else 0
        return 0


def week_number(programme: dict, target: date | None = None) -> int:
    """Return 1-indexed week of the programme for `target` (defaults to today).

    Returns 0 if before start, duration_weeks+1 if after end.
    """
    target = target or _today()
    start = date.fromisoformat(programme["start_date"])
    if target < start:
        return 0
    delta_days = (target - start).days
    wk = (delta_days // 7) + 1
    if wk > programme["duration_weeks"]:
        return programme["duration_weeks"] + 1
    return wk


# ══════════════════════════════════════════════════════════════════════
# EXERCISES
# ══════════════════════════════════════════════════════════════════════


async def get_exercises_by_slugs(slugs: list[str]) -> dict[str, dict]:
    """Fetch exercise rows keyed by slug."""
    if not slugs:
        return {}
    slug_filter = ",".join(slugs)
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(
            _url(EXERCISES_TABLE),
            headers=_read_headers(),
            params={"select": "*", "slug": f"in.({slug_filter})"},
        )
        resp.raise_for_status()
        return {row["slug"]: row for row in resp.json()}


async def get_all_exercises() -> list[dict]:
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(
            _url(EXERCISES_TABLE),
            headers=_read_headers(),
            params={"select": "*", "order": "category,name"},
        )
        resp.raise_for_status()
        return resp.json()


# ══════════════════════════════════════════════════════════════════════
# WORKOUT SESSIONS
# ══════════════════════════════════════════════════════════════════════


async def log_workout(
    *,
    session_type: str,
    session_date: str | None = None,
    duration_min: int | None = None,
    rpe: int | None = None,
    notes: str | None = None,
    sets: list[dict] | None = None,
    programme_id: str | None = None,
    week_no: int | None = None,
) -> dict:
    """Log a workout session + its per-exercise sets.

    `sets` is a list of {exercise_slug, set_no, reps, hold_s, notes}.
    Exercise slug is resolved to exercise_id before insert.
    """
    body = {
        "session_type": session_type,
        "session_date": session_date or _today().isoformat(),
        "duration_min": duration_min,
        "rpe": rpe,
        "notes": notes,
        "programme_id": programme_id,
        "week_no": week_no,
    }
    async with httpx.AsyncClient(timeout=15) as c:
        resp = await c.post(_url(SESSIONS_TABLE), headers=_write_headers(), json=body)
        resp.raise_for_status()
        session = resp.json()[0]

        if sets:
            slugs = list({s["exercise_slug"] for s in sets})
            ex_map = await get_exercises_by_slugs(slugs)
            set_rows = []
            for s in sets:
                ex = ex_map.get(s["exercise_slug"])
                if not ex:
                    logger.warning(f"Unknown exercise slug: {s['exercise_slug']}")
                    continue
                set_rows.append({
                    "session_id": session["id"],
                    "exercise_id": ex["id"],
                    "set_no": s.get("set_no", 1),
                    "reps": s.get("reps"),
                    "hold_s": s.get("hold_s"),
                    "notes": s.get("notes"),
                })
            if set_rows:
                sresp = await c.post(_url(SETS_TABLE), headers=_write_headers(), json=set_rows)
                sresp.raise_for_status()

    return session


async def get_sessions_in_range(start: date, end: date) -> list[dict]:
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(
            _url(SESSIONS_TABLE),
            headers=_read_headers(),
            params={
                "select": "*",
                "session_date": f"gte.{start.isoformat()}",
                "and": f"(session_date.lte.{end.isoformat()})",
                "order": "session_date.desc",
                "user_id": "eq.chris",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def count_sessions_this_week(today: date | None = None) -> int:
    today = today or _today()
    # ISO week: Monday as start
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)
    sessions = await get_sessions_in_range(start, end)
    return len([s for s in sessions if s["session_type"] not in ("mobility", "rest")])


# ══════════════════════════════════════════════════════════════════════
# MOBILITY
# ══════════════════════════════════════════════════════════════════════


async def log_mobility(
    *,
    slot: str,
    session_date: str | None = None,
    duration_min: int = 10,
    routine: str | None = None,
    programme_id: str | None = None,
) -> dict:
    body = {
        "slot": slot,
        "session_date": session_date or _today().isoformat(),
        "duration_min": duration_min,
        "routine": routine,
        "programme_id": programme_id,
    }
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.post(
            _url(MOBILITY_TABLE),
            headers={**_write_headers(), "Prefer": "resolution=merge-duplicates,return=representation"},
            json=body,
        )
        resp.raise_for_status()
        return resp.json()[0] if resp.json() else body


async def mobility_today() -> dict:
    """Return which slots (morning/evening) are done today."""
    today = _today().isoformat()
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(
            _url(MOBILITY_TABLE),
            headers=_read_headers(),
            params={"select": "slot", "session_date": f"eq.{today}", "user_id": "eq.chris"},
        )
        resp.raise_for_status()
        slots_done = {row["slot"] for row in resp.json()}
    return {
        "morning": "morning" in slots_done,
        "evening": "evening" in slots_done,
        "slots_done": list(slots_done),
    }


# ══════════════════════════════════════════════════════════════════════
# DATA FETCHERS (external tables)
# ══════════════════════════════════════════════════════════════════════


async def fetch_weight_history(days: int = 30) -> list[dict]:
    """Pull raw weight readings from weight_readings (Withings)."""
    cutoff = (_today() - timedelta(days=days)).isoformat()
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(
            f"{SUPABASE_URL}/rest/v1/weight_readings",
            headers=_read_headers(),
            params={
                "select": "measured_at,weight_kg",
                "user_id": "eq.chris",
                "measured_at": f"gte.{cutoff}T00:00:00",
                "order": "measured_at.asc",
            },
        )
        resp.raise_for_status()
        return [
            {"date": str(row["measured_at"])[:10], "value": float(row["weight_kg"])}
            for row in resp.json()
            if row.get("weight_kg") is not None
        ]


async def fetch_steps_history(days: int = 7) -> list[dict]:
    cutoff = (_today() - timedelta(days=days)).isoformat()
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(
            f"{SUPABASE_URL}/rest/v1/garmin_daily_summary",
            headers=_read_headers(),
            params={
                "select": "date,steps",
                "user_id": "eq.chris",
                "date": f"gte.{cutoff}",
                "order": "date.asc",
            },
        )
        resp.raise_for_status()
        return [
            {"date": str(row["date"]), "value": float(row["steps"])}
            for row in resp.json()
            if row.get("steps") is not None
        ]


async def fetch_nutrition_today() -> dict:
    """Sum today's nutrition logs into totals."""
    today = _today().isoformat()
    tomorrow = (_today() + timedelta(days=1)).isoformat()
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(
            f"{SUPABASE_URL}/rest/v1/nutrition_logs",
            headers=_read_headers(),
            params={
                "select": "calories,protein_g,carbs_g,fat_g,water_ml",
                "and": f"(logged_at.gte.{today}T00:00:00,logged_at.lt.{tomorrow}T00:00:00)",
            },
        )
        resp.raise_for_status()
        rows = resp.json()
    totals = {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0, "water_ml": 0.0}
    for row in rows:
        for key in totals:
            if row.get(key) is not None:
                totals[key] += float(row[key])
    return totals


# ══════════════════════════════════════════════════════════════════════
# DASHBOARD AGGREGATOR
# ══════════════════════════════════════════════════════════════════════


async def compute_dashboard() -> dict:
    """Build the full daily fitness dashboard payload.

    Structure:
        {
            "programme": {...} | None,
            "day_no": int, "week_no": int, "days_remaining": int,
            "weight": {trend, latest, slope, stalled, cumulative_loss},
            "nutrition": {calories, protein, target_calories, target_protein},
            "steps": {today, target, avg_7d},
            "today_workout": {session_type, exercises, done},
            "mobility": {morning, evening},
            "strength_this_week": {done, target},
            "flags": [...],   # human-readable alerts
        }
    """
    programme = await get_active_programme()

    weight_history = await fetch_weight_history(30)
    trend = compute_trend(weight_history)

    nutrition = await fetch_nutrition_today()
    steps_history = await fetch_steps_history(7)
    steps_today = steps_history[-1]["value"] if steps_history else 0
    steps_avg = (
        sum(p["value"] for p in steps_history) / len(steps_history)
        if steps_history else 0
    )
    mob = await mobility_today()
    strength_this_week = await count_sessions_this_week()

    flags: list[str] = []
    result: dict[str, Any] = {
        "programme": programme,
        "weight": {
            "latest_raw": trend.latest_raw,
            "trend_7d": round(trend.trend_7d, 2) if trend.trend_7d else None,
            "trend_ema": round(trend.trend_ema, 2) if trend.trend_ema else None,
            "slope_kg_per_week": round(trend.slope_kg_per_week, 2) if trend.slope_kg_per_week else None,
            "stalled": trend.stalled,
            "message": trend.message,
        },
        "nutrition": nutrition,
        "steps": {
            "today": int(steps_today),
            "avg_7d": int(steps_avg),
        },
        "mobility": mob,
        "strength_this_week": {"done": strength_this_week},
        "flags": flags,
    }

    if programme:
        wk = week_number(programme)
        start = date.fromisoformat(programme["start_date"])
        end = date.fromisoformat(programme["end_date"])
        days_remaining = max(0, (end - _today()).days)
        day_no = (_today() - start).days + 1

        result["day_no"] = day_no
        result["week_no"] = wk
        result["days_remaining"] = days_remaining

        # Fill in target values
        result["nutrition"]["target_calories"] = programme["daily_calorie_target"]
        result["nutrition"]["target_protein"] = programme["daily_protein_g"]
        result["steps"]["target"] = programme["daily_steps_target"]
        result["strength_this_week"]["target"] = programme["weekly_strength_sessions"]

        # Cumulative loss
        if trend.trend_7d is not None and programme.get("start_weight_kg"):
            loss = float(programme["start_weight_kg"]) - trend.trend_7d
            result["weight"]["cumulative_loss_kg"] = round(loss, 2)
            pct = loss / (float(programme["start_weight_kg"]) - float(programme["target_weight_kg"])) * 100
            result["weight"]["progress_pct"] = round(pct, 1)

        # Today's prescribed workout
        if 1 <= wk <= programme["duration_weeks"]:
            week_sessions = generate_week(programme["split"], wk)
            dow = _today().weekday()
            today_session = next((s for s in week_sessions if s.day_of_week == dow), None)
            if today_session:
                result["today_workout"] = session_to_dict(today_session)
            else:
                result["today_workout"] = None

        # Flags
        if trend.stalled:
            flags.append("WEIGHT TREND STALLED — drop 100 kcal + add 2k steps")
        if nutrition["calories"] > programme["daily_calorie_target"] * 1.1:
            flags.append(f"Over calorie target by {int(nutrition['calories'] - programme['daily_calorie_target'])} kcal")
        if nutrition["protein_g"] < programme["daily_protein_g"] * 0.8 and datetime.now(UK_TZ).hour >= 18:
            flags.append(f"Behind on protein: {int(nutrition['protein_g'])}/{programme['daily_protein_g']}g")
        if not mob["morning"] and datetime.now(UK_TZ).hour >= 10:
            flags.append("Morning mobility not logged")

    return result


# ══════════════════════════════════════════════════════════════════════
# WEEKLY REVIEW
# ══════════════════════════════════════════════════════════════════════


async def compute_weekly_review() -> dict:
    """Build Sunday review payload: 7-day adherence, trend change, adjustment."""
    programme = await get_active_programme()
    if not programme:
        return {"error": "No active programme"}

    today = _today()
    week_start = today - timedelta(days=today.weekday())  # Monday
    week_end = week_start + timedelta(days=6)
    wk_no = week_number(programme, today)

    # Weight
    weight_history = await fetch_weight_history(30)
    trend = compute_trend(weight_history)

    # Last week's weight for delta
    prev_week_values = [
        r["value"] for r in weight_history
        if week_start - timedelta(days=7) <= date.fromisoformat(r["date"]) < week_start
    ]
    this_week_values = [
        r["value"] for r in weight_history
        if week_start <= date.fromisoformat(r["date"]) <= week_end
    ]
    prev_avg = sum(prev_week_values) / len(prev_week_values) if prev_week_values else None
    this_avg = sum(this_week_values) / len(this_week_values) if this_week_values else None
    weight_change = (
        round(this_avg - prev_avg, 2) if (prev_avg is not None and this_avg is not None) else None
    )

    # Cumulative loss since programme start
    cum_loss = None
    if this_avg is not None and programme.get("start_weight_kg"):
        cum_loss = round(float(programme["start_weight_kg"]) - this_avg, 2)

    # Nutrition adherence (rough: look at nutrition_logs per day this week)
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(
            f"{SUPABASE_URL}/rest/v1/nutrition_logs",
            headers=_read_headers(),
            params={
                "select": "logged_at,calories,protein_g",
                "and": f"(logged_at.gte.{week_start.isoformat()}T00:00:00,logged_at.lt.{(week_end+timedelta(days=1)).isoformat()}T00:00:00)",
            },
        )
        resp.raise_for_status()
        logs = resp.json()

    daily_cal: dict[str, float] = {}
    daily_pro: dict[str, float] = {}
    for r in logs:
        d = str(r["logged_at"])[:10]
        daily_cal[d] = daily_cal.get(d, 0) + float(r.get("calories") or 0)
        daily_pro[d] = daily_pro.get(d, 0) + float(r.get("protein_g") or 0)

    target_cal = programme["daily_calorie_target"]
    target_pro = programme["daily_protein_g"]
    days_under_cal = sum(1 for v in daily_cal.values() if v <= target_cal * 1.05)
    days_hit_pro = sum(1 for v in daily_pro.values() if v >= target_pro * 0.95)
    tracked_days = len(daily_cal)

    # Steps adherence
    steps_week = await fetch_steps_history(7)
    steps_target = programme["daily_steps_target"]
    days_hit_steps = sum(1 for p in steps_week if p["value"] >= steps_target)

    # Strength sessions done
    sessions = await get_sessions_in_range(week_start, week_end)
    strength_done = len([s for s in sessions if s["session_type"] not in ("mobility", "rest")])

    # Mobility days hit
    async with httpx.AsyncClient(timeout=10) as c:
        mresp = await c.get(
            _url(MOBILITY_TABLE),
            headers=_read_headers(),
            params={
                "select": "session_date",
                "user_id": "eq.chris",
                "and": f"(session_date.gte.{week_start.isoformat()},session_date.lte.{week_end.isoformat()})",
            },
        )
        mresp.raise_for_status()
        mobility_days = len({row["session_date"] for row in mresp.json()})

    # Adjustment logic
    next_cal = target_cal
    next_steps = steps_target
    adjustment = "Continue current plan"
    if trend.stalled:
        next_cal = target_cal - 100
        next_steps = steps_target + 2000
        adjustment = f"STALL: -100 kcal ({next_cal}) and +2k steps ({next_steps})"

    return {
        "programme": programme,
        "week_no": wk_no,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "weight": {
            "trend_7d": round(this_avg, 2) if this_avg else None,
            "change_vs_last_week_kg": weight_change,
            "cumulative_loss_kg": cum_loss,
            "slope_kg_per_week": round(trend.slope_kg_per_week, 2) if trend.slope_kg_per_week else None,
            "stalled": trend.stalled,
        },
        "nutrition": {
            "tracked_days": tracked_days,
            "days_under_cal_target": days_under_cal,
            "days_hit_protein": days_hit_pro,
            "avg_calories": round(sum(daily_cal.values()) / tracked_days) if tracked_days else 0,
            "avg_protein_g": round(sum(daily_pro.values()) / tracked_days) if tracked_days else 0,
        },
        "steps": {
            "days_hit_target": days_hit_steps,
            "avg": round(sum(p["value"] for p in steps_week) / len(steps_week)) if steps_week else 0,
        },
        "strength": {
            "sessions_done": strength_done,
            "target": programme["weekly_strength_sessions"],
        },
        "mobility": {
            "days_hit": mobility_days,
            "target": 7,
        },
        "adjustment": {
            "next_calorie_target": next_cal,
            "next_steps_target": next_steps,
            "note": adjustment,
        },
    }


async def save_weekly_checkin(review: dict) -> dict | None:
    """Persist a weekly review as a check-in row."""
    programme = review.get("programme")
    if not programme:
        return None

    row = {
        "programme_id": programme["id"],
        "week_no": review["week_no"],
        "week_ending": review["week_end"],
        "trend_weight_kg": review["weight"]["trend_7d"],
        "weight_change_kg": review["weight"]["change_vs_last_week_kg"],
        "cumulative_loss_kg": review["weight"]["cumulative_loss_kg"],
        "calories_adherence_pct": (
            round(review["nutrition"]["days_under_cal_target"] / 7 * 100)
            if review["nutrition"]["tracked_days"] else 0
        ),
        "protein_adherence_pct": (
            round(review["nutrition"]["days_hit_protein"] / 7 * 100)
            if review["nutrition"]["tracked_days"] else 0
        ),
        "steps_adherence_pct": round(review["steps"]["days_hit_target"] / 7 * 100),
        "strength_sessions_hit": review["strength"]["sessions_done"],
        "mobility_days_hit": review["mobility"]["days_hit"],
        "next_calorie_target": review["adjustment"]["next_calorie_target"],
        "next_steps_target": review["adjustment"]["next_steps_target"],
        "adjustment_note": review["adjustment"]["note"],
    }
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.post(
            _url(CHECKINS_TABLE),
            headers={**_write_headers(), "Prefer": "resolution=merge-duplicates,return=representation"},
            json=row,
        )
        if resp.status_code in (200, 201):
            return resp.json()[0] if resp.json() else row
        return None
