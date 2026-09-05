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
- GET  /fitness/goal                   — resolved goal phase + live targets
- PUT  /fitness/goal                   — update the active programme's goal/phase config

Gym training log + adaptive plan (Sep 2026):
- GET  /fitness/next-session?type=     — next strength session, targets derived from logged history
- GET  /fitness/workouts?days=28       — logged sessions with sets (history)
- POST /fitness/cardio                 — log a cardio session (easy / hard, protocol blocks)
- GET  /fitness/cardio?days=28         — cardio history
- GET  /fitness/training-summary       — this week: strength + cardio vs plan, stalls, wins
- GET  /fitness/plan                   — the active training plan (versioned data)
- PUT  /fitness/plan                   — replace / patch the plan (new version, rationale recorded)
- GET  /fitness/plan/history           — plan versions

Phase 2 (Garmin activities + Fitbod import):
- POST /fitness/garmin/sync?days=7     — pull recent Garmin activities, link cardio/strength logs, auto-create unlogged cardio
- GET  /fitness/garmin/activities      — synced activities
- POST /fitness/import/fitbod          — import a Fitbod CSV export (body: {csv, dry_run})
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, HTMLResponse
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
    weight_kg: Optional[float] = None      # load on the stack / bar
    rir: Optional[int] = None              # reps in reserve (0 = failure)
    failed: bool = False                   # stopped short of target_reps
    target_reps: Optional[int] = None
    notes: Optional[str] = None
    # hints used only when the slug is new to the library (auto-created)
    exercise_name: Optional[str] = None
    category: Optional[str] = None         # push / pull / legs / core / conditioning / other
    muscle_group: Optional[str] = None
    equipment: Optional[str] = None


class LogCardioRequest(BaseModel):
    modality: str                          # stairmaster / treadmill / bike / rower / elliptical / walk / other
    intensity: str = "easy"                # easy | hard
    duration_min: Optional[int] = None
    protocol: Optional[list[dict]] = None  # [{phase, seconds, level}] — or use the shortcuts below
    peak_level: Optional[float] = None
    work_level: Optional[float] = None
    peak_seconds: Optional[int] = None     # shortcut: instantiate the plan pyramid with these
    hard_seconds: Optional[int] = None
    avg_hr: Optional[int] = None
    max_hr: Optional[int] = None
    calories: Optional[int] = None
    distance_m: Optional[int] = None
    rpe: Optional[int] = None
    limiter: Optional[str] = None          # legs / breathing / hip / time
    pain_flag: bool = False
    notes: Optional[str] = None
    garmin_activity_id: Optional[str] = None
    session_date: Optional[str] = None


class FitbodImportRequest(BaseModel):
    csv: Optional[str] = None            # raw CSV text
    file_path: Optional[str] = None      # or a local/WSL path the API can read
    dry_run: bool = False
    include_warmups: bool = False
    skip_if_day_logged: bool = True


class UpdatePlanRequest(BaseModel):
    plan: Optional[dict] = None            # full replacement
    patch: Optional[dict] = None           # targeted edit — see training_plan.apply_plan_patch
    use_default: bool = False              # (re)seed from the built-in default plan
    rationale: str = "Updated via Peter"
    created_by: str = "peter"


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
    # None -> use the programme's own deficit (falls back to 550 if unset)
    deficit_kcal: Optional[int] = None


