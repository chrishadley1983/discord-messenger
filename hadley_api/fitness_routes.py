"""Fitness tracking API.

Endpoints powering the 13-week post-Japan fat-loss programme:

- GET  /fitness/programme              — active programme + day/week numbers
- GET  /fitness/today                  — today's prescribed workout + targets
- GET  /fitness/dashboard              — full daily status (trend, adherence, workout)
- GET  /fitness/weekly-review          — Sunday review bundle
- GET  /fitness/trend?days=30          — smoothed weight trend math
- GET  /fitness/exercises              — exercise library (with videos + instructions)
- GET  /fitness/mobility/routine       — fixed 10-min daily mobility flow
- GET  /fitness/mobility/today         — today's mobility slots + streak
- POST /fitness/workout                — log a session + sets
- POST /fitness/mobility               — log a mobility slot
- POST /fitness/programme/start        — one-shot init: TDEE, programme, accountability goals
- POST /fitness/programme/recalibrate  — recompute calories/protein from latest weight
- POST /fitness/weekly-checkin         — persist a Sunday check-in snapshot
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from hadley_api.auth import require_auth
from domains.fitness import service as fit
from domains.fitness.trend import compute_trend
from domains.fitness.programme_generator import generate_week, session_to_dict
from domains.fitness.programme_start import start_programme as do_start
from domains.fitness.advisor import get_advice

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fitness", tags=["fitness"])


# ── Request models ──────────────────────────────────────────────────────


class WorkoutSet(BaseModel):
    exercise_slug: str
    set_no: int = 1
    reps: Optional[int] = None
    hold_s: Optional[int] = None
    notes: Optional[str] = None


class LogWorkoutRequest(BaseModel):
    session_type: str
    duration_min: Optional[int] = None
    rpe: Optional[int] = None
    notes: Optional[str] = None
    sets: list[WorkoutSet] = []
    session_date: Optional[str] = None


class LogMobilityRequest(BaseModel):
    slot: str                     # "morning" | "evening" | "adhoc"
    duration_min: int = 10
    routine: Optional[str] = None
    session_date: Optional[str] = None


class StartProgrammeRequest(BaseModel):
    start_date: str               # ISO
    current_weight_kg: float
    target_loss_kg: float = 10.0
    duration_weeks: int = 13


class RecalibrateRequest(BaseModel):
    # All optional — if unset, endpoint uses latest trend weight and 7d step avg
    current_weight_kg: Optional[float] = None
    avg_steps: Optional[float] = None
    deficit_kcal: int = 550


# ── Read endpoints ──────────────────────────────────────────────────────


@router.get("/programme")
async def get_programme():
    programme = await fit.get_active_programme()
    if not programme:
        return {"programme": None, "message": "No active programme"}
    wk = fit.week_number(programme)
    return {
        "programme": programme,
        "week_no": wk,
        "day_no": (fit._today() - fit.date.fromisoformat(programme["start_date"])).days + 1
                   if wk >= 1 else 0,
    }


@router.get("/today")
async def get_today():
    """Today's prescribed session + calorie/protein/steps targets."""
    programme = await fit.get_active_programme()
    if not programme:
        return {"error": "No active programme"}

    wk = fit.week_number(programme)
    dow = fit._today().weekday()
    sessions = generate_week(programme["split"], max(1, wk))
    today_session = next((s for s in sessions if s.day_of_week == dow), None)

    return {
        "programme_id": programme["id"],
        "week_no": wk,
        "day_of_week": dow,
        "targets": {
            "calories": programme["daily_calorie_target"],
            "protein_g": programme["daily_protein_g"],
            "steps": programme["daily_steps_target"],
        },
        "workout": session_to_dict(today_session) if today_session else None,
    }


@router.get("/dashboard")
async def get_dashboard():
    """Full daily fitness dashboard."""
    data = await fit.compute_dashboard()
    return data


@router.get("/weekly-review")
async def get_weekly_review():
    data = await fit.compute_weekly_review()
    return data


