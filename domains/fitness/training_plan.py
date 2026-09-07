"""Adaptive training plan — the programme as DATA, not code.

The agreed plan (split, sessions, exercises + rep ranges, cardio protocol,
progression rules, constraints) is stored as JSON in
``fitness_training_plans`` and versioned. Everything here is pure: the
service layer (``service.py``) does the I/O and hands in logged history.

Three jobs:

1. **Best practice** — ``DEFAULT_PLAN`` encodes double progression for
   pin-loaded machines / dumbbells (hit the top of the rep range with >= ``rir_up``
   reps in reserve -> one plate up; failed set -> hold; failed twice running ->
   drop ~10% and rebuild), a fixed-day standing week from w/c 7 Sep 2026
   (Mon Upper A push, Tue Lower A, Wed hard cardio, Thu Upper B pull, Fri easy
   cardio, Sat full body light, Sun rest/walk) and a hard-cardio pyramid
   with Chris's stated progression order (peak to a full 2 min -> +30 s on the
   other hard blocks -> raise the level). The stairmaster is only the EXAMPLE
   hard-cardio modality — bike / rower / treadmill intervals are interchangeable;
   ``intensity == "hard"`` is what makes a session the week's hard one.
2. **Learn from progress** — ``compute_next_session`` derives every exercise's
   next target from what was actually lifted, never from the calendar.
   ``next_cardio_hard`` does the same for the interval session.
3. **Adapt to what Chris actually did** — ``reconcile_plan`` folds off-plan
   exercises / session types into the plan (new version, rationale recorded)
   instead of dropping them.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from domains.fitness.programme_generator import PrescribedSession, PrescribedSet

PLAN_SPLIT = "plan"          # fitness_programmes.split value meaning "read fitness_training_plans"
STRENGTH_EXCLUDED = ("mobility", "rest", "cardio")

# ── Default plan (Sep 2026 gym version) ───────────────────────────────

_STAIRMASTER_PYRAMID = [
    {"phase": "warmup",   "seconds": 180, "level": 5.5},
    {"phase": "hard",     "seconds": 60,  "level": 9},
    {"phase": "easy",     "seconds": 120, "level": 5},
    {"phase": "hard",     "seconds": 90,  "level": 9},
    {"phase": "easy",     "seconds": 120, "level": 5},
    {"phase": "peak",     "seconds": 90,  "level": 9},
    {"phase": "easy",     "seconds": 120, "level": 5},
    {"phase": "hard",     "seconds": 90,  "level": 9},
    {"phase": "easy",     "seconds": 120, "level": 5},
    {"phase": "hard",     "seconds": 60,  "level": 9},
    {"phase": "cooldown", "seconds": 120, "level": 4},
]


def _ex(slug: str, sets: int, lo: int, hi: int, target: int | None = None, **extra: Any) -> dict:
    out = {"slug": slug, "sets": sets, "rep_range": [lo, hi], "target_reps": target or lo + (hi - lo) // 2}
    out.update(extra)
    return out


# Standing week from w/c 7 Sep 2026 (Mon..Sun). Strength entries name a session
# in ``sessions``; the others are ``cardio_hard`` / ``cardio_easy`` / ``rest``.
SCHEDULE_CARDIO_HARD, SCHEDULE_CARDIO_EASY, SCHEDULE_REST = "cardio_hard", "cardio_easy", "rest"

DEFAULT_PLAN: dict[str, Any] = {
    "split": "4x_fixed_days",
    "name": "Reset Cut gym plan — standing week (4 lifts + 1 hard cardio), w/c 7 Sep 2026",
    "goal": "Hold (ideally build) strength through the Reset Cut deficit; 75 kg by 20 Dec 2026.",
    "venue": "TSC Tonbridge — pin-loaded Life Fitness machines + dumbbells",
    "session_length_min": 40,
    # Plan-week numbering (cardio extension, second hard session) counts from here: week 1 = w/c 7 Sep.
    "schedule_from": "2026-09-07",
    "schedule": ["upper_a", "lower_a", SCHEDULE_CARDIO_HARD, "upper_b", SCHEDULE_CARDIO_EASY, "full_body", SCHEDULE_REST],
    "weekly": {
        "strength_sessions": 4,
        "cardio_easy": 1,                    # the Friday session is the only mandated easy one — see cardio.easy.note
        "cardio_hard": 1,
        "min_rest_days_between_strength": 0, # upper/lower sit on consecutive days by design (Mon/Tue); never two uppers back to back
    },
    "rotation": ["upper_a", "lower_a", "upper_b", "full_body"],
    "sessions": {
        "upper_a": {
            "label": "Upper A — push",
            "duration_min": 40,
            "page": "upper-a.html",
            "exercises": [
                _ex("db-flat-bench-press", 3, 8, 12, 10),
                _ex("db-incline-press", 3, 6, 10, 8, note="3 × 8 clean is the target — don't chase 10 yet"),
                _ex("shoulder-press", 3, 8, 12, 10, note="machine; after two dumbbell presses, expect it pre-fatigued"),
                _ex("db-flye", 2, 10, 14, 12, note="light and slow"),
                _ex("db-incline-curl", 4, 8, 12, 10, unilateral=True, note="set 4 = left arm only; left leads, right matches"),
            ],
        },
        "lower_a": {
            "label": "Lower A",
            "duration_min": 45,
            "page": "lower-a.html",
            "exercises": [
                _ex("leg-press", 3, 8, 12, 10, note="add plates between sets until set 3 ends at RPE 8"),
                _ex("db-romanian-deadlift", 3, 8, 12, 10),
                _ex("seated-leg-curl", 3, 10, 15, 12),
                _ex("db-split-squat", 2, 8, 12, 10, unilateral=True, note="per leg; weaker leg first, match reps"),
                _ex("hip-abduction", 2, 12, 20, 15),
                _ex("leg-press-calf-raise", 3, 12, 20, 15),
            ],
        },
        "upper_b": {
            "label": "Upper B — pull",
            "duration_min": 45,
            "page": "upper-b.html",
            "exercises": [
                _ex("lat-pulldown", 3, 8, 12, 10),
                _ex("seated-row", 3, 8, 12, 10),
                _ex("chest-press", 2, 8, 12, 10, light=True, note="light second chest exposure — stop at RPE 7, not to failure"),
                _ex("cable-face-pull", 2, 12, 20, 15),
                _ex("lateral-raise", 2, 12, 15, 12),
                _ex("triceps-pushdown", 2, 10, 15, 12),
            ],
        },
        "full_body": {
            "label": "Full body — light",
            "duration_min": 40,
            "page": "full-body.html",
            "status": "proposed",   # not yet trained — log what you do and it adapts
            "exercises": [
                _ex("goblet-squat", 3, 8, 12, 10),
                _ex("cable-pull-through", 3, 10, 15, 12),
                _ex("single-arm-db-row", 3, 8, 12, 10, unilateral=True, note="per side; left leads, right matches"),
                _ex("chest-press", 2, 8, 12, 10, light=True, note="light — stop at RPE 7"),
                _ex("kneeling-cable-crunch", 3, 10, 15, 12),
            ],
        },
        # Retired 7 Sep 2026 — kept so logged history (5–6 Sep) still resolves to a label.
        "upper": {
            "label": "Upper body — machines (retired 7 Sep, folded into Upper B)",
            "status": "retired",
            "exercises": [
                _ex("lat-pulldown", 3, 8, 12, 10),
                _ex("chest-press", 3, 8, 12, 10),
                _ex("seated-row", 3, 8, 12, 10),
                _ex("shoulder-press", 3, 8, 12, 10),
            ],
        },
        "upper_db": {
            "label": "Upper body — dumbbells (retired 7 Sep, now Upper A)",
            "status": "retired",
            "exercises": [
                _ex("db-flat-bench-press", 3, 8, 12, 10),
                _ex("db-flye", 3, 10, 14, 12),
                _ex("db-incline-press", 3, 8, 12, 10),
                _ex("db-incline-curl", 3, 8, 12, 10),
            ],
        },
    },
    "cardio": {
        "easy": {
            "modalities": ["bike", "walk", "treadmill", "elliptical"],
            "duration_min": 30,
            "duration_range_min": [30, 40],
            "rpe": [3, 4],
            "optional_after_lifts_min": [10, 20],
            "steps_count_as_easy": [8000, 10000],
            "note": "Fri: 30–40 min at RPE 3–4. Optional 10–20 min bike/walk after the Mon/Tue/Thu/Sat lifts. "
                    "A day of 8–10k steps counts as easy cardio.",
        },
        "hard": {
            # The stairmaster is the EXAMPLE only — any hard-cardio modality is interchangeable.
            # A session is the week's hard one because intensity == "hard", not because of the machine.
            "modality": "stairmaster",
            "modality_is_example": True,
            "modalities": ["stairmaster", "bike", "rower", "treadmill", "elliptical"],
            "note": "Stairmaster pyramid is the worked example; bike / rower / treadmill intervals on the same "
                    "block structure are interchangeable. Levels then mean that machine's resistance level.",
            "duration_min": 20,
            "protocol": _STAIRMASTER_PYRAMID,
            "targets": {"peak_seconds": 120, "hard_seconds": 90, "level": 9},
            "progression": [
                "Peak block to a full 120 s at the current level",
                "+30 s on the other hard blocks",
                "Raise the level by 1",
                "Extend to 25-30 min from plan week 4 (w/c 28 Sep)",
            ],
            "extend_from_week": 4,
            "second_session_from_week": 6,   # no second hard session before plan week 6 (w/c 12 Oct)
            "swap_on_pain": "bike",
        },
    },
    "progression": {
        "strength": {
            "method": "double_progression",
            "rir_up": 2,             # all sets at/above target with >= 2 in reserve -> one plate up
            "fail_hold": True,       # a failed set -> hold the load, aim clean sets
            "deload_after_fails": 2, # failed in 2 consecutive sessions -> drop ~deload_pct
            "deload_pct": 10,
            "stall_sessions": 3,     # same load, no increase, 3 sessions running -> flag
            "unilateral": "Weaker (left) side leads; the stronger side matches its reps.",
            "log_rir": "Log reps-in-reserve on the last set of each exercise.",
        },
    },
    "constraints": [
        "Hip: stop and switch to the bike on sharp or pinching pain (muscle fatigue is fine).",
        "In a deficit: expect slower progression. Hold rather than force a plate.",
        "Fixed days: Mon Upper A · Tue Lower A · Wed hard cardio · Thu Upper B · Fri easy cardio · Sat full body · Sun rest/walk. "
        "Upper and lower may sit on consecutive days; never two upper sessions back to back.",
        "Weaker (left) side leads on unilateral work; the stronger side matches its reps.",
        "Log reps-in-reserve on the last set of each exercise.",
        "No second hard cardio session before plan week 6 (w/c 12 Oct 2026).",
        "Machine shoulder press sits after two dumbbell presses on Upper A — expect it to be pre-fatigued.",
    ],
    "started": "2026-09-05",
}


def default_plan() -> dict:
    return copy.deepcopy(DEFAULT_PLAN)


def plan_week(plan: dict, today: date) -> int | None:
    """1-based week of the standing schedule (``schedule_from`` = week 1).
    None when unset or not an ISO date (the plan is free-form JSON from the DB)."""
    start = plan.get("schedule_from")
    if not start:
        return None
    try:
        ws = week_start_of(date.fromisoformat(str(start)))
    except ValueError:
        return None
    return max(1, (week_start_of(today) - ws).days // 7 + 1)


_SCHEDULE_SENTINELS = (SCHEDULE_CARDIO_HARD, SCHEDULE_CARDIO_EASY, SCHEDULE_REST)


def schedule_for(plan: dict) -> list[str] | None:
    """The 7-entry Mon..Sun schedule, or None (-> rotation fallback) when absent
    or malformed: wrong length, an entry that is neither a sentinel nor an
    active (non-retired) session type."""
    sched = plan.get("schedule")
    if not isinstance(sched, list) or len(sched) != 7:
        return None
    sessions = plan.get("sessions") or {}
    out: list[str] = []
    for s in sched:
        if not isinstance(s, str):
            return None
        if s in _SCHEDULE_SENTINELS:
            out.append(s)
        elif s in sessions and (sessions.get(s) or {}).get("status") != "retired":
            out.append(s)
        else:
            return None
    return out


def active_session_types(plan: dict) -> list[str]:
    """Session types that are part of the current schedule / rotation (retired ones excluded)."""
    sessions = plan.get("sessions") or {}
    return [k for k in (plan.get("rotation") or list(sessions.keys()))
            if (sessions.get(k) or {}).get("status") != "retired"]


# ── Rotation / ordering ──────────────────────────────────────────────

def strength_sessions_only(sessions: list[dict]) -> list[dict]:
    return [s for s in sessions if (s.get("session_type") or "") not in STRENGTH_EXCLUDED]


def next_session_type(plan: dict, recent_sessions: list[dict], today: date | None = None) -> str:
    """The strength session that comes next.

    Standing week (``schedule`` + ``today``): today's scheduled lift if it has
    not been logged today, otherwise the next scheduled lift after today
    (wrapping into next week). A skipped day is not carried forward — that
    matches the week view, which marks it "missed".

    Legacy rotation (no schedule): the type after the most recent logged one
    (``recent_sessions`` newest-first, non-strength ignored); a last type
    outside the rotation restarts at the top.
    """
    rotation: list[str] = plan.get("rotation") or list((plan.get("sessions") or {}).keys())
    if not rotation:
        return "full_body"
    strength = strength_sessions_only(recent_sessions)
    schedule = schedule_for(plan)
    if schedule and today is not None:
        active = set(active_session_types(plan))
        logged_today = {s.get("session_type") for s in strength if str(s.get("session_date")) == today.isoformat()}
        for offset in range(7):
            entry = schedule[(today.weekday() + offset) % 7]
            if entry in active and not (offset == 0 and entry in logged_today):
                return entry
        return rotation[0]
    if not strength:
        return rotation[0]
    last = strength[0].get("session_type")
    if last not in rotation:
        return rotation[0]
    return rotation[(rotation.index(last) + 1) % len(rotation)]


def resolve_session_type(plan: dict, inferred: str, session_date: date | None = None) -> str:
    """Map an inferred body-region type (Fitbod: ``upper`` / ``lower`` / ``full_body``)
    onto one of the plan's ACTIVE session types, never a retired one.

    Prefers the lift scheduled for that date when it is the same region
    (Tue leg day -> ``lower_a``), else the first active type of that region
    (``upper`` -> ``upper_a``), else the inferred name (legacy plans / new types).
    """
    active = active_session_types(plan)
    if inferred in active:
        return inferred
    region = inferred.split("_")[0]
    schedule = schedule_for(plan)
    if schedule and session_date is not None:
        entry = schedule[session_date.weekday()]
        if entry in active and entry.split("_")[0] == region:
            return entry
    for t in active:
        if t.split("_")[0] == region:
            return t
    return inferred


def order_variant(plan: dict, session_type: str, prior_count: int) -> str | None:
    variants = ((plan.get("sessions") or {}).get(session_type) or {}).get("order_variants")
    if not variants:
        return None
    keys = list(variants.keys())
    return keys[prior_count % len(keys)]


def rest_gap_ok(plan: dict, recent_sessions: list[dict], today: date) -> tuple[bool, int | None]:
    """(ok, days_since_last_strength). ok=False when yesterday was a strength day."""
    min_gap = int((plan.get("weekly") or {}).get("min_rest_days_between_strength", 1))
    strength = strength_sessions_only(recent_sessions)
    if not strength:
        return True, None
    last_date = date.fromisoformat(str(strength[0]["session_date"]))
    gap = (today - last_date).days
    return gap > min_gap, gap


# ── Strength progression ─────────────────────────────────────────────

def _round_to_step(value: float, step: float | None) -> float:
    if not step:
        return round(value, 1)
    return round(round(value / step) * step, 2)


def _session_stats(sets: list[dict]) -> dict:
    """Summarise one exercise's sets from one session."""
    working = [s for s in sets if s.get("reps") is not None]
    weights = [float(s["weight_kg"]) for s in working if s.get("weight_kg") is not None]
    reps = [int(s["reps"]) for s in working]
    rirs = [int(s["rir"]) for s in working if s.get("rir") is not None]
    return {
        "top_weight": max(weights) if weights else None,
        "reps": reps,
        "min_reps": min(reps) if reps else None,
        "min_rir": min(rirs) if rirs else None,
        "failed": any(bool(s.get("failed")) for s in working),
        "sets_done": len(working),
    }


