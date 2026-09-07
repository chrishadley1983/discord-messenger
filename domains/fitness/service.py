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
from domains.fitness.tdee import compute_tdee, TdeeResult, DEFAULT_PROTEIN_G_PER_KG
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

# Chris's biometric constants — mirrored from programme_start so the
# dashboard/weekly-review can recompute current targets without importing
# the one-shot initializer module.
CHRIS_HEIGHT_CM = 178
CHRIS_AGE_YEARS = 42
CHRIS_SEX = "male"

# Drift threshold: if current computed target differs from the stored
# programme target by more than this many kcal, flag for recalibration.
CALORIE_DRIFT_THRESHOLD = 80
PROTEIN_DRIFT_THRESHOLD_G = 10

PROGRAMMES_TABLE = "fitness_programmes"
EXERCISES_TABLE = "fitness_exercises"
SESSIONS_TABLE = "fitness_workout_sessions"
SETS_TABLE = "fitness_workout_sets"
MOBILITY_TABLE = "fitness_mobility_sessions"
CHECKINS_TABLE = "fitness_weekly_checkins"
CARDIO_TABLE = "fitness_cardio_sessions"
PLANS_TABLE = "fitness_training_plans"


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
    goal_config: dict | None = None,
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
    if goal_config is not None:
        body["goal_config"] = goal_config
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