class UpdateGoalRequest(BaseModel):
    # Either replace the whole config, or send convenience partials that are
    # merged into the existing goal_config.
    goal_config: Optional[dict] = None       # full replacement
    current_phase: Optional[str] = None      # flip the active phase (must exist)
    phases: Optional[dict] = None            # merge/replace named phase definitions
    auto_switch: Optional[dict] = None       # replace the auto-switch rule


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
    sessions = await fit.week_sessions_for(programme, max(1, wk))
    today_session = next((s for s in sessions if s.day_of_week == dow), None)

    out = {
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
    # Plan-driven split: the week view is a projection, so also say what the
    # NEXT strength session is (rotation + rest gap) regardless of the day.
    if programme.get("split") == "plan":
        try:
            nxt = await fit.next_session_bundle()
            out["next_session"] = {
                "session_type": nxt["session_type"], "label": nxt.get("label"),
                "rest_gap_ok": nxt.get("rest_gap_ok"), "days_since_last_strength": nxt.get("days_since_last_strength"),
                "exercises": [{"name": e["name"], "slug": e["slug"], "sets": e["sets"], "target_reps": e["target_reps"],
                               "weight_kg": e["weight_kg"], "action": e["action"]} for e in nxt.get("exercises", [])],
            }
        except Exception as e:  # never break the digest over the projection
            logger.warning(f"/fitness/today next_session failed: {e}")
    return out


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


@router.get("/next-session")
async def get_next_session(type: Optional[str] = Query(None, description="upper | lower | full_body — omit for the rotation's next")):
    """Next strength session with per-exercise targets derived from logged history.

    Double progression: every set at/above target with >= 2 reps in reserve ->
    one plate up; a failed set -> hold; failed twice running -> ~10% deload.
    Also returns `rest_gap_ok` (>= 1 rest day since the last strength session).
    """
    return await fit.next_session_bundle(type)


@router.get("/workouts")
async def list_workouts(days: int = Query(28, ge=1, le=365)):
    """Logged strength sessions (newest first) with sets embedded."""
    rows = await fit.get_workouts_with_sets(days)
    return {"days": days, "count": len(rows), "sessions": rows}


@router.get("/cardio")
async def list_cardio(days: int = Query(28, ge=1, le=365)):
    today = fit._today()
    rows = await fit.get_cardio_in_range(today - fit.timedelta(days=days), today)
    return {"days": days, "count": len(rows), "sessions": rows}


@router.get("/training-summary")
async def get_training_summary():
    """This ISO week vs the plan: strength done/target + next type, cardio easy/hard, stalls, wins."""
    return await fit.training_week_summary()


@router.get("/plan")
async def get_plan():
    """The active training plan (data). `seeded=false` means the built-in default is being served."""
    plan, row = await fit.get_plan_or_default()
    return {
        "seeded": row is not None,
        "version": row["version"] if row else None,
        "name": row["name"] if row else plan.get("name"),
        "rationale": row.get("rationale") if row else None,
        "created_at": row.get("created_at") if row else None,
        "plan": plan,
    }


@router.get("/plan/history")
async def get_plan_history(limit: int = Query(10, ge=1, le=50)):
    return {"versions": await fit.get_plan_history(limit)}


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
    sets = [s.model_dump() for s in req.sets]
    session = await fit.log_workout(
        session_type=req.session_type,
        session_date=req.session_date,
        duration_min=req.duration_min,
        rpe=req.rpe,
        notes=req.notes,
        sets=sets,
        programme_id=programme["id"] if programme else None,
        week_no=wk,
    )
    out: dict = {"session": session, "status": "logged", "plan_changes": [], "next_time": None, "week": None}

    # Adapt the plan to what was actually done (off-plan exercises / session
    # types get added, never dropped), then brief the NEXT time this session
    # type comes round + the week picture — so the skill can coach in one reply.
    if programme and programme.get("split") == "plan":
        try:
            plan, row = await fit.get_plan_or_default()
            new_plan, changes = fit.tp.reconcile_plan(plan, req.session_type, sets)
            if changes or row is None:
                saved = await fit.save_plan(
                    new_plan,
                    rationale=("Adapted from logged session: " + "; ".join(changes)) if changes else "Seeded on first logged session",
                    created_by="auto",
                )
                out["plan_changes"] = changes
                out["plan_version"] = saved["version"]
            else:
                out["plan_version"] = row["version"]
        except Exception as e:
            logger.warning(f"plan reconcile failed: {e}")
            out["plan_changes"] = [f"(plan not updated: {e})"]
        try:
            out["next_time"] = await fit.next_session_bundle(req.session_type)
            out["week"] = await fit.training_week_summary()
        except Exception as e:
            logger.warning(f"post-log briefing failed: {e}")
    return out


@router.post("/cardio", dependencies=[Depends(require_auth)])
async def log_cardio(req: LogCardioRequest):
    """Log a cardio session. Returns the week picture + the next hard-session prescription."""
    programme = await fit.get_active_programme()
    plan, _ = await fit.get_plan_or_default()
    protocol = req.protocol
    if protocol is None and req.intensity == "hard" and req.modality == (plan.get("cardio", {}).get("hard", {}).get("modality", "stairmaster")):
        template = plan["cardio"]["hard"].get("protocol") or []
        if template and any(v is not None for v in (req.peak_level, req.work_level, req.peak_seconds, req.hard_seconds)):
            protocol = fit.tp.build_protocol(template, hard_level=req.work_level, peak_level=req.peak_level or req.work_level,
                                             peak_seconds=req.peak_seconds, hard_seconds=req.hard_seconds)
    row = await fit.log_cardio(
        modality=req.modality, intensity=req.intensity, session_date=req.session_date,
        duration_min=req.duration_min, protocol=protocol, peak_level=req.peak_level, work_level=req.work_level,
        avg_hr=req.avg_hr, max_hr=req.max_hr, calories=req.calories, distance_m=req.distance_m, rpe=req.rpe,
        limiter=req.limiter, pain_flag=req.pain_flag, notes=req.notes, garmin_activity_id=req.garmin_activity_id,
        programme_id=programme["id"] if programme else None,
    )
    # Link to a watch-recorded activity if one has already been synced today (no Garmin call).
    try:
        from domains.fitness.garmin_activities import link_cardio_row
        linked = await link_cardio_row(row)
        if linked:
            row = linked
    except Exception as e:
        logger.warning(f"cardio garmin link failed: {e}")
    week = await fit.training_week_summary()
    wk = fit.week_number(programme) if programme else None
    last_hard = await fit.last_hard_cardio()
    return {
        "session": row, "status": "logged", "garmin_linked": bool(row.get("garmin_activity_id")),
        "week": week,
        "next_hard": fit.tp.next_cardio_hard(plan, last_hard, wk),
    }


@router.post("/garmin/sync", dependencies=[Depends(require_auth)])
async def garmin_sync(days: int = Query(7, ge=1, le=60)):
    """Sync recent Garmin activities into `garmin_activities`, then link logged cardio /
    strength sessions to them (copying HR + calories) and auto-create `source=garmin`
    cardio rows for recorded activities nobody logged (>= 15 min). Idempotent."""
    from domains.fitness.garmin_activities import sync_and_link
    return await sync_and_link(days)


@router.get("/garmin/activities")
async def garmin_activities(days: int = Query(28, ge=1, le=365)):
    from domains.fitness.garmin_activities import get_activities
    today = fit._today()
    rows = await get_activities(today - fit.timedelta(days=days), today)
    return {"days": days, "count": len(rows), "activities": rows}


@router.post("/import/fitbod", dependencies=[Depends(require_auth)])
async def import_fitbod(req: FitbodImportRequest):
    """Import a Fitbod CSV export. Sessions are grouped per day, exercise names mapped to
    library slugs (unknown ones auto-created), logged via the normal path (plan adapts),
    and deduped on a content hash (`external_id`) + same-day Peter logs."""
    from domains.fitness.fitbod_import import parse_fitbod_csv, import_sessions
    text = req.csv
    if not text and req.file_path:
        p = req.file_path
        if p.startswith("/mnt/"):  # WSL path -> Windows
            parts = p.split("/")
            p = f"{parts[2].upper()}:\\" + "\\".join(parts[3:])
        try:
            text = Path(p).read_text(encoding="utf-8-sig")
        except Exception as e:
            return JSONResponse(status_code=400, content={"error": f"cannot read file: {e}"})
    if not text:
        return JSONResponse(status_code=400, content={"error": "Provide csv text or file_path"})
    sessions = parse_fitbod_csv(text, include_warmups=req.include_warmups)
    result = await import_sessions(sessions, dry_run=req.dry_run, skip_if_day_logged=req.skip_if_day_logged)
    result["parsed"] = len(sessions)
    return result


@router.put("/plan", dependencies=[Depends(require_auth)])
async def update_plan(req: UpdatePlanRequest):
    """Replace or patch the training plan. Every call writes a new version with its rationale."""
    current, row = await fit.get_plan_or_default()
    changes: list[str] = []
    if req.use_default:
        new_plan = fit.tp.default_plan()
        changes = ["reset to the built-in default plan"]
    elif req.plan is not None:
        new_plan = req.plan
        changes = ["full plan replaced"]
    elif req.patch:
        new_plan, changes = fit.tp.apply_plan_patch(current, req.patch)
        if not changes:
            return {"status": "no_change", "version": row["version"] if row else None, "plan": current}
    else:
        return JSONResponse(status_code=400, content={"error": "Provide plan, patch, or use_default"})
    saved = await fit.save_plan(new_plan, rationale=req.rationale, created_by=req.created_by)
    return {"status": "saved", "version": saved["version"], "changes": changes, "plan": saved["plan"]}


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


@router.get("/goal")
async def get_goal():
    """Resolved goal phase (label/focus/protein framing) + live targets.

    The goal_config on the active programme is the source of truth for the
    protein target and coaching framing; this resolves the effective phase
    (applying any BMI auto-switch) and returns the live numbers alongside it.
    """
    programme = await fit.get_active_programme()
    if not programme:
        return {"goal": None, "message": "No active programme"}

    history = await fit.fetch_weight_history(30)
    trend = compute_trend(history)
    weight = trend.trend_7d or trend.latest_raw
    goal = fit.resolve_goal(programme, weight)

    out = {
        "programme_id": programme["id"],
        "current_phase": goal["current_phase"],
        "effective_phase": goal["effective_phase"],
        "transitioned": goal["transitioned"],
        "bmi": round(goal["bmi"], 1) if goal["bmi"] is not None else None,
        "phase": goal["phase"],
        "config": goal["config"],
    }
    if weight:
        steps_hist = await fit.fetch_steps_history(7)
        steps_avg = (
            sum(p["value"] for p in steps_hist) / len(steps_hist)
            if steps_hist else float(programme["daily_steps_target"])
        )
        live = fit.compute_current_targets(
            programme, float(weight),
            max(steps_avg, float(programme["daily_steps_target"])),
        )
        out["live_targets"] = {
            "target_calories": live.target_calories,
            "target_protein_g": live.target_protein_g,
            "weight_used_kg": round(float(weight), 2),
        }
    return out


@router.put("/goal", dependencies=[Depends(require_auth)])
async def put_goal(req: UpdateGoalRequest):
    """Update the active programme's goal_config (Peter's goal editor).

    Send `goal_config` to replace it wholesale, or any of `current_phase`,
    `phases`, `auto_switch` to merge a partial change. The live protein target
    + dashboard framing follow from the resulting config on the next rebuild.
    """
    programme = await fit.get_active_programme()
    if not programme:
        return JSONResponse(status_code=400, content={"error": "No active programme"})

    config = dict(req.goal_config) if req.goal_config is not None else dict(programme.get("goal_config") or {})
    if req.phases is not None:
        config.setdefault("phases", {})
        config["phases"].update(req.phases)
    if req.auto_switch is not None:
        config["auto_switch"] = req.auto_switch
    if req.current_phase is not None:
        if req.current_phase not in (config.get("phases") or {}):
            return JSONResponse(
                status_code=400,
                content={"error": f"Unknown phase '{req.current_phase}'"},
            )
        config["current_phase"] = req.current_phase

    if not config.get("phases"):
        return JSONResponse(
            status_code=400,
            content={"error": "goal_config must define at least one phase under 'phases'"},
        )

    updated = await fit.update_goal_config(programme["id"], config)
    goal = fit.resolve_goal(updated, None)
    return {
        "status": "updated",
        "current_phase": goal["current_phase"],
        "config": updated.get("goal_config"),
    }


@router.post("/weekly-checkin", dependencies=[Depends(require_auth)])
async def save_weekly_checkin():
    review = await fit.compute_weekly_review()
    if "error" in review:
        return JSONResponse(status_code=400, content=review)
    saved = await fit.save_weekly_checkin(review)
    return {"review": review, "checkin": saved}


# ── Reset-cut dashboard: local serve + on-demand refresh ────────────────
# These power the dashboard's Refresh button. They're unauthenticated on
# purpose: the API is local-only, and the public surge page is blocked from
# calling them by browser mixed-content rules — so only a same-origin LAN
# request (the locally-served page) actually reaches them. The `building`
# flag prevents concurrent rebuilds.

# Shared path (matches domains/fitness/dashboard_site.LOCAL_HTML) so the build
# process and this API service read/write the same file regardless of %TEMP%.
_DASH_HTML = Path(__file__).resolve().parents[1] / "data" / "reset-cut-dashboard.html"
_dash_state: dict = {"building": False, "generated_at": None}


@router.get("/dashboard/page", response_class=HTMLResponse)
async def dashboard_page():
    """Serve the latest built dashboard HTML over the LAN (refresh works here)."""
    if not _DASH_HTML.exists():
        try:
            from domains.fitness.dashboard_site import build_and_deploy
            res = await build_and_deploy(deploy=False)
            _dash_state["generated_at"] = res.get("generated_at")
        except Exception as e:
            return HTMLResponse(f"<h1>Dashboard not built yet</h1><p>{e}</p>", status_code=503)
    return HTMLResponse(_DASH_HTML.read_text(encoding="utf-8"))


@router.get("/dashboard/refresh/status")
async def dashboard_refresh_status():
    return _dash_state


async def _do_dashboard_refresh():
    _dash_state["building"] = True
    try:
        # Pull the freshest data from Withings + Garmin before rebuilding.
        try:
            from domains.nutrition.services.withings import get_weight
            await get_weight()
        except Exception as e:
            logger.warning(f"Dashboard refresh: Withings pull failed: {e}")
        try:
            from domains.peterbot.data_fetchers import _sync_garmin_to_supabase
            await _sync_garmin_to_supabase("dashboard-refresh")
        except Exception as e:
            logger.warning(f"Dashboard refresh: Garmin sync failed: {e}")
        from domains.fitness.dashboard_site import build_and_deploy
        res = await build_and_deploy(deploy=True)
        _dash_state["generated_at"] = res.get("generated_at")
        logger.info(f"Dashboard refreshed: {res.get('url')} @ {res.get('generated_at')} deployed={res.get('deployed')}")
    except Exception as e:
        logger.error(f"Dashboard refresh failed: {e}")
    finally:
        _dash_state["building"] = False


@router.post("/dashboard/refresh")
async def dashboard_refresh():
    """Trigger a rebuild from Garmin/Withings/Peter, then redeploy. Non-blocking."""
    if _dash_state["building"]:
        return {"status": "already_building", **_dash_state}
    asyncio.create_task(_do_dashboard_refresh())
    return {"status": "started"}


# ── Remote refresh relay poller ─────────────────────────────────────────
# The public surge page can't reach this LAN-only API, so its Refresh button
# POSTs sha256(passcode) to the `dashboard-refresh` Supabase Edge Function,
# which queues a row in dashboard_refresh_requests. This poller drains the
# queue: a row whose hash matches DASHBOARD_PASSCODE triggers the same
# rebuild+redeploy as the LAN button; anything else is marked rejected.

_RELAY_POLL_S = 20


def _relay_conf() -> tuple[str, dict] | None:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_KEY", "")
    if not url or not key or not os.getenv("DASHBOARD_PASSCODE"):
        return None
    return (f"{url}/rest/v1/dashboard_refresh_requests",
            {"apikey": key, "Authorization": f"Bearer {key}"})


async def _poll_refresh_relay():
    import hashlib
    import httpx
    conf = _relay_conf()
    if not conf:
        logger.warning("Dashboard relay poller disabled: SUPABASE_URL/KEY or DASHBOARD_PASSCODE missing")
        return
    rest, headers = conf
    want = hashlib.sha256(os.environ["DASHBOARD_PASSCODE"].encode()).hexdigest()
    logger.info("Dashboard relay poller started")
    while True:
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(rest, headers=headers,
                                params={"select": "id,pass_sha256", "processed_at": "is.null",
                                        "order": "requested_at.asc", "limit": "20"})
                r.raise_for_status()
                rows = r.json()
                if rows:
                    accepted = [row["id"] for row in rows if row["pass_sha256"] == want]
                    for row in rows:
                        ok = row["id"] in accepted
                        await c.patch(rest, headers=headers, params={"id": f"eq.{row['id']}"},
                                      json={"processed_at": datetime.now(timezone.utc).isoformat(),
                                            "status": "accepted" if ok else "rejected"})
                    if accepted:
                        logger.info(f"Dashboard relay: {len(accepted)} remote refresh request(s) accepted")
                        if not _dash_state["building"]:
                            asyncio.create_task(_do_dashboard_refresh())
                    if len(accepted) < len(rows):
                        logger.warning(f"Dashboard relay: rejected {len(rows) - len(accepted)} request(s) with a wrong passcode hash")
        except Exception as e:
            logger.warning(f"Dashboard relay poll failed: {e}")
        await asyncio.sleep(_RELAY_POLL_S)


@router.on_event("startup")
async def _start_refresh_relay():
    asyncio.create_task(_poll_refresh_relay())