def recommend_exercise(
    plan_ex: dict,
    history: list[dict],
    load_step_kg: float | None,
    rules: dict | None = None,
) -> dict:
    """Next target for one exercise from its logged history (newest-first).

    ``history`` items: {date, session_type, sets: [{reps, weight_kg, rir, failed, target_reps}]}.
    Returns a dict the skill can render verbatim.
    """
    rules = rules or DEFAULT_PLAN["progression"]["strength"]
    rir_up = int(rules.get("rir_up", 2))
    deload_after = int(rules.get("deload_after_fails", 2))
    deload_pct = float(rules.get("deload_pct", 10))
    sets = int(plan_ex.get("sets", 3))
    lo, hi = plan_ex.get("rep_range") or [8, 12]
    target = int(plan_ex.get("target_reps") or lo)
    out = {
        "slug": plan_ex["slug"],
        "sets": sets,
        "target_reps": target,
        "rep_range": [lo, hi],
        "weight_kg": None,
        "action": "start",
        "reason": "No history yet — pick a load you can do for the target reps with ~2 in reserve.",
        "last": None,
    }
    for k in ("note", "unilateral", "light"):
        if plan_ex.get(k) is not None:
            out[k] = plan_ex[k]
    if not history:
        return out

    last = _session_stats(history[0]["sets"])
    out["last"] = {"date": history[0]["date"], **last}
    w = last["top_weight"]

    if last["failed"]:
        # Consecutive failed sessions at the same load -> deload.
        streak = 1
        for h in history[1:]:
            st = _session_stats(h["sets"])
            if st["failed"] and st["top_weight"] == w:
                streak += 1
            else:
                break
        if streak >= deload_after and w:
            new_w = _round_to_step(w * (1 - deload_pct / 100), load_step_kg)
            out.update(weight_kg=new_w, action="deload",
                       reason=f"Failed at {w:g} kg two sessions running — drop ~{deload_pct:g}% and rebuild clean sets.")
        else:
            out.update(weight_kg=w, action="hold",
                       reason=f"Failed a rep last time — hold {w:g} kg and aim for a clean {sets}×{target}." if w
                       else f"Failed a rep last time — same load, aim for a clean {sets}×{target}.")
        return out

    # Fewer sets than prescribed is not a completed session, however clean the
    # sets were (6 Sep 2026: 2×10 on the incline DB press was read as "3×10 with
    # reps in reserve" and prescribed +2 kg). Finish the volume before loading.
    done_sets = len(history[0].get("sets") or [])
    if done_sets and done_sets < sets:
        out.update(weight_kg=w, action="hold",
                   reason=(f"Only {done_sets} of {sets} sets last time — hold {w:g} kg and complete all {sets}×{target} before adding load."
                           if w else f"Only {done_sets} of {sets} sets last time — same load, complete all {sets}×{target} first."))
        return out

    all_hit_target = last["min_reps"] is not None and last["min_reps"] >= target
    all_top_of_range = last["min_reps"] is not None and last["min_reps"] >= hi
    easy = last["min_rir"] is None or last["min_rir"] >= rir_up

    if all_top_of_range or (all_hit_target and easy):
        if w is None:
            out.update(action="increase", reason="Hit every set with reps to spare — add load / a harder variation.")
        elif load_step_kg:
            out.update(weight_kg=round(w + load_step_kg, 2), action="increase",
                       reason=f"{sets}×{target} at {w:g} kg with reps in reserve — go up one plate (+{load_step_kg:g} kg).")
        else:
            out.update(weight_kg=None, action="increase",
                       reason=f"{sets}×{target} at {w:g} kg with reps in reserve — go up one plate.")
        out["last_weight_kg"] = w
        return out

    if all_hit_target:
        out.update(weight_kg=w, action="hold",
                   reason=f"Hit {sets}×{target} at {w:g} kg but close to failure — repeat it, aim for {rir_up} in reserve before adding a plate."
                   if w else f"Hit {sets}×{target} but close to failure — repeat, aim for {rir_up} in reserve.")
        return out

    out.update(weight_kg=w, action="hold",
               reason=f"Short of {target} reps last time ({'/'.join(map(str, last['reps']))}) — hold {w:g} kg and chase the reps."
               if w else f"Short of {target} reps last time — same load, chase the reps.")
    return out