async def update_goal_config(programme_id: str, goal_config: dict) -> dict:
    """Persist a new goal_config onto a programme row (Peter's goal editor)."""
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.patch(
            _url(PROGRAMMES_TABLE),
            headers=_write_headers(),
            params={"id": f"eq.{programme_id}"},
            json={"goal_config": goal_config},
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if rows else {"id": programme_id, "goal_config": goal_config}


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
# WEIGHT-ADAPTIVE TARGETS
# ══════════════════════════════════════════════════════════════════════

# BMI below this is no longer "overweight" — the default trigger for switching
# a programme out of its aggressive fat-loss phase. Stored per-programme in
# goal_config.auto_switch.below, so this is only the fallback.
HEALTHY_BMI_DEFAULT = 25.0

# Default fat-loss protein floor as g/kg of STARTING weight. Deliberately below
# the muscle-build multiplier — a satiety/retention floor while weight loss
# leads. Used only to seed a new programme's goal_config; once set it's a flat
# number that doesn't drift with weight.
FAT_LOSS_PROTEIN_G_PER_KG = 1.4


def bmi(weight_kg: float, height_cm: float = CHRIS_HEIGHT_CM) -> float:
    """Body Mass Index from weight (kg) + height (cm)."""
    h_m = height_cm / 100.0
    return weight_kg / (h_m * h_m) if h_m else 0.0


def _adaptive_phase(g_per_kg: float) -> dict:
    """Synthesise a phase dict for legacy programmes with no goal_config —
    mirrors the old weight-adaptive behaviour using the column factor."""
    return {
        "label": "Active cut",
        "focus": "Lose fat while protecting lean mass.",
        "protein": {"mode": "adaptive", "g_per_kg": g_per_kg},
        "protein_note": f"~{g_per_kg:g} g/kg bodyweight.",
        "rule": f"Hit ~{g_per_kg:g} g/kg protein.",
    }


def resolve_goal(
    programme: dict,
    current_weight_kg: float | None = None,
    *,
    height_cm: int = CHRIS_HEIGHT_CM,
) -> dict:
    """Resolve the active goal phase for a programme.

    The programme's ``goal_config`` is the single source of truth for the
    protein target and coaching framing. This reads it and applies any
    metric-based auto-switch (e.g. ``fat_loss`` -> ``muscle_build`` once BMI
    drops into the healthy range). The switch is forward-only.

    When ``goal_config`` is absent the result mirrors the legacy
    weight-adaptive behaviour using the programme's ``protein_g_per_kg``
    column, so old rows and callers keep working unchanged.

    Returns:
        {
          "current_phase": str,     # stored phase
          "effective_phase": str,   # phase after auto-switch
          "transitioned": bool,     # effective != current (switch fired)
          "phase": dict,            # resolved phase definition (label/focus/
                                    #   protein/protein_note/rule)
          "bmi": float | None,
          "config": dict | None,    # raw goal_config (None if legacy)
        }
    """
    config = programme.get("goal_config") or None
    col_factor = float(programme.get("protein_g_per_kg") or DEFAULT_PROTEIN_G_PER_KG)
    cur_bmi = bmi(current_weight_kg, height_cm) if current_weight_kg else None

    if not isinstance(config, dict) or not config.get("phases"):
        return {
            "current_phase": "default", "effective_phase": "default",
            "transitioned": False, "phase": _adaptive_phase(col_factor),
            "bmi": cur_bmi, "config": None,
        }

    phases = config.get("phases", {})
    current_phase = config.get("current_phase") or next(iter(phases), "")
    effective_phase = current_phase

    sw = config.get("auto_switch") or {}
    to_phase = sw.get("below_to") or sw.get("to_phase")
    if (
        sw.get("metric") == "bmi" and to_phase in phases and to_phase != current_phase
        and cur_bmi is not None and sw.get("below") is not None
        and cur_bmi < float(sw["below"])
    ):
        effective_phase = to_phase

    phase = dict(phases.get(effective_phase) or phases.get(current_phase) or {})
    # Backfill the adaptive multiplier from the column when the phase omits it,
    # so "the old multiple" always tracks the programme's protein_g_per_kg.
    pr = dict(phase.get("protein") or {})
    if pr.get("mode") == "adaptive" and pr.get("g_per_kg") is None:
        pr["g_per_kg"] = col_factor
        phase["protein"] = pr

    return {
        "current_phase": current_phase,
        "effective_phase": effective_phase,
        "transitioned": effective_phase != current_phase,
        "phase": phase,
        "bmi": cur_bmi,
        "config": config,
    }


def default_goal_config(
    start_weight_kg: float,
    *,
    muscle_g_per_kg: float = DEFAULT_PROTEIN_G_PER_KG,
    switch_bmi: float = HEALTHY_BMI_DEFAULT,
) -> dict:
    """Build the default fat-loss-first goal_config for a new programme.

    The ``fat_loss`` phase pins protein to a flat floor (computed once from the
    starting weight, so weight loss leads); it auto-switches to the adaptive
    ``muscle_build`` multiplier once BMI drops below ``switch_bmi``. Editable
    later via PUT /fitness/goal.
    """
    floor = int(round((FAT_LOSS_PROTEIN_G_PER_KG * start_weight_kg) / 5) * 5)
    return {
        "current_phase": "fat_loss",
        "auto_switch": {"metric": "bmi", "below": switch_bmi, "to_phase": "muscle_build"},
        "phases": {
            "fat_loss": {
                "label": "Fat loss first",
                "focus": "Weight loss is the priority — the calorie deficit leads; protein is a satiety/retention floor, not a max.",
                "protein": {"mode": "fixed", "g": floor},
                "protein_note": f"{floor} g floor — enough to stay full and hold some muscle; not maxed, because fat loss comes first.",
                "rule": f"Hit ~{floor} g protein and stay under calories — protein is a floor, not the headline.",
            },
            "muscle_build": {
                "label": "Build muscle",
                "focus": "Healthy weight reached — shift toward protecting and building lean mass.",
                "protein": {"mode": "adaptive", "g_per_kg": muscle_g_per_kg},
                "protein_note": f"~{muscle_g_per_kg:g} g/kg — high protein to drive lean-mass growth now you're at a healthy weight.",
                "rule": f"Hit protein (~{muscle_g_per_kg:g} g/kg) — the priority for building muscle.",
            },
        },
    }


def compute_current_targets(
    programme: dict,
    current_weight_kg: float,
    avg_steps: float,
    *,
    height_cm: int = CHRIS_HEIGHT_CM,
    age_years: int = CHRIS_AGE_YEARS,
    sex: str = CHRIS_SEX,
    deficit_kcal: int | None = None,
    protein_g_per_kg: float | None = None,
) -> TdeeResult:
    """Recompute TDEE / calorie / protein targets from latest weight.

    BMR is ~10 kcal per kg, so every 5kg lost shaves ~50 kcal off BMR. At a
    1.6 activity multiplier that's ~80 kcal off TDEE, which is enough to
    stall fat loss if the target isn't refreshed. Call this any time you
    need a current target rather than the stored programme snapshot.

    Args:
        programme: Active programme row (just used for defaults if deficit
            needs to be read later; currently deficit is the kwarg).
        current_weight_kg: Latest trend weight (EMA or 7d SMA preferred).
        avg_steps: 7-day average step count.
        height_cm / age_years / sex: Biometric constants (default Chris).
        deficit_kcal: Daily deficit to apply (default 550).

    Returns:
        TdeeResult with live BMR, TDEE, target_calories, target_protein_g.
    """
    # Deficit defaults to the programme's own setting (so a deliberately
    # aggressive plan isn't overridden by the generic 550 default), falling
    # back to that default when the programme doesn't specify. This keeps the
    # weight-adaptive calories aligned with the plan while still auto-adjusting
    # down as BMR drops with weight loss.
    resolved_deficit = (
        deficit_kcal if deficit_kcal is not None
        else int(programme.get("deficit_kcal") or 550)
    )

    # Protein comes from the resolved goal phase: a 'fixed' phase pins it to a
    # flat number (e.g. 125 g during fat-loss); an 'adaptive' phase scales it
    # by the g/kg multiplier. An explicit protein_g_per_kg override still wins
    # (back-compat for callers that force a multiplier).
    fixed_protein_g: int | None = None
    if protein_g_per_kg is not None:
        resolved_factor = protein_g_per_kg
    else:
        protein_spec = resolve_goal(
            programme, current_weight_kg, height_cm=height_cm
        )["phase"].get("protein", {})
        if protein_spec.get("mode") == "fixed" and protein_spec.get("g") is not None:
            fixed_protein_g = int(protein_spec["g"])
            resolved_factor = DEFAULT_PROTEIN_G_PER_KG  # unused when fixed
        else:
            resolved_factor = float(
                protein_spec.get("g_per_kg")
                or programme.get("protein_g_per_kg")
                or DEFAULT_PROTEIN_G_PER_KG
            )

    return compute_tdee(
        weight_kg=current_weight_kg,
        height_cm=height_cm,
        age_years=age_years,
        avg_steps=avg_steps,
        sex=sex,
        deficit_kcal=resolved_deficit,
        protein_g_per_kg=resolved_factor,
        fixed_protein_g=fixed_protein_g,
    )


def targets_drifted(programme: dict, live: TdeeResult) -> dict:
    """Compare stored programme targets against freshly-computed ones.

    Returns a dict with the deltas and a boolean flag indicating whether
    the drift is large enough to warrant formal recalibration.
    """
    cal_delta = live.target_calories - int(programme["daily_calorie_target"])
    pro_delta = live.target_protein_g - int(programme["daily_protein_g"])
    drifted = (
        abs(cal_delta) >= CALORIE_DRIFT_THRESHOLD
        or abs(pro_delta) >= PROTEIN_DRIFT_THRESHOLD_G
    )
    return {
        "stored_calories": int(programme["daily_calorie_target"]),
        "live_calories": live.target_calories,
        "calorie_delta": cal_delta,
        "stored_protein_g": int(programme["daily_protein_g"]),
        "live_protein_g": live.target_protein_g,
        "protein_delta": pro_delta,
        "drifted": drifted,
    }


def compute_plan_maths(
    programme: dict,
    current_weight: float | None,
    slope_kg_per_week: float | None,
    today: date | None = None,
) -> dict:
    """Honest plan arithmetic: where the plan line is, the gap to it, the rate
    required from here, and where the current rate actually lands.

    This is the single source of truth for "am I on track" — the dashboard
    hero, the AI summary facts, the advisor and the Monday check-in all read
    from here so they can't disagree or soften independently.

    on_track tiers (worst first): off_track > well_behind > behind > settling
    > on_track > ahead. The gap thresholds are vs the linearly-interpolated
    weekly target line.
    """
    today = today or _today()
    end = date.fromisoformat(programme["end_date"])
    start_w = float(programme["start_weight_kg"])
    target_w = float(programme["target_weight_kg"])
    dur = int(programme["duration_weeks"])
    wk = week_number(programme, today)
    eff_week = min(max(wk, 1), dur)
    target_this_week = round(start_w - (start_w - target_w) * (eff_week / dur), 1)
    days_remaining = max(0, (end - today).days)
    weeks_remaining = max(days_remaining / 7.0, 0.15)

    out: dict[str, Any] = {
        "target_this_week": target_this_week,
        "weeks_remaining": round(weeks_remaining, 1),
        "gap_vs_line_kg": None,
        "required_kg_per_week": None,
        "required_pct_bw_per_week": None,
        "required_rate_unsafe": False,
        "actual_kg_per_week": round(slope_kg_per_week, 2) if slope_kg_per_week is not None else None,
        "projected_end_weight": None,
        "projected_finish_date": None,
        "on_track": "neutral",
        "on_track_label": "Tracking",
    }
    if wk < 1:
        out["on_track"], out["on_track_label"] = "pre_start", "Starts Monday"
        return out
    if current_weight is None:
        return out

    gap = round(current_weight - target_this_week, 1)
    required = (current_weight - target_w) / weeks_remaining
    req_pct = required / current_weight * 100
    out["gap_vs_line_kg"] = gap
    out["required_kg_per_week"] = round(required, 2)
    out["required_pct_bw_per_week"] = round(req_pct, 2)
    # Sustained loss above ~1% of body weight per week costs muscle — if the
    # plan now demands that, the plan itself is broken and needs re-baselining.
    out["required_rate_unsafe"] = req_pct > 1.0

    if slope_kg_per_week is not None:
        out["projected_end_weight"] = round(current_weight + slope_kg_per_week * weeks_remaining, 1)
        if slope_kg_per_week < -0.05:
            weeks_to_target = (current_weight - target_w) / -slope_kg_per_week
            if 0 < weeks_to_target < 520:
                out["projected_finish_date"] = (
                    today + timedelta(days=round(weeks_to_target * 7))
                ).isoformat()

    if gap <= -0.2:
        out["on_track"], out["on_track_label"] = "ahead", "Ahead of plan"
    elif gap <= 0.3:
        out["on_track"], out["on_track_label"] = "on_track", "On track"
    elif wk <= 2:
        # Early programme: weight noise dwarfs a small miss off a micro-target.
        out["on_track"], out["on_track_label"] = "settling", "Settling in"
    elif gap <= 1.0:
        out["on_track"], out["on_track_label"] = "behind", "Behind — tighten up"
    elif gap <= 2.5:
        out["on_track"], out["on_track_label"] = "well_behind", "Well behind — act now"
    else:
        out["on_track"], out["on_track_label"] = "off_track", "Off track — plan needs resetting"
    return out


async def recalibrate_programme(
    programme: dict,
    current_weight_kg: float,
    avg_steps: float,
    *,
    deficit_kcal: int | None = None,
) -> dict:
    """Recompute targets from the latest weight and persist them.

    Updates the programme row in-place (new TDEE, calories, protein) and
    returns both the old and new target values so callers can log the
    delta / notify Chris.
    """
    live = compute_current_targets(
        programme, current_weight_kg, avg_steps, deficit_kcal=deficit_kcal
    )
    goal = resolve_goal(programme, current_weight_kg)
    old = {
        "tdee_kcal": int(programme["tdee_kcal"]),
        "daily_calorie_target": int(programme["daily_calorie_target"]),
        "daily_protein_g": int(programme["daily_protein_g"]),
    }
    new = {
        "tdee_kcal": live.tdee,
        "daily_calorie_target": live.target_calories,
        "daily_protein_g": live.target_protein_g,
    }

    # If the goal phase auto-switched (e.g. BMI dropped into the healthy range
    # so protein flips from a flat fat-loss floor to the adaptive muscle-build
    # multiplier), persist the new current_phase so the change is sticky and
    # can be announced to Chris.
    phase_changed = None
    if goal["transitioned"] and goal["config"]:
        new_config = dict(goal["config"])
        new_config["current_phase"] = goal["effective_phase"]
        new["goal_config"] = new_config
        phase_changed = {
            "from": goal["current_phase"],
            "to": goal["effective_phase"],
            "label": goal["phase"].get("label"),
            "bmi": round(goal["bmi"], 1) if goal["bmi"] is not None else None,
        }

    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.patch(
            _url(PROGRAMMES_TABLE),
            headers=_write_headers(),
            params={"id": f"eq.{programme['id']}"},
            json=new,
        )
        resp.raise_for_status()
        updated = resp.json()[0] if resp.json() else {**programme, **new}

    # Keep the accountability goal rows in lockstep — they used to drift for
    # months (wrong session count, stale protein target, expired weight goal).
    goals_synced = await sync_accountability_goals(updated)

    return {
        "programme": updated,
        "old": old,
        "new": new,
        "weight_used_kg": current_weight_kg,
        "steps_avg_used": int(avg_steps),
        "bmr": live.bmr,
        "activity_factor": live.activity_factor,
        "deficit_kcal": live.deficit_kcal,
        "phase_changed": phase_changed,
        "effective_phase": goal["effective_phase"],
        "goals_synced": goals_synced,
    }


async def sync_accountability_goals(programme: dict) -> list[dict]:
    """Patch active accountability_goals rows to match the programme's targets.

    Matches rows by auto_source (the stable key) and only writes when the value
    actually differs, so repeated recalibrations are no-ops. Returns the list of
    changes applied (empty = everything already in sync).
    """
    targets = {
        "nutrition_calories": {
            "target_value": int(programme["daily_calorie_target"]),
            "title": f"Daily calories ≤ {int(programme['daily_calorie_target'])}",
        },
        "nutrition_protein": {
            "target_value": int(programme["daily_protein_g"]),
            "title": f"Protein ≥ {int(programme['daily_protein_g'])}g daily",
        },
        "fitness_strength_week": {
            "target_value": int(programme["weekly_strength_sessions"]),
            "title": f"{int(programme['weekly_strength_sessions'])} strength sessions per week",
        },
        "garmin_steps": {
            "target_value": int(programme["daily_steps_target"]),
            "title": f"{int(programme['daily_steps_target']) // 1000}k steps daily",
        },
        "weight": {
            "target_value": float(programme["target_weight_kg"]),
            "deadline": programme["end_date"],
        },
    }
    changes: list[dict] = []
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(
            f"{SUPABASE_URL}/rest/v1/accountability_goals",
            headers=_read_headers(),
            params={
                "select": "id,title,target_value,deadline,auto_source",
                "status": "eq.active",
                "user_id": "eq.chris",
            },
        )
        resp.raise_for_status()
        for g in resp.json():
            want = targets.get(g.get("auto_source") or "")
            if not want:
                continue
            patch = {}
            if float(g.get("target_value") or 0) != float(want["target_value"]):
                patch["target_value"] = want["target_value"]
            if want.get("title") and g.get("title") != want["title"]:
                patch["title"] = want["title"]
            if want.get("deadline") and g.get("deadline") != want["deadline"]:
                patch["deadline"] = want["deadline"]
            if not patch:
                continue
            r = await c.patch(
                f"{SUPABASE_URL}/rest/v1/accountability_goals",
                headers=_write_headers(),
                params={"id": f"eq.{g['id']}"},
                json=patch,
            )
            if r.status_code in (200, 204):
                changes.append({"goal_id": g["id"], "auto_source": g["auto_source"], **patch})
            else:
                logger.warning(f"Goal sync failed for {g['id']}: {r.status_code} {r.text}")
    return changes


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

    `sets` is a list of {exercise_slug, set_no, reps, hold_s, weight_kg, rir,
    failed, target_reps, notes, [exercise_name, category, muscle_group,
    equipment]}. Exercise slug is resolved to exercise_id before insert;
    unknown slugs are CREATED in the library (never silently dropped) so
    off-plan work is captured and the plan can adapt to it.
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
            ex_map = await ensure_exercises(sets)
            set_rows = []
            for s in sets:
                ex = ex_map.get(s["exercise_slug"])
                if not ex:
                    logger.warning(f"Unknown exercise slug (create failed): {s['exercise_slug']}")
                    continue
                set_rows.append({
                    "session_id": session["id"],
                    "exercise_id": ex["id"],
                    "set_no": s.get("set_no", 1),
                    "reps": s.get("reps"),
                    "hold_s": s.get("hold_s"),
                    "weight_kg": s.get("weight_kg"),
                    "rir": s.get("rir"),
                    "failed": bool(s.get("failed") or False),
                    "target_reps": s.get("target_reps"),
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


# Fixed 10-minute daily mobility flow. Order and durations chosen to
# warm up spine → open hips → release glutes → reset. Total ~9 min of
# active stretching + 1 min of transitions. All moves exist in the
# fitness_exercises table (mobility category) and are fetched by slug
# so the frontend can cross-reference for instructions / videos.
DAILY_MOBILITY_ROUTINE: list[dict] = [
    {"slug": "neck-rolls",              "duration_s": 30,  "note": "Slow circles each way"},
    {"slug": "cat-cow",                 "duration_s": 60,  "note": "10 reps, breathe with movement"},
    {"slug": "thoracic-twist",          "duration_s": 60,  "note": "5 reps each side"},
    {"slug": "worlds-greatest-stretch", "duration_s": 90,  "note": "3 reps each side"},
    {"slug": "couch-stretch",           "duration_s": 90,  "note": "45s each side"},
    {"slug": "pigeon-pose",             "duration_s": 120, "note": "60s each side — breathe deep"},
    {"slug": "childs-pose",             "duration_s": 60,  "note": "Full-body reset"},
]


async def get_mobility_routine() -> dict:
    """Return the fixed 10-minute daily mobility flow.

    Joins the hardcoded routine against the exercise library so the
    frontend gets name, form cue, instructions, video and equipment in
    the same payload — no extra lookups needed.
    """
    slugs = [step["slug"] for step in DAILY_MOBILITY_ROUTINE]
    library = await get_exercises_by_slugs(slugs)
    moves: list[dict] = []
    for step in DAILY_MOBILITY_ROUTINE:
        ex = library.get(step["slug"])
        if not ex:
            continue
        moves.append({
            "slug": step["slug"],
            "name": ex["name"],
            "duration_s": step["duration_s"],
            "note": step["note"],
            "form_cue": ex.get("form_cue"),
            "instructions": ex.get("instructions"),
            "video_url": ex.get("video_url"),
            "equipment": ex.get("equipment"),
            "muscle_group": ex.get("muscle_group"),
        })
    total_s = sum(m["duration_s"] for m in moves)
    return {
        "name": "Daily 10-minute mobility flow",
        "total_duration_s": total_s,
        "total_duration_min": round(total_s / 60, 1),
        "move_count": len(moves),
        "moves": moves,
    }


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


async def _live_steps_today(steps_history: list[dict]) -> float:
    """Today's step count — live from Garmin when reachable, otherwise
    the most recent row in `garmin_daily_summary` (which is up to 1 day stale
    because the sync job only runs once a morning)."""
    today_iso = _today().isoformat()
    try:
        from domains.nutrition.services import get_steps
        live = await get_steps()
        if live and live.get("steps") is not None and live.get("date") == today_iso:
            return float(live["steps"])
    except Exception as e:
        logger.warning(f"Live Garmin step fetch failed, falling back to DB: {e}")
    # Fall back to whatever the sync job last wrote.
    for row in reversed(steps_history):
        if row.get("date") == today_iso:
            return float(row["value"])
    return float(steps_history[-1]["value"]) if steps_history else 0.0


async def fetch_trends_series(days: int = 90) -> dict:
    """Build the Trends-tab payload: weight + Garmin time-series over N days.

    Returns:
        {
            "series": {
                weight:      [{date, value}],
                steps:       [{date, value}],
                sleep_score: [{date, value}],
                sleep_hours: [{date, value}],
                resting_hr:  [{date, value}],
                hrv:         [{date, value}],
                stress:      [{date, value}],
            },
            "summary": {
                "<metric>": {"current": float|None, "prior": float|None, "delta_pct": float|None}
            }
        }

    Each series drops nulls so the UI can plot directly. `summary` averages the
    most recent 14 days vs the prior 14 days for headline deltas.
    """
    cutoff = (_today() - timedelta(days=days)).isoformat()
    # Weight
    async with httpx.AsyncClient(timeout=10) as c:
        w_resp = await c.get(
            f"{SUPABASE_URL}/rest/v1/weight_readings",
            headers=_read_headers(),
            params={
                "select": "measured_at,weight_kg",
                "user_id": "eq.chris",
                "measured_at": f"gte.{cutoff}T00:00:00Z",
                "order": "measured_at.asc",
            },
        )
        w_resp.raise_for_status()
        weight_rows = w_resp.json()
        # Garmin (single round-trip for all fields)
        g_resp = await c.get(
            f"{SUPABASE_URL}/rest/v1/garmin_daily_summary",
            headers=_read_headers(),
            params={
                "select": "date,steps,sleep_score,sleep_hours,resting_hr,hrv_weekly_avg,hrv_last_night,avg_stress",
                "user_id": "eq.chris",
                "date": f"gte.{cutoff}",
                "order": "date.asc",
            },
        )
        g_resp.raise_for_status()
        garmin_rows = g_resp.json()

    def _pick(rows: list[dict], field_name: str, date_field: str = "date") -> list[dict]:
        out: list[dict] = []
        for r in rows:
            v = r.get(field_name)
            if v is None:
                continue
            day = str(r[date_field])[:10]
            out.append({"date": day, "value": float(v)})
        return out

    weight_series = [
        {"date": str(r["measured_at"])[:10], "value": float(r["weight_kg"])}
        for r in weight_rows
        if r.get("weight_kg") is not None
    ]

    series = {
        "weight": weight_series,
        "steps": _pick(garmin_rows, "steps"),
        "sleep_score": _pick(garmin_rows, "sleep_score"),
        "sleep_hours": _pick(garmin_rows, "sleep_hours"),
        "resting_hr": _pick(garmin_rows, "resting_hr"),
        "hrv": _pick(garmin_rows, "hrv_last_night"),
        "stress": _pick(garmin_rows, "avg_stress"),
    }

    # Summary: last 14d avg vs prior 14d avg.
    def _summarise(points: list[dict]) -> dict:
        if not points:
            return {"current": None, "prior": None, "delta_pct": None, "n": 0}
        today_ord = _today().toordinal()
        recent = [p["value"] for p in points if today_ord - date.fromisoformat(p["date"]).toordinal() < 14]
        prior = [
            p["value"] for p in points
            if 14 <= today_ord - date.fromisoformat(p["date"]).toordinal() < 28
        ]
        r_avg = round(sum(recent) / len(recent), 2) if recent else None
        p_avg = round(sum(prior) / len(prior), 2) if prior else None
        delta_pct: float | None = None
        if r_avg is not None and p_avg is not None and p_avg != 0:
            delta_pct = round((r_avg - p_avg) / p_avg * 100, 1)
        return {"current": r_avg, "prior": p_avg, "delta_pct": delta_pct, "n": len(points)}

    summary = {name: _summarise(pts) for name, pts in series.items()}
    return {"series": series, "summary": summary}


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
    prog_start = date.fromisoformat(programme["start_date"]) if programme else None
    trend = compute_trend(weight_history, programme_start=prog_start)

    nutrition = await fetch_nutrition_today()
    steps_history = await fetch_steps_history(7)
    steps_today = await _live_steps_today(steps_history)
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

        # Weight-adaptive targets: recompute TDEE from current trend weight
        # so the dashboard shows what Chris should eat TODAY, not what the
        # programme row captured at week 0. Fall back to stored values if
        # there's no trend weight yet (day 1 of the programme).
        current_weight = trend.trend_7d or trend.latest_raw
        if current_weight and steps_avg > 0:
            live = compute_current_targets(
                programme, current_weight, max(steps_avg, programme["daily_steps_target"])
            )
            result["nutrition"]["target_calories"] = live.target_calories
            result["nutrition"]["target_protein"] = live.target_protein_g
            result["live_targets"] = {
                "bmr": live.bmr,
                "activity_factor": live.activity_factor,
                "tdee": live.tdee,
                "target_calories": live.target_calories,
                "target_protein_g": live.target_protein_g,
                "weight_used_kg": round(current_weight, 2),
            }
            drift = targets_drifted(programme, live)
            result["target_drift"] = drift
            if drift["drifted"]:
                flags.append(
                    f"TARGETS DRIFTED — stored {drift['stored_calories']} kcal / "
                    f"live {drift['live_calories']} kcal (Δ {drift['calorie_delta']:+d}). "
                    "Run /fitness/programme/recalibrate."
                )
        else:
            result["nutrition"]["target_calories"] = programme["daily_calorie_target"]
            result["nutrition"]["target_protein"] = programme["daily_protein_g"]

        result["steps"]["target"] = programme["daily_steps_target"]
        result["strength_this_week"]["target"] = programme["weekly_strength_sessions"]

        # Active goal phase — the source of truth for the protein target +
        # coaching framing, so skills/dashboard never hardcode "180g / protect
        # muscle". Auto-switches (e.g. fat_loss -> muscle_build at healthy BMI).
        goal = resolve_goal(programme, current_weight)
        _gp = goal["phase"].get("protein") or {}
        result["goal"] = {
            "phase": goal["effective_phase"],
            "label": goal["phase"].get("label"),
            "focus": goal["phase"].get("focus"),
            "protein_note": goal["phase"].get("protein_note"),
            "rule": goal["phase"].get("rule"),
            "protein_mode": _gp.get("mode"),
            "protein_g_per_kg": _gp.get("g_per_kg"),
            "bmi": round(goal["bmi"], 1) if goal["bmi"] is not None else None,
        }

        # Cumulative loss
        if trend.trend_7d is not None and programme.get("start_weight_kg"):
            loss = float(programme["start_weight_kg"]) - trend.trend_7d
            result["weight"]["cumulative_loss_kg"] = round(loss, 2)
            pct = loss / (float(programme["start_weight_kg"]) - float(programme["target_weight_kg"])) * 100
            result["weight"]["progress_pct"] = round(pct, 1)

        # Today's prescribed workout (plan-aware when split == 'plan')
        if 1 <= wk <= programme["duration_weeks"]:
            week_sessions = await week_sessions_for(programme, wk)
            dow = _today().weekday()
            today_session = next((s for s in week_sessions if s.day_of_week == dow), None)
            if today_session:
                result["today_workout"] = session_to_dict(today_session)
            else:
                result["today_workout"] = None

        # Plan maths — the honest picture (gap vs line, required rate,
        # projection). Single source of truth for every check-in surface.
        plan = compute_plan_maths(programme, current_weight, trend.slope_kg_per_week)
        result["plan"] = plan

        # Flags — compare against live targets (not stored ones) so the
        # dashboard reflects the adaptive plan.
        live_cal = result["nutrition"]["target_calories"]
        live_pro = result["nutrition"]["target_protein"]
        gap = plan.get("gap_vs_line_kg") or 0
        if plan["on_track"] == "off_track":
            req = plan.get("required_kg_per_week")
            flags.append(
                f"OFF TRACK — {gap:+.1f} kg vs the plan line; hitting "
                f"{programme['target_weight_kg']:g} kg by {programme['end_date']} now needs "
                f"{req:.2f} kg/wk"
                + (" (unsafe — re-baseline the plan)" if plan["required_rate_unsafe"] else "")
            )
        elif plan["on_track"] in ("behind", "well_behind"):
            flags.append(f"BEHIND PLAN — {gap:+.1f} kg vs this week's line")
        if trend.stalled:
            # Scale the correction with how far behind the line we are.
            if gap > 2:
                flags.append("WEIGHT TREND STALLED — drop 200 kcal + add 3k steps, and review what isn't being logged")
            else:
                flags.append("WEIGHT TREND STALLED — drop 100 kcal + add 2k steps")
        if nutrition["calories"] > live_cal * 1.1:
            flags.append(f"Over calorie target by {int(nutrition['calories'] - live_cal)} kcal")
        if nutrition["protein_g"] < live_pro * 0.8 and datetime.now(UK_TZ).hour >= 18:
            flags.append(f"Behind on protein: {int(nutrition['protein_g'])}/{live_pro}g")
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
    strength_done = len([s for s in sessions if s["session_type"] not in ("mobility", "rest", "cardio")])

    # Plan-driven training block (Phase 2): cardio, progressions, stalls, Garmin HR
    training_block: dict | None = None
    strength_target = programme["weekly_strength_sessions"]
    if programme.get("split") == "plan":
        try:
            training_block = await training_week_summary(today)
            strength_target = training_block["strength"]["target"]
            cardio_rows = await get_cardio_in_range(week_start, week_end)
            hrs = [int(c["avg_hr"]) for c in cardio_rows if c.get("avg_hr")]
            training_block["cardio"]["avg_hr"] = round(sum(hrs) / len(hrs)) if hrs else None
            training_block["cardio"]["garmin_matched"] = sum(1 for c in cardio_rows if c.get("garmin_activity_id"))
            training_block["cardio"]["sessions"] = [
                {"date": c["session_date"], "modality": c["modality"], "intensity": c["intensity"],
                 "minutes": c.get("duration_min"), "avg_hr": c.get("avg_hr"), "pain": bool(c.get("pain_flag"))}
                for c in cardio_rows
            ]
        except Exception as e:
            logger.warning(f"weekly review training block failed: {e}")

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

    # Live targets recomputed from current weight. Weekly review is the
    # natural recalibration checkpoint — if BMR has dropped enough that the
    # live target differs from what's stored, we surface that as a
    # recommended adjustment rather than a stall reaction.
    avg_steps_week = (
        sum(p["value"] for p in steps_week) / len(steps_week) if steps_week else 0
    )
    live: TdeeResult | None = None
    drift: dict | None = None
    if this_avg is not None:
        live = compute_current_targets(
            programme,
            this_avg,
            max(avg_steps_week, programme["daily_steps_target"]),
        )
        drift = targets_drifted(programme, live)

    # Adjustment logic
    next_cal = target_cal
    next_steps = steps_target
    adjustment = "Continue current plan"
    recalibrate_recommended = False

    if trend.stalled:
        next_cal = target_cal - 100
        next_steps = steps_target + 2000
        adjustment = f"STALL: -100 kcal ({next_cal}) and +2k steps ({next_steps})"
    elif drift and drift["drifted"]:
        # Weight has dropped (or risen) enough that BMR-derived targets
        # no longer match the stored plan. Recommend formal recalibration.
        next_cal = live.target_calories  # type: ignore[union-attr]
        next_steps = steps_target
        recalibrate_recommended = True
        adjustment = (
            f"RECALIBRATE: weight {this_avg:.1f}kg → new target {next_cal} kcal "
            f"(Δ {drift['calorie_delta']:+d}). POST /fitness/programme/recalibrate."
        )

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
            "target": strength_target,
        },
        "training": training_block,
        "mobility": {
            "days_hit": mobility_days,
            "target": 7,
        },
        "adjustment": {
            "next_calorie_target": next_cal,
            "next_steps_target": next_steps,
            "note": adjustment,
            "recalibrate_recommended": recalibrate_recommended,
        },
        "live_targets": (
            {
                "bmr": live.bmr,
                "activity_factor": live.activity_factor,
                "tdee": live.tdee,
                "target_calories": live.target_calories,
                "target_protein_g": live.target_protein_g,
                "weight_used_kg": round(this_avg, 2) if this_avg else None,
            }
            if live else None
        ),
        "target_drift": drift,
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


# ══════════════════════════════════════════════════════════════════════
# GYM TRAINING LOG + ADAPTIVE PLAN (Sep 2026)
# ══════════════════════════════════════════════════════════════════════
# Pure logic lives in domains/fitness/training_plan.py; this section is I/O.

from domains.fitness import training_plan as tp  # noqa: E402


async def ensure_exercises(sets: list[dict]) -> dict[str, dict]:
    """Resolve slugs -> exercise rows, creating any that don't exist yet.

    A set may carry `exercise_name`, `category`, `muscle_group`, `equipment`
    hints for the auto-created row. Category falls back to 'other'.
    """
    slugs = list({s["exercise_slug"] for s in sets})
    ex_map = await get_exercises_by_slugs(slugs)
    missing = [s for s in slugs if s not in ex_map]
    if not missing:
        return ex_map
    hints = {s["exercise_slug"]: s for s in sets}
    rows = []
    for slug in missing:
        h = hints[slug]
        measurement = "hold_seconds" if (h.get("hold_s") and not h.get("reps")) else "reps"
        rows.append({
            "name": h.get("exercise_name") or slug.replace("-", " ").title(),
            "slug": slug,
            "category": h.get("category") or "other",
            "muscle_group": h.get("muscle_group") or "unknown",
            "measurement": measurement,
            "default_sets": 3,
            "default_reps": h.get("target_reps") or h.get("reps") or 10,
            "equipment": h.get("equipment"),
            "progression_note": "Auto-added from a logged session - double progression by default",
        })
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(_url(EXERCISES_TABLE), headers=_write_headers(), json=rows)
        if r.status_code >= 300:
            logger.warning(f"ensure_exercises insert failed: {r.status_code} {r.text}")
    return await get_exercises_by_slugs(slugs)


async def get_exercise_meta(slugs: list[str]) -> dict[str, dict]:
    if not slugs:
        return {}
    return await get_exercises_by_slugs(slugs)


async def get_sets_history(days: int = 56, slugs: list[str] | None = None) -> dict[str, list[dict]]:
    """Logged sets grouped by exercise slug, newest session first.

    Returns {slug: [{date, session_type, session_id, sets: [{set_no, reps, weight_kg, rir, failed, target_reps}]}]}.
    """
    cutoff = (_today() - timedelta(days=days)).isoformat()
    params = {
        "select": "set_no,reps,hold_s,weight_kg,rir,failed,target_reps,notes,"
                  "exercise:fitness_exercises!inner(slug,name,load_step_kg),"
                  "session:fitness_workout_sessions!inner(id,session_date,session_type,user_id)",
        "session.user_id": "eq.chris",
        "session.session_date": f"gte.{cutoff}",
        "order": "set_no.asc",
    }
    if slugs:
        params["exercise.slug"] = f"in.({','.join(slugs)})"
    async with httpx.AsyncClient(timeout=15) as c:
        resp = await c.get(_url(SETS_TABLE), headers=_read_headers(), params=params)
        resp.raise_for_status()
        rows = resp.json()

    grouped: dict[str, dict[str, dict]] = {}
    for r in rows:
        ex, sess = r.get("exercise") or {}, r.get("session") or {}
        if not ex or not sess:
            continue
        slug = ex["slug"]
        key = sess["id"]
        entry = grouped.setdefault(slug, {}).setdefault(key, {
            "date": sess["session_date"], "session_type": sess["session_type"],
            "session_id": key, "sets": [],
        })
        entry["sets"].append({
            "set_no": r["set_no"], "reps": r.get("reps"), "hold_s": r.get("hold_s"),
            "weight_kg": float(r["weight_kg"]) if r.get("weight_kg") is not None else None,
            "rir": r.get("rir"), "failed": bool(r.get("failed")), "target_reps": r.get("target_reps"),
        })
    out: dict[str, list[dict]] = {}
    for slug, by_session in grouped.items():
        sessions = sorted(by_session.values(), key=lambda e: (str(e["date"]), e["session_id"]), reverse=True)
        for e in sessions:
            e["sets"].sort(key=lambda s: s["set_no"])
        out[slug] = sessions
    return out


async def get_workouts_with_sets(days: int = 28) -> list[dict]:
    """Sessions (newest first) with their sets embedded - the history endpoint."""
    cutoff = (_today() - timedelta(days=days)).isoformat()
    async with httpx.AsyncClient(timeout=15) as c:
        resp = await c.get(
            _url(SESSIONS_TABLE), headers=_read_headers(),
            params={
                "select": "*,sets:fitness_workout_sets(set_no,reps,hold_s,weight_kg,rir,failed,target_reps,notes,"
                          "exercise:fitness_exercises(slug,name))",
                "user_id": "eq.chris",
                "session_date": f"gte.{cutoff}",
                "order": "session_date.desc",
            },
        )
        resp.raise_for_status()
        rows = resp.json()
    for r in rows:
        r["sets"] = sorted(
            r.get("sets") or [],
            key=lambda s: ((s.get("exercise") or {}).get("slug", ""), int(s.get("set_no") or 0)),
        )
    return rows


# -- Cardio -------------------------------------------------------------

async def log_cardio(
    *,
    modality: str,
    intensity: str = "easy",
    session_date: str | None = None,
    duration_min: int | None = None,
    protocol: list[dict] | None = None,
    peak_level: float | None = None,
    work_level: float | None = None,
    avg_hr: int | None = None,
    max_hr: int | None = None,
    calories: int | None = None,
    distance_m: int | None = None,
    rpe: int | None = None,
    limiter: str | None = None,
    pain_flag: bool = False,
    notes: str | None = None,
    garmin_activity_id: str | None = None,
    programme_id: str | None = None,
) -> dict:
    body = {
        "modality": modality, "intensity": intensity,
        "session_date": session_date or _today().isoformat(),
        "duration_min": duration_min, "protocol": protocol,
        "peak_level": peak_level, "work_level": work_level,
        "avg_hr": avg_hr, "max_hr": max_hr, "calories": calories, "distance_m": distance_m,
        "rpe": rpe, "limiter": limiter, "pain_flag": bool(pain_flag), "notes": notes,
        "garmin_activity_id": garmin_activity_id, "programme_id": programme_id,
    }
    async with httpx.AsyncClient(timeout=15) as c:
        resp = await c.post(_url(CARDIO_TABLE), headers=_write_headers(), json=body)
        resp.raise_for_status()
        return resp.json()[0]


async def get_cardio_in_range(start: date, end: date) -> list[dict]:
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(
            _url(CARDIO_TABLE), headers=_read_headers(),
            params={
                "select": "*", "user_id": "eq.chris",
                "session_date": f"gte.{start.isoformat()}",
                "and": f"(session_date.lte.{end.isoformat()})",
                "order": "session_date.desc,created_at.desc",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def last_hard_cardio(days: int = 28) -> dict | None:
    rows = await get_cardio_in_range(_today() - timedelta(days=days), _today())
    return next((r for r in rows if r.get("intensity") == "hard"), None)


# -- Plans --------------------------------------------------------------

async def get_active_plan() -> dict | None:
    """Active plan ROW (plan JSON under ['plan']). None if never seeded."""
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(
            _url(PLANS_TABLE), headers=_read_headers(),
            params={"select": "*", "user_id": "eq.chris", "status": "eq.active", "limit": "1"},
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if rows else None


async def get_plan_or_default() -> tuple[dict, dict | None]:
    """(plan_json, row_or_None). Falls back to the built-in default when unseeded."""
    row = await get_active_plan()
    if row:
        return row["plan"], row
    return tp.default_plan(), None


async def save_plan(plan: dict, *, rationale: str, created_by: str = "peter",
                    name: str | None = None) -> dict:
    """Supersede the active plan with a new version."""
    current = await get_active_plan()
    version = int(current["version"]) + 1 if current else 1
    programme = await get_active_programme()
    async with httpx.AsyncClient(timeout=15) as c:
        if current:
            r = await c.patch(_url(PLANS_TABLE), headers=_write_headers(),
                              params={"id": f"eq.{current['id']}"}, json={"status": "superseded"})
            r.raise_for_status()
        body = {
            "programme_id": programme["id"] if programme else None,
            "version": version, "status": "active",
            "name": name or plan.get("name") or (current or {}).get("name") or "Training plan",
            "plan": plan, "rationale": rationale, "created_by": created_by,
        }
        resp = await c.post(_url(PLANS_TABLE), headers=_write_headers(), json=body)
        resp.raise_for_status()
        return resp.json()[0]


async def get_plan_history(limit: int = 10) -> list[dict]:
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(
            _url(PLANS_TABLE), headers=_read_headers(),
            params={"select": "id,version,status,name,rationale,created_by,created_at",
                    "user_id": "eq.chris", "order": "version.desc", "limit": str(limit)},
        )
        resp.raise_for_status()
        return resp.json()


# -- Composite reads ----------------------------------------------------

async def week_sessions_for(programme: dict, week_no: int, today: date | None = None) -> list[PrescribedSession]:
    """Plan-aware replacement for generate_week(programme['split'], wk).

    split == 'plan' -> project the stored plan onto this week (logged sessions on
    their real days, remaining rotation on the next free days). Other splits
    keep the legacy code-generated prescription.
    """
    split = programme.get("split") or "5x_short"
    if split != tp.PLAN_SPLIT:
        return generate_week(split, max(1, week_no))
    today = today or _today()
    plan, _ = await get_plan_or_default()
    ws = tp.week_start_of(today)
    recent = await get_sessions_in_range(ws - timedelta(days=21), ws + timedelta(days=6))
    logged = [s for s in recent if str(s["session_date"]) >= ws.isoformat()]
    return tp.build_week_sessions(plan, ws, logged, today, recent_sessions=recent)


async def next_session_bundle(session_type: str | None = None) -> dict:
    """Everything the skill needs to brief the next strength session."""
    plan, row = await get_plan_or_default()
    today = _today()
    recent = await get_sessions_in_range(today - timedelta(days=28), today)
    st = session_type or tp.next_session_type(plan, recent, today)
    prior_count = len([s for s in recent if s.get("session_type") == st])
    spec = (plan.get("sessions") or {}).get(st) or {}
    slugs = [e["slug"] for e in spec.get("exercises", [])]
    history = await get_sets_history(days=84, slugs=slugs) if slugs else {}
    meta = await get_exercise_meta(slugs)
    rec = tp.compute_next_session(plan, st, history, meta, prior_count)
    ok, gap = tp.rest_gap_ok(plan, recent, today)
    rec["rest_gap_ok"] = ok
    rec["days_since_last_strength"] = gap
    rec["plan_version"] = row["version"] if row else None
    rec["suggested"] = session_type is None
    return rec


async def training_week_summary(today: date | None = None) -> dict:
    today = today or _today()
    plan, row = await get_plan_or_default()
    ws = tp.week_start_of(today)
    we = ws + timedelta(days=6)
    strength = tp.strength_sessions_only(await get_sessions_in_range(ws, we))
    cardio = await get_cardio_in_range(ws, we)
    history = await get_sets_history(days=42)
    rules = (plan.get("progression") or {}).get("strength") or {}
    return {
        "week_start": ws.isoformat(),
        "strength": {
            "done": len(strength),
            "target": int((plan.get("weekly") or {}).get("strength_sessions", 3)),
            "sessions": [{"date": s["session_date"], "type": s["session_type"], "rpe": s.get("rpe")} for s in strength],
            "next": tp.next_session_type(plan, strength, today),
        },
        "cardio": tp.cardio_week_summary(plan, cardio),
        "progressions_this_week": tp.progressions_since(history, ws),
        "stalled": tp.stalled_exercises(history, int(rules.get("stall_sessions", 3))),
        "plan_version": row["version"] if row else None,
    }
