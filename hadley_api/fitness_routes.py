"""Fitness tracking API.

Endpoints powering the 13-week post-Japan fat-loss programme:

- GET  /fitness/programme         — active programme + day/week numbers
- GET  /fitness/today             — today's prescribed workout + targets
- GET  /fitness/dashboard         — full daily status (trend, adherence, workout)
- GET  /fitness/weekly-review     — Sunday review bundle
- GET  /fitness/trend?days=30     — smoothed weight trend math
- GET  /fitness/exercises         — exercise library
- POST /fitness/workout           — log a session + sets
- POST /fitness/mobility          — log a mobility slot
- POST /fitness/programme/start   — one-shot init: TDEE, programme, accountability goals
- POST /fitness/weekly-checkin    — persist a Sunday check-in snapshot
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


@router.get("/exercises")
async def list_exercises(category: Optional[str] = None):
    all_ex = await fit.get_all_exercises()
    if category:
        all_ex = [e for e in all_ex if e["category"] == category]
    return {"exercises": all_ex, "count": len(all_ex)}


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


@router.post("/weekly-checkin", dependencies=[Depends(require_auth)])
async def save_weekly_checkin():
    review = await fit.compute_weekly_review()
    if "error" in review:
        return JSONResponse(status_code=400, content=review)
    saved = await fit.save_weekly_checkin(review)
    return {"review": review, "checkin": saved}