def compute_next_session(
    plan: dict,
    session_type: str,
    history_by_slug: dict[str, list[dict]],
    exercise_meta: dict[str, dict],
    prior_count: int = 0,
) -> dict:
    """Full next-session prescription for ``session_type``."""
    sessions = plan.get("sessions") or {}
    spec = sessions.get(session_type)
    if not spec:
        return {"session_type": session_type, "known": False, "exercises": [],
                "note": "Not in the plan yet — log what you do and it'll be added."}
    rules = (plan.get("progression") or {}).get("strength") or {}
    variant = order_variant(plan, session_type, prior_count)
    order = (spec.get("order_variants") or {}).get(variant) if variant else None
    plan_exs = list(spec.get("exercises") or [])
    if order:
        by_slug = {e["slug"]: e for e in plan_exs}
        plan_exs = [by_slug[s] for s in order if s in by_slug] + [e for e in plan_exs if e["slug"] not in order]

    exercises = []
    for pe in plan_exs:
        meta = exercise_meta.get(pe["slug"], {})
        rec = recommend_exercise(pe, history_by_slug.get(pe["slug"], []), meta.get("load_step_kg"), rules)
        rec["name"] = meta.get("name", pe["slug"])
        exercises.append(rec)
    return {
        "session_type": session_type,
        "known": True,
        "label": spec.get("label", session_type),
        "status": spec.get("status", "active"),
        "order_variant": variant,
        "duration_min": int(spec.get("duration_min") or plan.get("session_length_min", 40)),
        "page": spec.get("page"),
        "exercises": exercises,
        "constraints": plan.get("constraints", []),
    }