@router.get("/trend")
async def get_trend(days: int = Query(30, ge=1, le=365)):
    history = await fit.fetch_weight_history(days)
    trend = compute_trend(history)
    return {
        "days": days,
        "readings_count": trend.readings_count,
        "latest_raw": trend.latest_raw,
        "trend_7d": trend.trend_7d,
        "trend_ema": trend.trend_ema,
        "slope_kg_per_week": trend.slope_kg_per_week,
        "stalled": trend.stalled,
        "message": trend.message,
        "readings": history,
    }


@router.get("/trends")
async def get_trends(days: int = Query(90, ge=7, le=365)):
    """Time-series for the Trends tab: weight, steps, sleep, RHR, HRV, stress.

    Each series is `[{date, value}]` ordered oldest -> newest with nulls dropped
    so the UI can plot directly without filtering. `summary` returns current
    vs prior-period deltas for headline KPI tiles.
    """
    series = await fit.fetch_trends_series(days)
    return {
        "days": days,
        "series": series["series"],
        "summary": series["summary"],
    }


@router.get("/exercises")
async def list_exercises(category: Optional[str] = None):
    """Exercise library.

    Returns all exercises (or a single category) with their full metadata:
    name, slug, category, muscle group, default sets/reps/holds, form cue,
    progression note, step-by-step instructions, equipment, and a video URL
    (YouTube search link — always live).
    """
    all_ex = await fit.get_all_exercises()
    if category:
        all_ex = [e for e in all_ex if e["category"] == category]

    # Group by category for easy frontend rendering. Category order matches
    # the training split progression (push/pull/legs first, then core,
    # conditioning, mobility as support).
    category_order = ["push", "pull", "legs", "core", "conditioning", "mobility"]
    by_category: dict[str, list[dict]] = {c: [] for c in category_order}
    for ex in all_ex:
        by_category.setdefault(ex["category"], []).append(ex)

    return {
        "exercises": all_ex,
        "by_category": by_category,
        "category_order": category_order,
        "count": len(all_ex),
    }


@router.get("/mobility/routine")
async def get_mobility_routine():
    """Return the fixed 10-minute daily mobility flow.

    Each move is joined against the exercise library so the frontend has
    name, form cue, instructions, video URL, and equipment in a single
    payload. No auth required — reference data.
    """
    routine = await fit.get_mobility_routine()
    return routine


@router.get("/mobility/today")
async def get_mobility_today():
    """Which mobility slots have been done today + 7-day history + streak.

    A day counts as "done" if at least one slot (morning OR evening) was
    logged. Streak walks backwards from today; today not being done yet
    does NOT break the streak (the day is still in progress).
    """
    from datetime import timedelta
    import httpx

    status = await fit.mobility_today()
    today = fit._today()

    # Pull a window a bit wider than 7 days so the streak can extend past
    # 7 if Chris has been consistent.
    cutoff = (today - timedelta(days=30)).isoformat()
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(
            f"{fit.SUPABASE_URL}/rest/v1/{fit.MOBILITY_TABLE}",
            headers=fit._read_headers(),
            params={
                "select": "session_date,slot",
                "user_id": "eq.chris",
                "session_date": f"gte.{cutoff}",
                "order": "session_date.desc",
            },
        )
        resp.raise_for_status()
        rows = resp.json()

    days_done: set[str] = {str(r["session_date"]) for r in rows}

    # 7-day history (most recent first)
    history = [
        {
            "date": (today - timedelta(days=i)).isoformat(),
            "done": (today - timedelta(days=i)).isoformat() in days_done,
        }
        for i in range(7)
    ]

    # Streak: walk back from today. Today not done yet is a "grace" day.
    streak = 0
    for i in range(30):
        d = (today - timedelta(days=i)).isoformat()
        if d in days_done:
            streak += 1
        elif i == 0:
            continue  # today in progress — don't break, don't count
        else:
            break

    return {
        "today": status,
        "streak_days": streak,
        "history_7d": history,
    }


