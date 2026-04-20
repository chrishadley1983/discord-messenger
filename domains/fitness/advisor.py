"""Fitness advisor engine.

Hybrid rules-based system for PT/nutritionist-quality advice.
Builds a snapshot of all available data, then evaluates ~25 rules
that each produce structured advice with severity levels.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Literal

logger = logging.getLogger(__name__)

SEVERITY_ORDER = {"warning": 0, "caution": 1, "info": 2, "positive": 3}


@dataclass
class Advice:
    severity: Literal["positive", "info", "caution", "warning"]
    category: str
    headline: str
    detail: str
    action: str


@dataclass
class Snapshot:
    # Programme
    week_no: int = 0
    day_no: int = 0
    programme_active: bool = False
    is_training_day: bool = False
    session_type: str | None = None
    deficit_kcal: int = 550

    # Weight
    current_weight_kg: float | None = None
    start_weight_kg: float | None = None
    slope_kg_per_week: float | None = None
    weight_stalled: bool = False
    stalled_weeks: int = 0

    # Nutrition (today)
    calories_eaten: float = 0
    calories_target: int = 0
    protein_eaten: float = 0
    protein_target: int = 0
    carbs_eaten: float = 0
    fat_eaten: float = 0
    water_ml: float = 0
    water_target: int = 3500

    # Steps
    steps_today: int = 0
    steps_target: int = 15000
    steps_7d_avg: float = 0

    # Recovery
    sleep_hours: float | None = None
    sleep_score: int | None = None
    resting_hr: int | None = None
    resting_hr_5d: list[int] = field(default_factory=list)
    hrv_weekly_avg: int | None = None
    hrv_last_night: int | None = None
    hrv_status: str | None = None
    stress_avg: int | None = None

    # Training
    strength_sessions_week: int = 0
    strength_target: int = 4
    recent_rpe: list[int] = field(default_factory=list)
    mobility_streak: int = 0
    mobility_done_today: bool = False

    # Time
    hour_of_day: int = 12
    day_of_week: int = 0  # 0=Mon

    # Derived
    bmr: int = 0
    tdee: int = 0

    # Weekly nutrition (for pattern detection)
    days_over_target_this_week: int = 0
    avg_protein_pct_this_week: float = 100.0


async def build_snapshot() -> Snapshot:
    """Gather all available data into a single advisor snapshot."""
    from domains.fitness import service as fit
    from domains.fitness.trend import compute_trend
    from domains.fitness.programme_generator import generate_week
    from zoneinfo import ZoneInfo
    import httpx

    UK_TZ = ZoneInfo("Europe/London")
    now = datetime.now(UK_TZ)
    today = now.date()
    snap = Snapshot(hour_of_day=now.hour, day_of_week=today.weekday())

    programme = await fit.get_active_programme()
    if not programme:
        return snap

    snap.programme_active = True
    snap.week_no = fit.week_number(programme)
    snap.day_no = (today - date.fromisoformat(programme["start_date"])).days + 1
    snap.start_weight_kg = float(programme.get("start_weight_kg") or 0)
    snap.deficit_kcal = int(programme.get("deficit_kcal", 550))
    snap.steps_target = int(programme["daily_steps_target"])
    snap.strength_target = int(programme["weekly_strength_sessions"])

    # Today's prescribed workout
    if 1 <= snap.week_no <= programme["duration_weeks"]:
        sessions = generate_week(programme["split"], snap.week_no)
        today_session = next(
            (s for s in sessions if s.day_of_week == today.weekday()), None
        )
        if today_session:
            snap.is_training_day = today_session.session_type not in ("rest", "mobility")
            snap.session_type = today_session.session_type

    # Weight — filter history to programme start so pre-cut data doesn't fake trends
    weight_history = await fit.fetch_weight_history(30)
    prog_start = date.fromisoformat(programme["start_date"])
    trend = compute_trend(weight_history, programme_start=prog_start)
    snap.current_weight_kg = trend.trend_7d or trend.latest_raw
    snap.slope_kg_per_week = trend.slope_kg_per_week
    snap.weight_stalled = trend.stalled

    # Nutrition today
    nutrition = await fit.fetch_nutrition_today()
    snap.calories_eaten = nutrition["calories"]
    snap.protein_eaten = nutrition["protein_g"]
    snap.carbs_eaten = nutrition["carbs_g"]
    snap.fat_eaten = nutrition["fat_g"]
    snap.water_ml = nutrition["water_ml"]

    # Live targets
    steps_history = await fit.fetch_steps_history(7)
    snap.steps_today = int(await fit._live_steps_today(steps_history))
    snap.steps_7d_avg = (
        sum(p["value"] for p in steps_history) / len(steps_history)
        if steps_history else 0
    )

    current_weight = snap.current_weight_kg or float(programme["start_weight_kg"])
    avg_steps = max(snap.steps_7d_avg, snap.steps_target)
    live = fit.compute_current_targets(programme, current_weight, avg_steps)
    snap.calories_target = live.target_calories
    snap.protein_target = live.target_protein_g
    snap.bmr = live.bmr
    snap.tdee = live.tdee

    # Training load
    snap.strength_sessions_week = await fit.count_sessions_this_week()
    recent_sessions = await fit.get_sessions_in_range(
        today - timedelta(days=14), today
    )
    snap.recent_rpe = [
        int(s["rpe"]) for s in recent_sessions
        if s.get("rpe") is not None
    ]

    # Mobility
    mob = await fit.mobility_today()
    snap.mobility_done_today = mob.get("morning", False) or mob.get("evening", False)

    # Recovery: Garmin data (last 5 days for HR trend)
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            resp = await c.get(
                f"{fit.SUPABASE_URL}/rest/v1/garmin_daily_summary",
                headers=fit._read_headers(),
                params={
                    "select": "date,resting_hr,sleep_hours,sleep_score,hrv_weekly_avg,hrv_last_night,hrv_status,avg_stress",
                    "user_id": "eq.chris",
                    "date": f"gte.{(today - timedelta(days=5)).isoformat()}",
                    "order": "date.desc",
                    "limit": "5",
                },
            )
            resp.raise_for_status()
            garmin_rows = resp.json()
    except Exception:
        garmin_rows = []

    if garmin_rows:
        latest = garmin_rows[0]
        snap.sleep_hours = latest.get("sleep_hours")
        snap.sleep_score = latest.get("sleep_score")
        snap.resting_hr = latest.get("resting_hr")
        snap.hrv_weekly_avg = latest.get("hrv_weekly_avg")
        snap.hrv_last_night = latest.get("hrv_last_night")
        snap.hrv_status = latest.get("hrv_status")
        snap.stress_avg = latest.get("avg_stress")
        snap.resting_hr_5d = [
            int(r["resting_hr"]) for r in garmin_rows
            if r.get("resting_hr") is not None
        ]

    # Mobility streak (reuse the endpoint logic)
    try:
        cutoff = (today - timedelta(days=30)).isoformat()
        async with httpx.AsyncClient(timeout=10) as c:
            resp = await c.get(
                f"{fit.SUPABASE_URL}/rest/v1/{fit.MOBILITY_TABLE}",
                headers=fit._read_headers(),
                params={
                    "select": "session_date",
                    "user_id": "eq.chris",
                    "session_date": f"gte.{cutoff}",
                    "order": "session_date.desc",
                },
            )
            resp.raise_for_status()
            mob_rows = resp.json()
        days_done = {str(r["session_date"]) for r in mob_rows}
        streak = 0
        for i in range(30):
            d = (today - timedelta(days=i)).isoformat()
            if d in days_done:
                streak += 1
            elif i == 0:
                continue
            else:
                break
        snap.mobility_streak = streak
    except Exception:
        pass

    # Weekly nutrition pattern (this ISO week so far)
    try:
        week_start = today - timedelta(days=today.weekday())
        async with httpx.AsyncClient(timeout=10) as c:
            resp = await c.get(
                f"{fit.SUPABASE_URL}/rest/v1/nutrition_logs",
                headers=fit._read_headers(),
                params={
                    "select": "logged_at,calories,protein_g",
                    "and": f"(logged_at.gte.{week_start.isoformat()}T00:00:00,logged_at.lt.{(today + timedelta(days=1)).isoformat()}T00:00:00)",
                },
            )
            resp.raise_for_status()
            nut_rows = resp.json()

        by_day: dict[str, dict] = {}
        for r in nut_rows:
            d = str(r["logged_at"])[:10]
            if d not in by_day:
                by_day[d] = {"cal": 0.0, "pro": 0.0}
            by_day[d]["cal"] += float(r.get("calories") or 0)
            by_day[d]["pro"] += float(r.get("protein_g") or 0)

        if by_day:
            snap.days_over_target_this_week = sum(
                1 for v in by_day.values() if v["cal"] > snap.calories_target * 1.05
            )
            pro_pcts = [
                (v["pro"] / snap.protein_target * 100) if snap.protein_target else 100
                for v in by_day.values()
            ]
            snap.avg_protein_pct_this_week = sum(pro_pcts) / len(pro_pcts)
    except Exception:
        pass

    return snap


# ══════════════════════════════════════════════════════════════════════
# RULES ENGINE
# ══════════════════════════════════════════════════════════════════════

def _deficit_actual(s: Snapshot) -> float:
    """Current actual deficit: target - eaten. Positive = in deficit."""
    return s.calories_target - s.calories_eaten


def _rate_pct_bw(s: Snapshot) -> float | None:
    """Weekly loss as % of body weight."""
    if s.slope_kg_per_week is None or s.current_weight_kg is None:
        return None
    return abs(s.slope_kg_per_week) / s.current_weight_kg * 100


def _hr_trend(s: Snapshot) -> float | None:
    """Resting HR change over the 5-day window. Positive = rising."""
    hrs = s.resting_hr_5d
    if len(hrs) < 3:
        return None
    return hrs[0] - hrs[-1]


def _rpe_trend(s: Snapshot) -> float | None:
    """RPE trend: avg of recent 3 vs older sessions."""
    rpe = s.recent_rpe
    if len(rpe) < 4:
        return None
    recent = sum(rpe[:3]) / 3
    older = sum(rpe[3:]) / len(rpe[3:])
    return recent - older


# ── Energy balance rules ─────────────────────────────────────────────

def _rule_extreme_deficit(s: Snapshot) -> Advice | None:
    deficit = _deficit_actual(s)
    if deficit <= 1000 or s.calories_eaten == 0 or s.hour_of_day < 19:
        return None
    return Advice(
        severity="warning",
        category="energy_balance",
        headline="Dangerously large deficit",
        detail=f"You're {int(deficit)} kcal under target. Deficits over 1000 kcal trigger muscle breakdown, hormonal disruption, and binge risk — especially in week {s.week_no} of a cut.",
        action="Eat something substantial now. A meal with 40g+ protein and complex carbs. This isn't discipline, it's damage.",
    )


def _rule_aggressive_deficit_training(s: Snapshot) -> Advice | None:
    deficit = _deficit_actual(s)
    if (
        not s.is_training_day
        or deficit <= 700
        or s.calories_eaten == 0
        or s.hour_of_day < 15
    ):
        return None
    return Advice(
        severity="warning",
        category="energy_balance",
        headline="Too deep a deficit on a training day",
        detail=f"You're {int(deficit)} kcal under target with a {s.session_type} session today. Training under-fuelled increases injury risk and kills performance.",
        action="Add 200-300 kcal from carbs before your session. A banana and toast, or oats with honey.",
    )


def _rule_aggressive_deficit_rest(s: Snapshot) -> Advice | None:
    deficit = _deficit_actual(s)
    if (
        s.is_training_day
        or deficit <= 700
        or s.calories_eaten == 0
        or s.hour_of_day < 19
    ):
        return None
    sleep_ok = s.sleep_score is None or s.sleep_score >= 60
    if sleep_ok:
        return Advice(
            severity="info",
            category="energy_balance",
            headline="Deep deficit on a rest day — acceptable",
            detail=f"You're {int(deficit)} kcal under target, but it's a rest day and recovery looks fine. A slightly deeper cut on low-activity days can accelerate progress.",
            action="Just make sure you hit your protein target. The deficit itself is OK today.",
        )
    return Advice(
        severity="caution",
        category="energy_balance",
        headline="Deep deficit with poor recovery",
        detail=f"You're {int(deficit)} kcal under target and your sleep score was {s.sleep_score}. Poor sleep + deep deficit compounds fatigue.",
        action="Eat closer to target today. Prioritise protein and slow carbs for better sleep tonight.",
    )


def _rule_surplus_in_cut(s: Snapshot) -> Advice | None:
    if s.calories_target <= 0 or s.calories_eaten == 0:
        return None
    over_pct = (s.calories_eaten - s.calories_target) / s.calories_target * 100
    if over_pct < 15:
        return None
    over_kcal = int(s.calories_eaten - s.calories_target)
    if s.days_over_target_this_week >= 3:
        return Advice(
            severity="caution",
            category="energy_balance",
            headline="Pattern of overshooting calories",
            detail=f"You're {over_kcal} kcal over target today, and this is the {s.days_over_target_this_week}th day this week you've exceeded it. One day is a blip, three is a pattern.",
            action="Track what's causing the overshoot — snacking, portion sizes, or liquid calories. Fix the pattern, not just today.",
        )
    return Advice(
        severity="info",
        category="energy_balance",
        headline="Over calorie target today",
        detail=f"You're {over_kcal} kcal over target. One day won't derail the programme — weekly average matters more than daily perfection.",
        action="Don't try to compensate tomorrow by under-eating. Just get back on target.",
    )


def _rule_moderate_deficit_sweet_spot(s: Snapshot) -> Advice | None:
    if s.calories_eaten == 0 or s.calories_target <= 0:
        return None
    pct = s.calories_eaten / s.calories_target * 100
    if 90 <= pct <= 105 and s.hour_of_day >= 18:
        return Advice(
            severity="positive",
            category="energy_balance",
            headline="Calories dialled in today",
            detail=f"You're at {int(s.calories_eaten)}/{s.calories_target} kcal — right in the sweet spot.",
            action="Keep it up. This is what sustainable fat loss looks like.",
        )
    return None


# ── Protein rules ────────────────────────────────────────────────────

def _rule_protein_critical(s: Snapshot) -> Advice | None:
    if s.protein_target <= 0 or s.protein_eaten == 0:
        return None
    pct = s.protein_eaten / s.protein_target * 100
    if pct >= 60 or s.hour_of_day < 16:
        return None
    return Advice(
        severity="warning",
        category="nutrition",
        headline="Protein critically low",
        detail=f"Only {int(s.protein_eaten)}g of {s.protein_target}g protein ({int(pct)}%) and it's {s.hour_of_day}:00. In a deficit, low protein = muscle loss. Full stop.",
        action=f"You need {int(s.protein_target - s.protein_eaten)}g more. Two scoops of whey (50g) + a chicken breast (40g) would close the gap.",
    )


def _rule_protein_undershoot(s: Snapshot) -> Advice | None:
    if s.protein_target <= 0 or s.protein_eaten == 0:
        return None
    pct = s.protein_eaten / s.protein_target * 100
    if pct >= 80 or pct < 60 or s.hour_of_day < 18:
        return None
    return Advice(
        severity="caution",
        category="nutrition",
        headline="Behind on protein",
        detail=f"{int(s.protein_eaten)}g of {s.protein_target}g protein ({int(pct)}%). At {s.deficit_kcal} kcal deficit, every gram matters for muscle preservation.",
        action=f"Add a high-protein snack: Greek yoghurt, whey shake, or eggs. Need ~{int(s.protein_target - s.protein_eaten)}g more.",
    )


def _rule_protein_nailing_it(s: Snapshot) -> Advice | None:
    if s.protein_target <= 0 or s.protein_eaten == 0:
        return None
    pct = s.protein_eaten / s.protein_target * 100
    if pct < 95 or s.hour_of_day < 18:
        return None
    return Advice(
        severity="positive",
        category="nutrition",
        headline="Protein target hit",
        detail=f"{int(s.protein_eaten)}g protein — that's exactly what your muscles need to hold on during this cut.",
        action="This is the single most important macro. Keep prioritising it.",
    )


# ── Hydration rules ─────────────────────────────────────────────────

def _rule_dehydrated(s: Snapshot) -> Advice | None:
    if s.water_ml == 0 or s.hour_of_day < 15:
        return None
    pct = s.water_ml / s.water_target * 100
    if pct >= 60:
        return None
    return Advice(
        severity="caution",
        category="hydration",
        headline="Behind on water",
        detail=f"{int(s.water_ml)}ml of {s.water_target}ml target ({int(pct)}%). Dehydration tanks performance, recovery, and makes hunger worse in a deficit.",
        action=f"Drink {int(s.water_target - s.water_ml)}ml before bed. Keep a bottle visible.",
    )


# ── Weight trend rules ───────────────────────────────────────────────

def _rule_rate_too_fast(s: Snapshot) -> Advice | None:
    rate = _rate_pct_bw(s)
    if rate is None or rate <= 1.0:
        return None
    return Advice(
        severity="warning",
        category="weight_trend",
        headline=f"Losing too fast — {abs(s.slope_kg_per_week or 0):.1f} kg/week",
        detail=f"That's {rate:.1f}% of body weight per week. Above 1% sustained = muscle loss, metabolic adaptation, and hormonal disruption. The scale might look good but you're burning muscle, not just fat.",
        action="Increase calories by 150-200 kcal (add carbs around training). The goal is 0.5-1% BW/week.",
    )


def _rule_rate_perfect(s: Snapshot) -> Advice | None:
    rate = _rate_pct_bw(s)
    if rate is None or s.slope_kg_per_week is None:
        return None
    if s.slope_kg_per_week >= 0:
        return None
    if 0.5 <= rate <= 1.0:
        return Advice(
            severity="positive",
            category="weight_trend",
            headline=f"Perfect rate of loss — {abs(s.slope_kg_per_week):.1f} kg/week",
            detail=f"That's {rate:.1f}% of body weight — the research-backed sweet spot for losing fat while preserving muscle.",
            action="Don't change anything. The plan is working.",
        )
    return None


def _rule_weight_stalled(s: Snapshot) -> Advice | None:
    if not s.weight_stalled:
        return None
    return Advice(
        severity="caution",
        category="weight_trend",
        headline="Weight trend has stalled",
        detail="Scale hasn't moved meaningfully in 2+ weeks. This can be water retention, adaptation, or the deficit has closed as you've lost weight.",
        action="First: check adherence (are you actually hitting targets?). If yes: recalibrate — drop 100 kcal, add 2k steps. If stalled 3+ weeks, consider a 7-10 day maintenance phase to reset hormones.",
    )


def _rule_diet_break(s: Snapshot) -> Advice | None:
    if not s.weight_stalled:
        return None
    adherence_poor = s.avg_protein_pct_this_week < 70
    if not adherence_poor:
        return None
    return Advice(
        severity="caution",
        category="weight_trend",
        headline="Consider a diet break",
        detail="Weight stalled AND adherence is dropping — classic sign of diet fatigue. Pushing harder from here usually triggers a binge-restrict cycle.",
        action="Take 7-10 days at maintenance calories (TDEE, no deficit). Keep protein and training the same. You won't gain fat — you'll reset leptin, cortisol, and motivation. Then resume the cut.",
    )


# ── Recovery rules ───────────────────────────────────────────────────

def _rule_poor_sleep_training(s: Snapshot) -> Advice | None:
    if s.sleep_score is None or s.sleep_score >= 60 or not s.is_training_day:
        return None
    return Advice(
        severity="caution",
        category="recovery",
        headline=f"Poor sleep ({s.sleep_score}/100) + training day",
        detail=f"Sleep score of {s.sleep_score} means compromised CNS recovery. Training hard today risks injury and poor adaptation — you won't get stronger from this session, just more fatigued.",
        action=f"Drop RPE by 1-2 for your {s.session_type} session. Or swap for light cardio / mobility. Live to train another day.",
    )


def _rule_resting_hr_rising(s: Snapshot) -> Advice | None:
    delta = _hr_trend(s)
    if delta is None or delta < 3:
        return None
    return Advice(
        severity="caution",
        category="recovery",
        headline=f"Resting HR trending up (+{delta:.0f} bpm over 5 days)",
        detail="Rising resting HR is a classic overtraining signal. It means your body is under systemic stress — the deficit, training load, and/or poor sleep are accumulating.",
        action="Drop training volume by 20% for 3-4 days. Prioritise sleep. If HR doesn't come back down, take a full rest day.",
    )


def _rule_hrv_low(s: Snapshot) -> Advice | None:
    if s.hrv_status is None:
        return None
    status_lower = s.hrv_status.lower()
    if status_lower in ("balanced", "high", "optimal"):
        return None
    return Advice(
        severity="caution",
        category="recovery",
        headline=f"HRV status: {s.hrv_status}",
        detail=f"Garmin reports HRV as '{s.hrv_status}' (weekly avg: {s.hrv_weekly_avg}ms, last night: {s.hrv_last_night}ms). Low HRV means your autonomic nervous system is stressed — poor recovery capacity.",
        action="Reduce training intensity today. If HRV stays low 3+ days, take a deload.",
    )


def _rule_high_stress(s: Snapshot) -> Advice | None:
    if s.stress_avg is None or s.stress_avg < 50:
        return None
    if s.is_training_day:
        return Advice(
            severity="caution",
            category="recovery",
            headline=f"High stress level ({s.stress_avg}/100) on a training day",
            detail="Garmin stress above 50 combined with training adds more cortisol on top. Cortisol inhibits muscle protein synthesis and promotes fat retention — the opposite of what you want in a cut.",
            action="Keep the session short and moderate. No ego lifts today.",
        )
    return None


def _rule_good_sleep(s: Snapshot) -> Advice | None:
    if s.sleep_score is None or s.sleep_score < 80:
        return None
    return Advice(
        severity="positive",
        category="recovery",
        headline=f"Solid sleep — {s.sleep_score}/100",
        detail=f"{s.sleep_hours or '?'}h with quality score {s.sleep_score}. Good sleep is the single biggest recovery factor, especially in a calorie deficit.",
        action="Keep doing whatever you did last night. This is where the gains actually happen.",
    )


# ── Training rules ───────────────────────────────────────────────────

def _rule_rpe_creep(s: Snapshot) -> Advice | None:
    delta = _rpe_trend(s)
    if delta is None or delta < 1.5:
        return None
    return Advice(
        severity="caution",
        category="training",
        headline="RPE creeping up without load increase",
        detail=f"Average RPE has risen by {delta:.1f} over your last sessions without adding weight or reps. That's fatigue accumulating, not getting weaker.",
        action="Program a deload: same exercises, 60% of normal volume, RPE 5-6 max. One easy week now prevents two forced weeks later.",
    )


def _rule_missed_sessions(s: Snapshot) -> Advice | None:
    if s.day_of_week < 4:
        return None
    if s.strength_sessions_week >= s.strength_target - 1:
        return None
    remaining_days = 6 - s.day_of_week
    sessions_needed = s.strength_target - s.strength_sessions_week
    if sessions_needed <= remaining_days:
        return Advice(
            severity="info",
            category="training",
            headline=f"Behind on training — {s.strength_sessions_week}/{s.strength_target} sessions this week",
            detail=f"You have {remaining_days} days left to fit in {sessions_needed} session(s). Consistency matters more than intensity.",
            action="Fit them in. Even a 20-minute session counts. Don't let perfect be the enemy of done.",
        )
    return Advice(
        severity="caution",
        category="training",
        headline=f"Likely to miss training target this week",
        detail=f"Only {s.strength_sessions_week}/{s.strength_target} sessions done with {remaining_days} day(s) left. Missing 2+ sessions per week erodes the programme's strength-retention benefit.",
        action="Do what you can. Prioritise compound movements if time is short.",
    )


def _rule_mobility_dropped(s: Snapshot) -> Advice | None:
    if s.mobility_streak > 0 or s.mobility_done_today:
        return None
    return Advice(
        severity="caution",
        category="training",
        headline="Mobility streak broken",
        detail="No mobility logged recently. Skipping mobility during a training programme increases injury risk — tight hips and thoracic spine are the usual culprits.",
        action="10 minutes. That's all. Do the daily flow — it's designed to hit exactly the spots that seize up during a cut.",
    )


def _rule_mobility_consistent(s: Snapshot) -> Advice | None:
    if s.mobility_streak < 7:
        return None
    return Advice(
        severity="positive",
        category="training",
        headline=f"Mobility streak: {s.mobility_streak} days",
        detail="A week+ of daily mobility. This is doing more for injury prevention than most people's entire warm-up routine.",
        action="Keep the streak alive. Consistency here compounds over the programme.",
    )


# ── Composite rules ──────────────────────────────────────────────────

def _rule_everything_on_point(s: Snapshot) -> Advice | None:
    if s.calories_eaten == 0 or s.hour_of_day < 20:
        return None
    cal_pct = s.calories_eaten / s.calories_target * 100 if s.calories_target else 0
    pro_pct = s.protein_eaten / s.protein_target * 100 if s.protein_target else 0
    steps_ok = s.steps_today >= s.steps_target * 0.9
    cal_ok = 90 <= cal_pct <= 105
    pro_ok = pro_pct >= 90
    if cal_ok and pro_ok and steps_ok:
        return Advice(
            severity="positive",
            category="overall",
            headline="Nailing it today",
            detail=f"Calories: {int(s.calories_eaten)}/{s.calories_target}. Protein: {int(s.protein_eaten)}/{s.protein_target}g. Steps: {s.steps_today:,}/{s.steps_target:,}. Everything is on point.",
            action="This is what elite consistency looks like. One day at a time, and today was a win.",
        )
    return None


# ── Rule registry + evaluator ────────────────────────────────────────

ALL_RULES = [
    _rule_extreme_deficit,
    _rule_aggressive_deficit_training,
    _rule_aggressive_deficit_rest,
    _rule_surplus_in_cut,
    _rule_moderate_deficit_sweet_spot,
    _rule_protein_critical,
    _rule_protein_undershoot,
    _rule_protein_nailing_it,
    _rule_dehydrated,
    _rule_rate_too_fast,
    _rule_rate_perfect,
    _rule_weight_stalled,
    _rule_diet_break,
    _rule_poor_sleep_training,
    _rule_resting_hr_rising,
    _rule_hrv_low,
    _rule_high_stress,
    _rule_good_sleep,
    _rule_rpe_creep,
    _rule_missed_sessions,
    _rule_mobility_dropped,
    _rule_mobility_consistent,
    _rule_everything_on_point,
]


def evaluate_rules(snap: Snapshot) -> list[Advice]:
    """Run all rules, return sorted by severity (warnings first)."""
    results: list[Advice] = []
    for rule_fn in ALL_RULES:
        try:
            advice = rule_fn(snap)
            if advice is not None:
                results.append(advice)
        except Exception as e:
            logger.warning(f"Rule {rule_fn.__name__} failed: {e}")
    results.sort(key=lambda a: SEVERITY_ORDER.get(a.severity, 99))
    return results


async def get_advice() -> dict:
    """Full advisor pipeline: build snapshot, run rules, return structured output."""
    snap = await build_snapshot()
    advice_list = evaluate_rules(snap)
    return {
        "advice": [
            {
                "severity": a.severity,
                "category": a.category,
                "headline": a.headline,
                "detail": a.detail,
                "action": a.action,
            }
            for a in advice_list
        ],
        "snapshot": {
            "programme_active": snap.programme_active,
            "week_no": snap.week_no,
            "day_no": snap.day_no,
            "is_training_day": snap.is_training_day,
            "session_type": snap.session_type,
            "calories": {"eaten": int(snap.calories_eaten), "target": snap.calories_target},
            "protein": {"eaten": int(snap.protein_eaten), "target": snap.protein_target},
            "steps": {"today": snap.steps_today, "target": snap.steps_target},
            "weight_kg": round(snap.current_weight_kg, 1) if snap.current_weight_kg else None,
            "slope_kg_per_week": round(snap.slope_kg_per_week, 2) if snap.slope_kg_per_week else None,
            "sleep_score": snap.sleep_score,
            "resting_hr": snap.resting_hr,
            "hrv_status": snap.hrv_status,
            "mobility_streak": snap.mobility_streak,
            "strength_sessions": {"done": snap.strength_sessions_week, "target": snap.strength_target},
        },
        "counts": {
            "warning": sum(1 for a in advice_list if a.severity == "warning"),
            "caution": sum(1 for a in advice_list if a.severity == "caution"),
            "info": sum(1 for a in advice_list if a.severity == "info"),
            "positive": sum(1 for a in advice_list if a.severity == "positive"),
            "total": len(advice_list),
        },
    }