# ── Stalls / wins (advisor signals) ──────────────────────────────────

def stalled_exercises(history_by_slug: dict[str, list[dict]], stall_sessions: int = 3) -> list[dict]:
    """Exercises whose top load hasn't moved for >= stall_sessions consecutive sessions."""
    out = []
    for slug, hist in history_by_slug.items():
        if len(hist) < stall_sessions:
            continue
        tops = [_session_stats(h["sets"])["top_weight"] for h in hist[:stall_sessions]]
        if any(t is None for t in tops):
            continue
        if len(set(tops)) == 1:
            out.append({"slug": slug, "weight_kg": tops[0], "sessions": stall_sessions})
    return out


def progressions_since(history_by_slug: dict[str, list[dict]], since: date) -> list[dict]:
    """Exercises where the most recent session (on/after ``since``) beat the previous top load."""
    wins = []
    for slug, hist in history_by_slug.items():
        if len(hist) < 2:
            continue
        latest, prev = hist[0], hist[1]
        if date.fromisoformat(str(latest["date"])) < since:
            continue
        a, b = _session_stats(latest["sets"])["top_weight"], _session_stats(prev["sets"])["top_weight"]
        if a is not None and b is not None and a > b:
            wins.append({"slug": slug, "from_kg": b, "to_kg": a})
    return wins


