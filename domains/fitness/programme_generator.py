"""13-week bodyweight programme generator.

Given a split type, returns a week-by-week exercise prescription with
progressive overload (reps or holds increase each week).

5x_short split (Chris's choice):
    Mon — Push (upper push)
    Tue — Legs A (quad focus)
    Wed — Pull + core
    Thu — Legs B (posterior chain)
    Fri — Full-body conditioning
    Sat — Mobility + long walk (active recovery)
    Sun — Rest

Each session is ~20 minutes: 4-5 exercises, 3 sets each.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SplitType = Literal["5x_short", "3x_ppl", "4x_upper_lower"]


@dataclass
class PrescribedSet:
    exercise_slug: str
    sets: int
    reps: int | None = None
    hold_s: int | None = None
    note: str | None = None


@dataclass
class PrescribedSession:
    day_of_week: int                 # 0=Mon, 6=Sun
    session_type: str                # "push", "legs_a", etc.
    label: str                       # human-readable: "Push (upper)"
    duration_min: int
    exercises: list[PrescribedSet] = field(default_factory=list)
    is_rest: bool = False
    notes: str | None = None


# ═══════════════════════════════════════════════════════════════════════
# 5x/week SHORT SPLIT — base prescription (week 1)
# ═══════════════════════════════════════════════════════════════════════
# Progression: +1 rep/set or +5s hold per week, capped at double the starting volume

_BASE_5X_SHORT: dict[str, tuple[str, list[tuple[str, int, int | None, int | None]]]] = {
    "push": ("Push (upper)", [
        # (slug, sets, base_reps, base_hold_s)
        ("push-up", 3, 10, None),
        ("pike-push-up", 3, 6, None),
        ("chair-dip", 3, 10, None),
        ("diamond-push-up", 2, 6, None),
        ("plank", 2, None, 45),
    ]),
    "legs_a": ("Legs A (quads)", [
        ("bw-squat", 3, 15, None),
        ("reverse-lunge", 3, 10, None),
        ("bulgarian-split-squat", 3, 8, None),
        ("wall-sit", 2, None, 45),
        ("calf-raise", 2, 20, None),
    ]),
    "pull_core": ("Pull + core", [
        ("inverted-row", 3, 8, None),
        ("superman-hold", 3, None, 20),
        ("reverse-snow-angel", 2, 12, None),
        ("dead-bug", 3, 10, None),
        ("hollow-hold", 3, None, 20),
    ]),
    "legs_b": ("Legs B (posterior)", [
        ("glute-bridge", 3, 15, None),
        ("single-leg-glute-bridge", 3, 8, None),
        ("bw-good-morning", 3, 12, None),
        ("single-leg-rdl", 3, 8, None),
        ("bird-dog", 3, 10, None),
    ]),
    "full_body": ("Full body conditioning", [
        ("burpee", 3, 8, None),
        ("mountain-climber", 3, 20, None),
        ("skater-jump", 3, 12, None),
        ("push-up", 2, 10, None),
        ("plank", 2, None, 45),
    ]),
}

# Day of week mapping for 5x_short
_5X_SCHEDULE = [
    (0, "push"),         # Mon
    (1, "legs_a"),       # Tue
    (2, "pull_core"),    # Wed
    (3, "legs_b"),       # Thu
    (4, "full_body"),    # Fri
    # Sat/Sun handled specially (mobility/rest)
]


# ═══════════════════════════════════════════════════════════════════════
# 4x/week UPPER-LOWER SPLIT — base prescription (week 1)
# ═══════════════════════════════════════════════════════════════════════
# Bodyweight + bands + <5kg only. Mon/Tue/Thu/Fri train; Wed active
# recovery; Sat walk; Sun rest. ~30-min sessions (5-6 moves). Posterior
# chain / glute / core bias to be sciatica- and hip-friendly: no running,
# no loaded spinal flexion. Progression is rep/tempo driven (see _progress).
_BASE_4X_UPPER_LOWER: dict[str, tuple[str, list[tuple[str, int, int | None, int | None]]]] = {
    "lower_a": ("Lower A (glutes / posterior — hip-friendly)", [
        # (slug, sets, base_reps, base_hold_s)
        ("glute-bridge", 3, 15, None),
        ("single-leg-glute-bridge", 3, 10, None),
        ("bulgarian-split-squat", 3, 10, None),
        ("bw-good-morning", 3, 12, None),
        ("single-leg-rdl", 3, 8, None),
        ("side-plank", 3, None, 30),
    ]),
    "upper_a": ("Upper A (push)", [
        ("push-up", 3, 12, None),
        ("pike-push-up", 3, 8, None),
        ("chair-dip", 3, 10, None),
        ("diamond-push-up", 2, 8, None),
        ("plank", 2, None, 45),
    ]),
    "lower_b": ("Lower B (quads / single-leg)", [
        ("bw-squat", 3, 15, None),
        ("reverse-lunge", 3, 10, None),
        ("step-up", 3, 10, None),
        ("wall-sit", 2, None, 45),
        ("calf-raise", 2, 20, None),
        ("dead-bug", 3, 10, None),
    ]),
    "upper_b": ("Upper B (pull / core)", [
        ("inverted-row", 3, 8, None),
        ("reverse-snow-angel", 3, 12, None),
        ("superman-hold", 3, None, 20),
        ("hollow-hold", 3, None, 20),
        ("bird-dog", 3, 10, None),
    ]),
}

# Day of week mapping for 4x_upper_lower
_4X_UL_SCHEDULE = [
    (0, "lower_a"),      # Mon
    (1, "upper_a"),      # Tue
    # Wed handled specially (active recovery)
    (3, "lower_b"),      # Thu
    (4, "upper_b"),      # Fri
    # Sat/Sun handled specially (walk / rest)
]


def _progress(base_reps: int | None, base_hold: int | None, week_no: int) -> tuple[int | None, int | None]:
    """Apply weekly progression to base values.

    +1 rep/week (capped at 2x base), or +5s hold/week (capped at 2x base).
    """
    if base_reps is not None:
        new_reps = base_reps + (week_no - 1)
        cap = base_reps * 2
        return (min(new_reps, cap), None)
    if base_hold is not None:
        new_hold = base_hold + (week_no - 1) * 5
        cap = base_hold * 2
        return (None, min(new_hold, cap))
    return (None, None)


def _build_training_days(
    base: dict[str, tuple[str, list[tuple[str, int, int | None, int | None]]]],
    schedule: list[tuple[int, str]],
    week_no: int,
    duration_min: int,
) -> list[PrescribedSession]:
    """Build the training-day sessions for a split, applying progression."""
    sessions: list[PrescribedSession] = []
    for dow, session_key in schedule:
        label, exercises = base[session_key]
        prescribed: list[PrescribedSet] = []
        for slug, sets, base_reps, base_hold in exercises:
            reps, hold = _progress(base_reps, base_hold, week_no)
            prescribed.append(PrescribedSet(
                exercise_slug=slug,
                sets=sets,
                reps=reps,
                hold_s=hold,
            ))
        sessions.append(PrescribedSession(
            day_of_week=dow,
            session_type=session_key,
            label=label,
            duration_min=duration_min,
            exercises=prescribed,
        ))
    return sessions


def _mobility_day(dow: int, notes: str) -> PrescribedSession:
    return PrescribedSession(
        day_of_week=dow,
        session_type="mobility",
        label="Mobility + walk",
        duration_min=30,
        is_rest=False,
        notes=notes,
    )


def _rest_day(dow: int) -> PrescribedSession:
    return PrescribedSession(
        day_of_week=dow,
        session_type="rest",
        label="Rest day",
        duration_min=0,
        is_rest=True,
        notes="Full rest. 10-min mobility only if you feel tight.",
    )


def generate_week(split: SplitType, week_no: int) -> list[PrescribedSession]:
    """Return the 7-day prescription for `week_no` (1-indexed)."""
    if split == "5x_short":
        sessions = _build_training_days(_BASE_5X_SHORT, _5X_SCHEDULE, week_no, 20)
        sessions.append(_mobility_day(5, "10-min mobility routine + 45-60 min walk (target 15k+ steps)"))
        sessions.append(_rest_day(6))
        return sessions

    if split == "4x_upper_lower":
        sessions = _build_training_days(_BASE_4X_UPPER_LOWER, _4X_UL_SCHEDULE, week_no, 30)
        # Wed: active recovery between the two halves
        sessions.append(_mobility_day(2, "Active recovery: 10-min hip/sciatica mobility + zone-2 walk"))
        # Sat: walk-focused mobility
        sessions.append(_mobility_day(5, "10-min mobility + long walk (target 15k+ steps)"))
        # Sun: rest
        sessions.append(_rest_day(6))
        sessions.sort(key=lambda s: s.day_of_week)
        return sessions

    raise NotImplementedError(f"Split '{split}' not yet implemented")


def generate_programme(split: SplitType, weeks: int = 13) -> list[list[PrescribedSession]]:
    """Return a full N-week programme as a list of week prescriptions."""
    return [generate_week(split, w) for w in range(1, weeks + 1)]


def session_to_dict(session: PrescribedSession) -> dict:
    """Serialise a session for API/skill consumption."""
    return {
        "day_of_week": session.day_of_week,
        "session_type": session.session_type,
        "label": session.label,
        "duration_min": session.duration_min,
        "is_rest": session.is_rest,
        "notes": session.notes,
        "exercises": [
            {
                "exercise_slug": e.exercise_slug,
                "sets": e.sets,
                "reps": e.reps,
                "hold_s": e.hold_s,
                "note": e.note,
            }
            for e in session.exercises
        ],
    }