@router.get("/advice")
async def get_fitness_advice():
    """PT/nutritionist-quality advice based on all available signals.

    Cross-references nutrition, weight trend, recovery (sleep, HRV, HR),
    training load, mobility, and programme context. Returns structured
    advice items sorted by severity (warning > caution > info > positive).
    """
    return await get_advice()


# ── Write endpoints (auth-gated) ────────────────────────────────────────


@router.post("/workout", dependencies=[Depends(require_auth)])
async def log_workout(req: LogWorkoutRequest):
    programme = await fit.get_active_programme()
    wk = fit.week_number(programme) if programme else None
    session = await fit.log_workout(
        session_type=req.session_type,
        session_date=req.session_date,
        duration_min=req.duration_min,
        rpe=req.rpe,
        notes=req.notes,
        sets=[s.model_dump() for s in req.sets],
        programme_id=programme["id"] if programme else None,
        week_no=wk,
    )
    return {"session": session, "status": "logged"}


@router.post("/mobility", dependencies=[Depends(require_auth)])
async def log_mobility(req: LogMobilityRequest):
    programme = await fit.get_active_programme()
    row = await fit.log_mobility(
        slot=req.slot,
        session_date=req.session_date,
        duration_min=req.duration_min,
        routine=req.routine,
        programme_id=programme["id"] if programme else None,
    )
    return {"session": row, "status": "logged"}


@router.post("/programme/start", dependencies=[Depends(require_auth)])
async def start_programme(req: StartProgrammeRequest):
    api_base = os.getenv("HADLEY_API_INTERNAL", "http://localhost:8100")
    api_key = os.getenv("HADLEY_AUTH_KEY", "")
    result = await do_start(
        start_date=req.start_date,
        current_weight_kg=req.current_weight_kg,
        target_loss_kg=req.target_loss_kg,
        duration_weeks=req.duration_weeks,
        api_base=api_base,
        api_key=api_key,
    )
    return result


@router.post("/programme/recalibrate", dependencies=[Depends(require_auth)])
async def recalibrate_programme(req: RecalibrateRequest):
    """Recompute and persist calorie/protein targets from latest weight.

    As Chris loses weight his BMR drops ~10 kcal per kg lost. At a 1.6
    activity multiplier that's ~80 kcal off TDEE for every 5kg, which is
    enough to stall fat loss if the target isn't refreshed. This endpoint
    pulls the latest trend weight + 7-day step average (or accepts explicit
    overrides) and updates the active programme row in-place.
    """
    programme = await fit.get_active_programme()
    if not programme:
        return JSONResponse(
            status_code=400,
            content={"error": "No active programme to recalibrate"},
        )

    # Resolve current weight from latest trend if not supplied
    weight = req.current_weight_kg
    if weight is None:
        history = await fit.fetch_weight_history(30)
        trend = compute_trend(history)
        weight = trend.trend_7d or trend.latest_raw
        if weight is None:
            return JSONResponse(
                status_code=400,
                content={"error": "No weight history available for recalibration"},
            )

    # Resolve steps from 7-day average if not supplied
    steps_avg = req.avg_steps
    if steps_avg is None:
        steps_hist = await fit.fetch_steps_history(7)
        steps_avg = (
            sum(p["value"] for p in steps_hist) / len(steps_hist)
            if steps_hist else float(programme["daily_steps_target"])
        )
        # Don't under-estimate if Chris is still ramping — use his target
        # as a floor so we don't shrink calories based on a slow week.
        steps_avg = max(steps_avg, float(programme["daily_steps_target"]))

    result = await fit.recalibrate_programme(
        programme,
        current_weight_kg=float(weight),
        avg_steps=float(steps_avg),
        deficit_kcal=req.deficit_kcal,
    )
    return {"status": "recalibrated", **result}


@router.post("/weekly-checkin", dependencies=[Depends(require_auth)])
async def save_weekly_checkin():
    review = await fit.compute_weekly_review()
    if "error" in review:
        return JSONResponse(status_code=400, content=review)
    saved = await fit.save_weekly_checkin(review)
    return {"review": review, "checkin": saved}