# ── Cardio ────────────────────────────────────────────────────────────

def build_protocol(template: list[dict], *, hard_level: float | None = None,
                   peak_level: float | None = None, peak_seconds: int | None = None,
                   hard_seconds: int | None = None) -> list[dict]:
    """Instantiate the pyramid template with what was actually done / is targeted."""
    out = []
    for b in template:
        nb = dict(b)
        if b["phase"] == "peak":
            if peak_level is not None:
                nb["level"] = peak_level
            if peak_seconds is not None:
                nb["seconds"] = peak_seconds
        elif b["phase"] == "hard":
            if hard_level is not None:
                nb["level"] = hard_level
            if hard_seconds is not None:
                nb["seconds"] = hard_seconds
        out.append(nb)
    return out


def _protocol_summary(protocol: list[dict] | None) -> dict:
    protocol = protocol or []
    peak = next((b for b in protocol if b.get("phase") == "peak"), None)
    hards = [b for b in protocol if b.get("phase") == "hard"]
    return {
        "peak_seconds": int(peak["seconds"]) if peak else None,
        "peak_level": float(peak["level"]) if peak and peak.get("level") is not None else None,
        "hard_seconds_min": min(int(b["seconds"]) for b in hards) if hards else None,
        "hard_level": max(float(b["level"]) for b in hards if b.get("level") is not None) if hards else None,
        "total_seconds": sum(int(b.get("seconds") or 0) for b in protocol),
    }


