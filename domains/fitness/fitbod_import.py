"""Fitbod CSV import (Phase 2).

Fitbod has no public API; Settings → Export Workout Data emails a CSV with
one row per set:

    Date,Exercise,Reps,Weight(kg),Duration(s),Distance(m),Incline,Resistance,isWarmup,Note,multiplier
    2026-09-05 10:12:33 +0100,Lat Pulldown,10,33.0,0,0,0,0,false,,1

``parse_fitbod_csv`` (pure) groups rows into sessions per calendar day and
maps Fitbod exercise names onto our slugs; ``import_sessions`` logs them via
the normal service path (so the plan adapts and next-session targets update),
deduping on a per-day content hash stored in ``external_id``.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)

# Fitbod name (lower, stripped) -> (slug, category)
ALIASES: dict[str, tuple[str, str]] = {
    "lat pulldown": ("lat-pulldown", "pull"), "wide grip lat pulldown": ("lat-pulldown", "pull"),
    "cable lat pulldown": ("lat-pulldown", "pull"), "close grip lat pulldown": ("lat-pulldown", "pull"),
    "machine chest press": ("chest-press", "push"), "chest press": ("chest-press", "push"),
    "seated machine chest press": ("chest-press", "push"), "machine bench press": ("chest-press", "push"),
    "seated cable row": ("seated-row", "pull"), "seated row": ("seated-row", "pull"),
    "machine row": ("seated-row", "pull"), "seated machine row": ("seated-row", "pull"),
    "machine shoulder press": ("shoulder-press", "push"), "shoulder press": ("shoulder-press", "push"),
    "seated machine shoulder press": ("shoulder-press", "push"),
    "leg press": ("leg-press", "legs"), "machine leg press": ("leg-press", "legs"),
    "leg extension": ("leg-extension", "legs"), "machine leg extension": ("leg-extension", "legs"),
    "seated leg curl": ("seated-leg-curl", "legs"), "leg curl": ("seated-leg-curl", "legs"),
    "lying leg curl": ("seated-leg-curl", "legs"),
    "hip abduction": ("hip-abduction", "legs"), "machine hip abduction": ("hip-abduction", "legs"),
    "seated calf raise": ("seated-calf-raise", "legs"), "machine calf raise": ("seated-calf-raise", "legs"),
    "pec deck": ("pec-fly", "push"), "machine fly": ("pec-fly", "push"), "chest fly": ("pec-fly", "push"),
    "reverse machine fly": ("rear-delt-fly", "pull"), "rear delt fly": ("rear-delt-fly", "pull"),
    "face pull": ("cable-face-pull", "pull"), "cable face pull": ("cable-face-pull", "pull"),
    "cable curl": ("cable-curl", "pull"), "cable bicep curl": ("cable-curl", "pull"),
    "triceps pushdown": ("triceps-pushdown", "push"), "cable triceps pushdown": ("triceps-pushdown", "push"),
    "tricep pushdown": ("triceps-pushdown", "push"), "rope pushdown": ("triceps-pushdown", "push"),
    "dumbbell lateral raise": ("lateral-raise", "push"), "lateral raise": ("lateral-raise", "push"),
    "assisted pull up": ("assisted-pull-up", "pull"), "assisted pull-up": ("assisted-pull-up", "pull"),
    "cable glute kickback": ("cable-glute-kickback", "legs"), "glute kickback": ("cable-glute-kickback", "legs"),
    "pallof press": ("cable-pallof-press", "core"), "cable pallof press": ("cable-pallof-press", "core"),
    "push up": ("push-up", "push"), "push-up": ("push-up", "push"), "plank": ("plank", "core"),
    "goblet squat": ("bw-squat", "legs"), "bodyweight squat": ("bw-squat", "legs"),
    "glute bridge": ("glute-bridge", "legs"), "dead bug": ("dead-bug", "core"),
}

_UPPER = {"push", "pull"}
_LOWER = {"legs"}
_CATEGORY_HINTS = [
    (re.compile(r"squat|lunge|leg|calf|glute|hip|deadlift|rdl|hamstring|quad", re.I), "legs"),
    (re.compile(r"row|pull|lat|curl|face|rear delt|shrug|back", re.I), "pull"),
    (re.compile(r"press|push|fly|dip|tricep|shoulder|lateral|chest", re.I), "push"),
    (re.compile(r"plank|crunch|ab |abs|core|pallof|dead bug|twist", re.I), "core"),
]


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def map_exercise(name: str) -> tuple[str, str]:
    key = re.sub(r"\s+", " ", name.strip().lower())
    key = key.replace("(machine)", "machine").replace("-", " ").strip()
    if key in ALIASES:
        return ALIASES[key]
    for alias, val in ALIASES.items():
        if key.endswith(alias) or key.startswith(alias):
            return val
    cat = next((c for rx, c in _CATEGORY_HINTS if rx.search(name)), "other")
    return slugify(name), cat


def _to_bool(v: str) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes", "y")


def _to_float(v) -> float | None:
    try:
        f = float(str(v).strip())
        return f
    except Exception:
        return None


def _parse_date(v: str) -> str:
    s = str(v).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return s[:10]


def infer_session_type(categories: list[str]) -> str:
    cats = {c for c in categories if c in _UPPER | _LOWER}
    if not cats:
        return "full_body"
    if cats <= _UPPER:
        return "upper"
    if cats <= _LOWER:
        return "lower"
    return "full_body"


def parse_fitbod_csv(text: str, include_warmups: bool = False) -> list[dict]:
    """CSV text -> [{session_date, session_type, external_id, sets: [...], exercises: [names]}]."""
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    if not reader.fieldnames:
        return []
    cols = {c.strip().lower(): c for c in reader.fieldnames}

    def col(row, *names):
        for n in names:
            k = cols.get(n.lower())
            if k is not None:
                return row.get(k)
        return None

    by_day: dict[str, list[dict]] = defaultdict(list)
    for row in reader:
        name = (col(row, "Exercise") or "").strip()
        if not name:
            continue
        if not include_warmups and _to_bool(col(row, "isWarmup") or ""):
            continue
        d = _parse_date(col(row, "Date") or "")
        reps = _to_float(col(row, "Reps"))
        weight = _to_float(col(row, "Weight(kg)", "Weight (kg)", "Weight"))
        dur = _to_float(col(row, "Duration(s)", "Duration (s)"))
        mult = _to_float(col(row, "multiplier")) or 1
        slug, cat = map_exercise(name)
        by_day[d].append({
            "exercise_slug": slug, "exercise_name": name, "category": cat,
            "reps": int(reps) if reps else None,
            "hold_s": int(dur) if (dur and not reps) else None,
            "weight_kg": round(weight * (mult if mult and mult > 0 else 1), 2) if weight else None,
            "notes": (col(row, "Note") or "").strip() or None,
        })

    sessions = []
    for d in sorted(by_day):
        sets = by_day[d]
        counter: dict[str, int] = defaultdict(int)
        for s in sets:
            counter[s["exercise_slug"]] += 1
            s["set_no"] = counter[s["exercise_slug"]]
            s["target_reps"] = s["reps"]
        digest = hashlib.sha1(("|".join(f"{s['exercise_slug']}:{s['reps']}:{s['weight_kg']}" for s in sets)).encode()).hexdigest()[:16]
        sessions.append({
            "session_date": d,
            "session_type": infer_session_type([s["category"] for s in sets]),
            "external_id": f"fitbod:{d}:{digest}",
            "exercises": list(dict.fromkeys(s["exercise_name"] for s in sets)),
            "sets": sets,
        })
    return sessions


async def import_sessions(sessions: list[dict], *, dry_run: bool = False, skip_if_day_logged: bool = True) -> dict:
    """Log parsed Fitbod sessions via the service; dedupe on external_id / same-day."""
    from domains.fitness import service as fit
    from datetime import date, timedelta
    import httpx

    if not sessions:
        return {"imported": 0, "skipped": [], "dry_run": dry_run, "sessions": []}
    dates = [date.fromisoformat(s["session_date"]) for s in sessions]
    existing = await fit.get_sessions_in_range(min(dates) - timedelta(days=1), max(dates) + timedelta(days=1))
    by_ext = {e.get("external_id") for e in existing if e.get("external_id")}
    by_day = defaultdict(list)
    for e in existing:
        by_day[str(e["session_date"])].append(e)
    programme = await fit.get_active_programme()

    imported, skipped, out = 0, [], []
    for s in sessions:
        if s["external_id"] in by_ext:
            skipped.append({"date": s["session_date"], "reason": "already imported"})
            continue
        if skip_if_day_logged and any(e.get("session_type") not in ("mobility", "rest", "cardio") for e in by_day.get(s["session_date"], [])):
            skipped.append({"date": s["session_date"], "reason": "a strength session is already logged that day (Peter)"})
            continue
        out.append({"date": s["session_date"], "type": s["session_type"], "exercises": s["exercises"], "sets": len(s["sets"])})
        if dry_run:
            continue
        wk = fit.week_number(programme, date.fromisoformat(s["session_date"])) if programme else None
        session = await fit.log_workout(
            session_type=s["session_type"], session_date=s["session_date"], notes="Imported from Fitbod",
            sets=s["sets"], programme_id=programme["id"] if programme else None, week_no=wk,
        )
        async with httpx.AsyncClient(timeout=15) as c:
            await c.patch(fit._url(fit.SESSIONS_TABLE), headers=fit._write_headers(),
                          params={"id": f"eq.{session['id']}"}, json={"source": "fitbod", "external_id": s["external_id"]})
        # adapt the plan like a Peter log would
        try:
            if programme and programme.get("split") == "plan":
                plan, row = await fit.get_plan_or_default()
                new_plan, changes = fit.tp.reconcile_plan(plan, s["session_type"], s["sets"])
                if changes:
                    await fit.save_plan(new_plan, rationale="Adapted from Fitbod import: " + "; ".join(changes), created_by="auto")
        except Exception as e:
            logger.warning(f"fitbod plan reconcile failed: {e}")
        imported += 1
    return {"imported": imported, "skipped": skipped, "dry_run": dry_run, "sessions": out}