def next_cardio_hard(plan: dict, last: dict | None, week_no: int | None = None,
                     today: date | None = None) -> dict:
    """Next hard-cardio prescription following the plan's progression order.

    ``week_no`` is the programme week; when the plan carries ``schedule_from``
    and ``today`` is given (callers pass the service's UK-time today), the plan
    week (week 1 = that Monday) takes precedence for the week-gated steps
    (extend the session, allow a second hard session).
    The modality is the plan's worked example (stairmaster) unless the last hard
    session used another one — the machine is interchangeable, ``intensity``
    is what makes it the hard session.
    """
    hard = (plan.get("cardio") or {}).get("hard") or {}
    template = hard.get("protocol") or _STAIRMASTER_PYRAMID
    targets = hard.get("targets") or {"peak_seconds": 120, "hard_seconds": 90, "level": 9}
    example = hard.get("modality", "stairmaster")
    interchangeable = bool(hard.get("modality_is_example", False))
    allowed = set(hard.get("modalities") or []) | {example}
    last_mod = last.get("modality") if last else None
    modality = last_mod if (interchangeable and last_mod in allowed) else example
    pw = plan_week(plan, today) if today is not None else None
    if pw is not None:
        week_no = pw
    extra = {"modality_is_example": interchangeable}
    if interchangeable:
        extra["modality_note"] = hard.get("note") or "Any hard-cardio modality is interchangeable."

    if last and last.get("pain_flag"):
        swap = hard.get("swap_on_pain", "bike")
        return {"modality": swap, "protocol": None, "duration_min": hard.get("duration_min", 20),
                "reason": f"Hip pain flagged last time — do the hard session on the {swap} this week and see how it feels.",
                "stage": "pain_swap", **extra}

    if not last:
        return {"modality": modality, "protocol": build_protocol(template), "duration_min": hard.get("duration_min", 20),
                "reason": "First interval session — run the pyramid as written; drop the peak to 90 s if the legs go.",
                "stage": "start", **_protocol_summary(build_protocol(template)), **extra}

    cur = _protocol_summary(last.get("protocol"))
    if cur["peak_seconds"] is None:      # unstructured last session — restart from the template
        proto = build_protocol(template)
        return {"modality": modality, "protocol": proto, "duration_min": hard.get("duration_min", 20),
                "reason": "Last session had no block detail — run the pyramid as written.", "stage": "start",
                **_protocol_summary(proto), **extra}

    level = cur["hard_level"] or targets["level"]
    peak_level = cur["peak_level"] or level
    peak_target = int(targets.get("peak_seconds", 120))
    hard_target = int(targets.get("hard_seconds", 90))

    if cur["peak_seconds"] < peak_target:
        new_peak = min(peak_target, cur["peak_seconds"] + 30)
        proto = build_protocol(template, hard_level=level, peak_level=peak_level, peak_seconds=new_peak,
                               hard_seconds=None)
        # keep the last session's hard-block durations
        proto = _carry_hard_seconds(proto, last.get("protocol"))
        stage, reason = "extend_peak", f"Hold every hard block at L{level:g}; push the peak from {cur['peak_seconds']} s to {new_peak} s."
    elif cur["hard_seconds_min"] is not None and cur["hard_seconds_min"] < hard_target:
        proto = _bump_shortest_hard(build_protocol(template, hard_level=level, peak_level=peak_level,
                                                   peak_seconds=cur["peak_seconds"]), last.get("protocol"), hard_target)
        stage, reason = "extend_hard", f"Peak is a full {cur['peak_seconds']} s — now add 30 s to the shorter hard blocks at L{level:g}."
    else:
        new_level = level + 1
        proto = build_protocol(template, hard_level=new_level, peak_level=peak_level + 1,
                               peak_seconds=cur["peak_seconds"], hard_seconds=None)
        proto = _carry_hard_seconds(proto, last.get("protocol"))
        stage, reason = "raise_level", f"Durations are maxed at L{level:g} — take every hard block up to L{new_level:g}."

    out = {"modality": modality, "protocol": proto, "duration_min": hard.get("duration_min", 20),
           "reason": reason, "stage": stage, **_protocol_summary(proto), **extra}
    extend_from = int(hard.get("extend_from_week", 4))
    if week_no and week_no >= extend_from and out["total_seconds"] < 25 * 60:
        out["note"] = (f"Week {extend_from}+: extend the session toward 25-30 min "
                       "(add an easy/hard pair before the cool-down).")
    return out


def _carry_hard_seconds(proto: list[dict], last_protocol: list[dict] | None) -> list[dict]:
    """Copy the hard-block durations from the last session, position by position."""
    if not last_protocol:
        return proto
    last_hards = [b for b in last_protocol if b.get("phase") == "hard"]
    i = 0
    for b in proto:
        if b["phase"] == "hard" and i < len(last_hards):
            b["seconds"] = int(last_hards[i]["seconds"])
            i += 1
    return proto


def _bump_shortest_hard(proto: list[dict], last_protocol: list[dict] | None, hard_target: int) -> list[dict]:
    proto = _carry_hard_seconds(proto, last_protocol)
    hards = [b for b in proto if b["phase"] == "hard"]
    if not hards:
        return proto
    shortest = min(int(b["seconds"]) for b in hards)
    for b in hards:
        if int(b["seconds"]) == shortest:
            b["seconds"] = min(hard_target, shortest + 30)
    return proto


def cardio_week_summary(plan: dict, cardio_sessions: list[dict]) -> dict:
    weekly = plan.get("weekly") or {}
    easy = [c for c in cardio_sessions if c.get("intensity") != "hard"]
    hard = [c for c in cardio_sessions if c.get("intensity") == "hard"]
    return {
        "easy_done": len(easy), "easy_target": int(weekly.get("cardio_easy", 5)),
        "hard_done": len(hard), "hard_target": int(weekly.get("cardio_hard", 1)),
        "minutes": sum(int(c.get("duration_min") or 0) for c in cardio_sessions),
    }


# ── Adapt the plan to what was actually done ──────────────────────────

def _mode(values: list[int], default: int) -> int:
    if not values:
        return default
    return max(set(values), key=values.count)


def reconcile_plan(plan: dict, session_type: str, logged_sets: list[dict]) -> tuple[dict, list[str]]:
    """Fold a logged session into the plan. Returns (new_plan, changes).

    - Unknown session type -> new session entry (+ appended to the rotation).
    - Exercises logged that aren't in that session -> added with the logged
      sets / reps as the starting prescription (+ appended to order variants).
    Nothing is ever removed automatically; Chris edits removals via PUT /fitness/plan.
    """
    if session_type in STRENGTH_EXCLUDED:
        return plan, []
    new = copy.deepcopy(plan)
    changes: list[str] = []
    sessions = new.setdefault("sessions", {})

    # group logged sets by slug preserving first-seen order
    by_slug: dict[str, list[dict]] = {}
    for s in logged_sets:
        by_slug.setdefault(s["exercise_slug"], []).append(s)

    if session_type not in sessions:
        sessions[session_type] = {"label": session_type.replace("_", " ").title(), "exercises": [], "status": "active"}
        rotation = new.setdefault("rotation", [])
        if session_type not in rotation:
            rotation.append(session_type)
        changes.append(f"added session type '{session_type}' to the plan + rotation")

    spec = sessions[session_type]
    existing = {e["slug"] for e in spec.setdefault("exercises", [])}
    for slug, sets in by_slug.items():
        if slug in existing:
            continue
        reps = [int(s["reps"]) for s in sets if s.get("reps") is not None]
        target = _mode([s["target_reps"] for s in sets if s.get("target_reps")], _mode(reps, 10))
        lo, hi = max(1, target - 2), target + 2
        spec["exercises"].append({"slug": slug, "sets": max(1, len(sets)), "rep_range": [lo, hi], "target_reps": target})
        for variant in (spec.get("order_variants") or {}).values():
            if slug not in variant:
                variant.append(slug)
        changes.append(f"added {slug} ({len(sets)}×{target}) to '{session_type}'")
    if spec.get("status") == "proposed" and by_slug:
        spec["status"] = "active"
        changes.append(f"'{session_type}' confirmed by training it")
    return new, changes


def apply_plan_patch(plan: dict, patch: dict) -> tuple[dict, list[str]]:
    """Targeted edits from Peter: swap / add / remove exercises, retune targets.

    patch = {
      "session_type": "upper",
      "remove": ["chest-press"],
      "add": [{"slug": "incline-chest-press", "sets": 3, "rep_range": [8,12], "target_reps": 10}],
      "set": {"lat-pulldown": {"sets": 4}},
      "weekly": {"cardio_easy": 4},
      "constraints_add": ["..."],
    }
    """
    new = copy.deepcopy(plan)
    changes: list[str] = []
    st = patch.get("session_type")
    if st:
        spec = new.setdefault("sessions", {}).setdefault(st, {"label": st.replace("_", " ").title(), "exercises": []})
        # A retired session (upper / upper_db after 7 Sep) can still be edited for
        # the record, but never comes back into the rotation.
        if st not in new.setdefault("rotation", []) and spec.get("status") != "retired":
            new["rotation"].append(st)
        for slug in patch.get("remove") or []:
            before = len(spec["exercises"])
            spec["exercises"] = [e for e in spec["exercises"] if e["slug"] != slug]
            for variant in (spec.get("order_variants") or {}).values():
                if slug in variant:
                    variant.remove(slug)
            if len(spec["exercises"]) < before:
                changes.append(f"removed {slug} from '{st}'")
        for ex in patch.get("add") or []:
            if any(e["slug"] == ex["slug"] for e in spec["exercises"]):
                continue
            spec["exercises"].append({"slug": ex["slug"], "sets": int(ex.get("sets", 3)),
                                      "rep_range": ex.get("rep_range") or [8, 12],
                                      "target_reps": int(ex.get("target_reps") or 10)})
            for variant in (spec.get("order_variants") or {}).values():
                variant.append(ex["slug"])
            changes.append(f"added {ex['slug']} to '{st}'")
        for slug, fields in (patch.get("set") or {}).items():
            for e in spec["exercises"]:
                if e["slug"] == slug:
                    e.update({k: v for k, v in fields.items() if k in ("sets", "rep_range", "target_reps")})
                    changes.append(f"updated {slug} in '{st}': {fields}")
        if "label" in patch:
            spec["label"] = patch["label"]
        if patch.get("status"):
            spec["status"] = patch["status"]
    if patch.get("weekly"):
        new.setdefault("weekly", {}).update(patch["weekly"])
        changes.append(f"weekly targets: {patch['weekly']}")
    if patch.get("rotation"):
        new["rotation"] = list(patch["rotation"])
        changes.append(f"rotation: {patch['rotation']}")
    for c in patch.get("constraints_add") or []:
        new.setdefault("constraints", []).append(c)
        changes.append(f"constraint added: {c}")
    if patch.get("cardio"):
        for k, v in patch["cardio"].items():
            new.setdefault("cardio", {}).setdefault(k, {}).update(v)
        changes.append(f"cardio: {list(patch['cardio'].keys())}")
    return new, changes


# ── Week view (dashboard / today compat) ──────────────────────────────

def build_week_sessions(
    plan: dict,
    week_start: date,
    logged_this_week: list[dict],
    today: date,
    recent_sessions: list[dict] | None = None,
) -> list[PrescribedSession]:
    """Project the plan onto Mon..Sun for the dashboard / /fitness/today.

    Logged strength sessions sit on their real days. With a fixed ``schedule``
    (standing week) the remaining strength sessions go on their scheduled days
    from today onward (a missed earlier day stays as a missed marker, it is not
    pushed later); other days show what the schedule says (hard cardio, easy
    cardio, rest). Without a schedule the rotation is placed on the next free
    days from today keeping >= ``min_rest_days_between_strength`` between lifts.
    """
    rotation = plan.get("rotation") or ["upper", "lower", "full_body"]
    sessions_spec = plan.get("sessions") or {}
    weekly = plan.get("weekly") or {}
    target_n = int(weekly.get("strength_sessions", 3))
    min_gap = int(weekly.get("min_rest_days_between_strength", 1))

    by_dow: dict[int, PrescribedSession] = {}
    logged = sorted(strength_sessions_only(logged_this_week), key=lambda s: str(s["session_date"]))
    for s in logged:
        d = date.fromisoformat(str(s["session_date"]))
        dow = (d - week_start).days
        if 0 <= dow <= 6:
            by_dow[dow] = _plan_session(plan, s["session_type"], dow, done=True)

    schedule = schedule_for(plan)
    if schedule:
        return _build_scheduled_week(plan, schedule, by_dow, week_start, today)

    remaining = max(0, target_n - len(by_dow))
    # Rotation continues from the most recent strength session, even if it was
    # last week (a fresh Monday after a Saturday upper day starts at lower).
    rotation_src = logged if logged else strength_sessions_only(recent_sessions or [])
    nxt = next_session_type(plan, sorted(rotation_src, key=lambda s: str(s["session_date"]), reverse=True))
    start_dow = max(0, (today - week_start).days)
    dow = start_dow
    last_strength = max(by_dow) if by_dow else None
    if last_strength is None and recent_sessions:
        prev = strength_sessions_only(recent_sessions)
        if prev:
            last_date = max(date.fromisoformat(str(s["session_date"])) for s in prev)
            last_strength = (last_date - week_start).days  # negative dow = last week
    while remaining > 0 and dow <= 6:
        gap_ok = last_strength is None or (dow - last_strength) > min_gap
        if dow not in by_dow and gap_ok:
            by_dow[dow] = _plan_session(plan, nxt, dow, done=False)
            last_strength = dow
            remaining -= 1
            nxt = rotation[(rotation.index(nxt) + 1) % len(rotation)] if nxt in rotation else rotation[0]
        dow += 1

    hard = (plan.get("cardio") or {}).get("hard") or {}
    out: list[PrescribedSession] = []
    for d in range(7):
        if d in by_dow:
            out.append(by_dow[d])
        else:
            out.append(PrescribedSession(
                day_of_week=d, session_type="cardio", label="Easy cardio / walk", duration_min=30,
                is_rest=False,
                notes=f"Zone-2: {', '.join((plan.get('cardio') or {}).get('easy', {}).get('modalities', ['walk']))}. "
                      f"One session this week is the hard pyramid ({hard.get('modality', 'stairmaster')} or equivalent).",
            ))
    return out


def _hard_cardio_label(plan: dict) -> str:
    hard = (plan.get("cardio") or {}).get("hard") or {}
    example = hard.get("modality", "stairmaster")
    if hard.get("modality_is_example"):
        return f"Hard cardio — {example} pyramid or equivalent"
    return f"Hard cardio — {example} pyramid"


def _build_scheduled_week(plan: dict, schedule: list[str], by_dow: dict[int, PrescribedSession],
                          week_start: date, today: date) -> list[PrescribedSession]:
    sessions_spec = plan.get("sessions") or {}
    cardio = plan.get("cardio") or {}
    easy, hard = cardio.get("easy") or {}, cardio.get("hard") or {}
    today_dow = (today - week_start).days
    out: list[PrescribedSession] = []
    for d in range(7):
        if d in by_dow:
            out.append(by_dow[d])
            continue
        entry = schedule[d]
        if entry in sessions_spec and entry not in (SCHEDULE_CARDIO_HARD, SCHEDULE_CARDIO_EASY, SCHEDULE_REST):
            if d < today_dow:
                spec = sessions_spec.get(entry) or {}
                out.append(PrescribedSession(
                    day_of_week=d, session_type="rest", label=f"{spec.get('label', entry)} — missed", duration_min=0,
                    is_rest=True, notes="Scheduled lift not logged. Do not stack it on another day; the week carries on."))
            else:
                out.append(_plan_session(plan, entry, d, done=False))
        elif entry == SCHEDULE_CARDIO_HARD:
            out.append(PrescribedSession(
                day_of_week=d, session_type="cardio", label=_hard_cardio_label(plan),
                duration_min=int(hard.get("duration_min", 20)), is_rest=False,
                notes=(hard.get("note") or "") or None))
        elif entry == SCHEDULE_CARDIO_EASY:
            rng = easy.get("duration_range_min")
            if not (isinstance(rng, list) and len(rng) >= 2):
                rng = [easy.get("duration_min", 30)] * 2
            lo, hi = rng[0], rng[1]
            rpe = easy.get("rpe") if isinstance(easy.get("rpe"), list) and easy.get("rpe") else [3, 4]
            out.append(PrescribedSession(
                day_of_week=d, session_type="cardio", label=f"Easy cardio {lo}–{hi} min · RPE {rpe[0]}–{rpe[-1]}",
                duration_min=int(easy.get("duration_min", 30)), is_rest=False,
                notes=f"{', '.join(easy.get('modalities', ['walk']))}. " + (easy.get("note") or "")))
        else:
            out.append(PrescribedSession(
                day_of_week=d, session_type="rest", label="Rest or walk", duration_min=0, is_rest=True,
                notes="Walk if you like; 8–10k steps counts as easy cardio."))
    return out


def _plan_session(plan: dict, session_type: str, dow: int, done: bool) -> PrescribedSession:
    spec = (plan.get("sessions") or {}).get(session_type) or {"label": session_type, "exercises": []}
    exs = [PrescribedSet(exercise_slug=e["slug"], sets=int(e.get("sets", 3)), reps=int(e.get("target_reps") or 10))
           for e in spec.get("exercises", [])]
    label = spec.get("label", session_type) + (" ✓" if done else "")
    return PrescribedSession(day_of_week=dow, session_type=session_type, label=label,
                             duration_min=int(spec.get("duration_min") or plan.get("session_length_min", 40)), exercises=exs,
                             notes=("Done" if done else ("Proposed — log what you do and it adapts" if spec.get("status") == "proposed" else None)))


def week_start_of(d: date) -> date:
    return d - timedelta(days=d.weekday())
