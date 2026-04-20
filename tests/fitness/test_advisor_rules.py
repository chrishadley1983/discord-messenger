"""Unit tests for the fitness advisor rules engine.

Tests every rule with triggering conditions, non-triggering conditions,
and boundary cases. Uses controlled Snapshot objects — no I/O.
"""
import pytest
from domains.fitness.advisor import (
    Snapshot, Advice, evaluate_rules,
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
    _deficit_actual,
    _rate_pct_bw,
    _hr_trend,
    _rpe_trend,
)


def _snap(**overrides) -> Snapshot:
    """Build a Snapshot with sensible defaults and overrides."""
    defaults = dict(
        programme_active=True,
        week_no=3,
        day_no=18,
        is_training_day=False,
        session_type=None,
        deficit_kcal=550,
        current_weight_kg=88.0,
        start_weight_kg=90.0,
        slope_kg_per_week=-0.7,
        weight_stalled=False,
        calories_eaten=2000,
        calories_target=2343,
        protein_eaten=120,
        protein_target=150,
        water_ml=2500,
        water_target=3500,
        steps_today=12000,
        steps_target=15000,
        steps_7d_avg=13000,
        sleep_hours=7.5,
        sleep_score=75,
        resting_hr=60,
        resting_hr_5d=[60, 59, 60, 58, 59],
        hrv_weekly_avg=45,
        hrv_last_night=42,
        hrv_status="BALANCED",
        stress_avg=35,
        strength_sessions_week=3,
        strength_target=4,
        recent_rpe=[7, 7, 6, 6, 6],
        mobility_streak=5,
        mobility_done_today=True,
        hour_of_day=14,
        day_of_week=2,
        bmr=1808,
        tdee=2893,
        days_over_target_this_week=0,
        avg_protein_pct_this_week=90.0,
    )
    defaults.update(overrides)
    return Snapshot(**defaults)


# ── Helper function tests ────────────────────────────────────────────


class TestHelpers:
    def test_deficit_actual_in_deficit(self):
        s = _snap(calories_eaten=2000, calories_target=2343)
        assert _deficit_actual(s) == 343

    def test_deficit_actual_surplus(self):
        s = _snap(calories_eaten=2800, calories_target=2343)
        assert _deficit_actual(s) == -457

    def test_rate_pct_bw(self):
        s = _snap(slope_kg_per_week=-0.88, current_weight_kg=88.0)
        rate = _rate_pct_bw(s)
        assert rate == pytest.approx(1.0, abs=0.01)

    def test_rate_pct_bw_none_if_no_slope(self):
        s = _snap(slope_kg_per_week=None)
        assert _rate_pct_bw(s) is None

    def test_hr_trend_rising(self):
        s = _snap(resting_hr_5d=[63, 62, 61, 60, 59])
        assert _hr_trend(s) == 4  # 63 - 59

    def test_hr_trend_stable(self):
        s = _snap(resting_hr_5d=[60, 60, 60, 60, 60])
        assert _hr_trend(s) == 0

    def test_hr_trend_none_if_insufficient(self):
        s = _snap(resting_hr_5d=[60, 59])
        assert _hr_trend(s) is None

    def test_rpe_trend_rising(self):
        s = _snap(recent_rpe=[9, 8, 8, 6, 6, 6])
        delta = _rpe_trend(s)
        assert delta is not None
        assert delta > 1.5

    def test_rpe_trend_stable(self):
        s = _snap(recent_rpe=[6, 6, 6, 6, 6])
        delta = _rpe_trend(s)
        assert delta is not None
        assert delta < 0.5

    def test_rpe_trend_none_if_insufficient(self):
        s = _snap(recent_rpe=[7, 6, 6])
        assert _rpe_trend(s) is None


# ── Energy balance rules ─────────────────────────────────────────────


class TestExtremeDeficit:
    def test_fires_over_1000(self):
        s = _snap(calories_eaten=1200, calories_target=2343)
        a = _rule_extreme_deficit(s)
        assert a is not None
        assert a.severity == "warning"
        assert "1143" in a.detail

    def test_silent_at_900(self):
        s = _snap(calories_eaten=1500, calories_target=2343)
        assert _rule_extreme_deficit(s) is None

    def test_silent_if_nothing_eaten(self):
        s = _snap(calories_eaten=0, calories_target=2343)
        assert _rule_extreme_deficit(s) is None


class TestAggressiveDeficitTraining:
    def test_fires_on_training_day(self):
        s = _snap(
            is_training_day=True, session_type="push",
            calories_eaten=1500, calories_target=2343,
        )
        a = _rule_aggressive_deficit_training(s)
        assert a is not None
        assert a.severity == "warning"
        assert "push" in a.detail

    def test_silent_on_rest_day(self):
        s = _snap(
            is_training_day=False,
            calories_eaten=1500, calories_target=2343,
        )
        assert _rule_aggressive_deficit_training(s) is None

    def test_silent_if_deficit_under_700(self):
        s = _snap(
            is_training_day=True, session_type="push",
            calories_eaten=1800, calories_target=2343,
        )
        assert _rule_aggressive_deficit_training(s) is None


class TestAggressiveDeficitRest:
    def test_info_if_sleep_ok(self):
        s = _snap(
            is_training_day=False, sleep_score=70,
            calories_eaten=1500, calories_target=2343,
        )
        a = _rule_aggressive_deficit_rest(s)
        assert a is not None
        assert a.severity == "info"
        assert "acceptable" in a.headline.lower()

    def test_caution_if_sleep_poor(self):
        s = _snap(
            is_training_day=False, sleep_score=45,
            calories_eaten=1500, calories_target=2343,
        )
        a = _rule_aggressive_deficit_rest(s)
        assert a is not None
        assert a.severity == "caution"

    def test_info_if_no_sleep_data(self):
        s = _snap(
            is_training_day=False, sleep_score=None,
            calories_eaten=1500, calories_target=2343,
        )
        a = _rule_aggressive_deficit_rest(s)
        assert a is not None
        assert a.severity == "info"


class TestSurplusInCut:
    def test_info_on_first_overshoot(self):
        s = _snap(
            calories_eaten=2800, calories_target=2343,
            days_over_target_this_week=1,
        )
        a = _rule_surplus_in_cut(s)
        assert a is not None
        assert a.severity == "info"

    def test_caution_on_pattern(self):
        s = _snap(
            calories_eaten=2800, calories_target=2343,
            days_over_target_this_week=3,
        )
        a = _rule_surplus_in_cut(s)
        assert a is not None
        assert a.severity == "caution"
        assert "pattern" in a.headline.lower()

    def test_silent_within_15pct(self):
        s = _snap(calories_eaten=2500, calories_target=2343)
        assert _rule_surplus_in_cut(s) is None


class TestDeficitSweetSpot:
    def test_fires_evening_on_target(self):
        s = _snap(
            calories_eaten=2300, calories_target=2343,
            hour_of_day=20,
        )
        a = _rule_moderate_deficit_sweet_spot(s)
        assert a is not None
        assert a.severity == "positive"

    def test_silent_before_evening(self):
        s = _snap(
            calories_eaten=2300, calories_target=2343,
            hour_of_day=14,
        )
        assert _rule_moderate_deficit_sweet_spot(s) is None

    def test_silent_if_way_off(self):
        s = _snap(
            calories_eaten=1500, calories_target=2343,
            hour_of_day=20,
        )
        assert _rule_moderate_deficit_sweet_spot(s) is None


# ── Protein rules ────────────────────────────────────────────────────


class TestProteinCritical:
    def test_fires_below_60pct_after_4pm(self):
        s = _snap(protein_eaten=80, protein_target=150, hour_of_day=17)
        a = _rule_protein_critical(s)
        assert a is not None
        assert a.severity == "warning"

    def test_silent_before_4pm(self):
        s = _snap(protein_eaten=80, protein_target=150, hour_of_day=14)
        assert _rule_protein_critical(s) is None

    def test_silent_above_60pct(self):
        s = _snap(protein_eaten=100, protein_target=150, hour_of_day=17)
        assert _rule_protein_critical(s) is None


class TestProteinUndershoot:
    def test_fires_60_to_80pct_after_6pm(self):
        s = _snap(protein_eaten=110, protein_target=150, hour_of_day=19)
        a = _rule_protein_undershoot(s)
        assert a is not None
        assert a.severity == "caution"

    def test_silent_above_80pct(self):
        s = _snap(protein_eaten=125, protein_target=150, hour_of_day=19)
        assert _rule_protein_undershoot(s) is None


class TestProteinNailingIt:
    def test_fires_above_95pct_after_6pm(self):
        s = _snap(protein_eaten=148, protein_target=150, hour_of_day=20)
        a = _rule_protein_nailing_it(s)
        assert a is not None
        assert a.severity == "positive"

    def test_silent_below_95pct(self):
        s = _snap(protein_eaten=130, protein_target=150, hour_of_day=20)
        assert _rule_protein_nailing_it(s) is None


# ── Hydration rule ───────────────────────────────────────────────────


class TestDehydrated:
    def test_fires_below_60pct_after_3pm(self):
        s = _snap(water_ml=1800, water_target=3500, hour_of_day=16)
        a = _rule_dehydrated(s)
        assert a is not None
        assert a.severity == "caution"

    def test_silent_above_60pct(self):
        s = _snap(water_ml=2200, water_target=3500, hour_of_day=16)
        assert _rule_dehydrated(s) is None

    def test_silent_before_3pm(self):
        s = _snap(water_ml=500, water_target=3500, hour_of_day=10)
        assert _rule_dehydrated(s) is None


# ── Weight trend rules ───────────────────────────────────────────────


class TestRateTooFast:
    def test_fires_above_1pct(self):
        s = _snap(slope_kg_per_week=-1.1, current_weight_kg=88.0)
        a = _rule_rate_too_fast(s)
        assert a is not None
        assert a.severity == "warning"

    def test_silent_at_safe_rate(self):
        s = _snap(slope_kg_per_week=-0.6, current_weight_kg=88.0)
        assert _rule_rate_too_fast(s) is None


class TestRatePerfect:
    def test_fires_in_sweet_spot(self):
        s = _snap(slope_kg_per_week=-0.7, current_weight_kg=88.0)
        a = _rule_rate_perfect(s)
        assert a is not None
        assert a.severity == "positive"

    def test_silent_if_gaining(self):
        s = _snap(slope_kg_per_week=0.3, current_weight_kg=88.0)
        assert _rule_rate_perfect(s) is None

    def test_silent_if_too_fast(self):
        s = _snap(slope_kg_per_week=-1.5, current_weight_kg=88.0)
        assert _rule_rate_perfect(s) is None


class TestWeightStalled:
    def test_fires_when_stalled(self):
        s = _snap(weight_stalled=True)
        a = _rule_weight_stalled(s)
        assert a is not None
        assert a.severity == "caution"

    def test_silent_when_moving(self):
        s = _snap(weight_stalled=False)
        assert _rule_weight_stalled(s) is None


class TestDietBreak:
    def test_fires_stalled_plus_poor_adherence(self):
        s = _snap(weight_stalled=True, avg_protein_pct_this_week=60.0)
        a = _rule_diet_break(s)
        assert a is not None
        assert a.severity == "caution"
        assert "diet break" in a.headline.lower()

    def test_silent_if_adherence_ok(self):
        s = _snap(weight_stalled=True, avg_protein_pct_this_week=90.0)
        assert _rule_diet_break(s) is None


# ── Recovery rules ───────────────────────────────────────────────────


class TestPoorSleepTraining:
    def test_fires_low_sleep_training(self):
        s = _snap(sleep_score=45, is_training_day=True, session_type="legs")
        a = _rule_poor_sleep_training(s)
        assert a is not None
        assert a.severity == "caution"
        assert "legs" in a.action

    def test_silent_good_sleep(self):
        s = _snap(sleep_score=80, is_training_day=True)
        assert _rule_poor_sleep_training(s) is None

    def test_silent_rest_day(self):
        s = _snap(sleep_score=40, is_training_day=False)
        assert _rule_poor_sleep_training(s) is None


class TestRestingHrRising:
    def test_fires_rising_3_bpm(self):
        s = _snap(resting_hr_5d=[64, 63, 62, 61, 60])
        a = _rule_resting_hr_rising(s)
        assert a is not None
        assert a.severity == "caution"

    def test_silent_stable(self):
        s = _snap(resting_hr_5d=[60, 60, 60, 60, 60])
        assert _rule_resting_hr_rising(s) is None


class TestHrvLow:
    def test_fires_low_status(self):
        s = _snap(hrv_status="LOW")
        a = _rule_hrv_low(s)
        assert a is not None
        assert a.severity == "caution"

    def test_silent_balanced(self):
        s = _snap(hrv_status="BALANCED")
        assert _rule_hrv_low(s) is None

    def test_silent_no_data(self):
        s = _snap(hrv_status=None)
        assert _rule_hrv_low(s) is None


class TestHighStress:
    def test_fires_high_stress_training(self):
        s = _snap(stress_avg=55, is_training_day=True)
        a = _rule_high_stress(s)
        assert a is not None
        assert a.severity == "caution"

    def test_silent_low_stress(self):
        s = _snap(stress_avg=30, is_training_day=True)
        assert _rule_high_stress(s) is None

    def test_silent_rest_day(self):
        s = _snap(stress_avg=60, is_training_day=False)
        assert _rule_high_stress(s) is None


class TestGoodSleep:
    def test_fires_high_score(self):
        s = _snap(sleep_score=85, sleep_hours=8.0)
        a = _rule_good_sleep(s)
        assert a is not None
        assert a.severity == "positive"

    def test_silent_mediocre(self):
        s = _snap(sleep_score=65)
        assert _rule_good_sleep(s) is None


# ── Training rules ───────────────────────────────────────────────────


class TestRpeCreep:
    def test_fires_rising_rpe(self):
        s = _snap(recent_rpe=[9, 9, 8, 6, 6, 6])
        a = _rule_rpe_creep(s)
        assert a is not None
        assert a.severity == "caution"

    def test_silent_stable(self):
        s = _snap(recent_rpe=[7, 7, 6, 7, 6, 7])
        assert _rule_rpe_creep(s) is None


class TestMissedSessions:
    def test_fires_behind_on_friday(self):
        s = _snap(day_of_week=4, strength_sessions_week=1, strength_target=4)
        a = _rule_missed_sessions(s)
        assert a is not None

    def test_silent_early_in_week(self):
        s = _snap(day_of_week=1, strength_sessions_week=1, strength_target=4)
        assert _rule_missed_sessions(s) is None

    def test_silent_if_on_track(self):
        s = _snap(day_of_week=4, strength_sessions_week=3, strength_target=4)
        assert _rule_missed_sessions(s) is None


class TestMobilityDropped:
    def test_fires_broken_streak(self):
        s = _snap(mobility_streak=0, mobility_done_today=False)
        a = _rule_mobility_dropped(s)
        assert a is not None
        assert a.severity == "caution"

    def test_silent_if_done_today(self):
        s = _snap(mobility_streak=0, mobility_done_today=True)
        assert _rule_mobility_dropped(s) is None

    def test_silent_if_streak_active(self):
        s = _snap(mobility_streak=3, mobility_done_today=False)
        assert _rule_mobility_consistent(s) is None  # streak < 7
        assert _rule_mobility_dropped(s) is None


class TestMobilityConsistent:
    def test_fires_week_streak(self):
        s = _snap(mobility_streak=7)
        a = _rule_mobility_consistent(s)
        assert a is not None
        assert a.severity == "positive"
        assert "7" in a.headline

    def test_silent_short_streak(self):
        s = _snap(mobility_streak=4)
        assert _rule_mobility_consistent(s) is None


# ── Composite rules ──────────────────────────────────────────────────


class TestEverythingOnPoint:
    def test_fires_all_green_evening(self):
        s = _snap(
            calories_eaten=2300, calories_target=2343,
            protein_eaten=145, protein_target=150,
            steps_today=14000, steps_target=15000,
            hour_of_day=21,
        )
        a = _rule_everything_on_point(s)
        assert a is not None
        assert a.severity == "positive"
        assert "nailing" in a.headline.lower()

    def test_silent_if_protein_off(self):
        s = _snap(
            calories_eaten=2300, calories_target=2343,
            protein_eaten=100, protein_target=150,
            steps_today=14000, steps_target=15000,
            hour_of_day=21,
        )
        assert _rule_everything_on_point(s) is None

    def test_silent_before_8pm(self):
        s = _snap(
            calories_eaten=2300, calories_target=2343,
            protein_eaten=145, protein_target=150,
            steps_today=14000, steps_target=15000,
            hour_of_day=15,
        )
        assert _rule_everything_on_point(s) is None


# ── Evaluator ────────────────────────────────────────────────────────


class TestEvaluateRules:
    def test_returns_sorted_by_severity(self):
        s = _snap(
            calories_eaten=1200, calories_target=2343,  # extreme deficit
            sleep_score=85, sleep_hours=8.0,             # good sleep
            mobility_streak=10,                          # consistent
        )
        advice = evaluate_rules(s)
        assert len(advice) > 0
        severities = [a.severity for a in advice]
        order = {"warning": 0, "caution": 1, "info": 2, "positive": 3}
        for i in range(len(severities) - 1):
            assert order[severities[i]] <= order[severities[i + 1]]

    def test_warning_comes_first(self):
        s = _snap(
            calories_eaten=1200, calories_target=2343,
            sleep_score=85, sleep_hours=8.0,
        )
        advice = evaluate_rules(s)
        if advice:
            assert advice[0].severity == "warning"

    def test_empty_programme_returns_few_items(self):
        s = Snapshot()
        advice = evaluate_rules(s)
        # Most rules should skip with zero data
        assert isinstance(advice, list)

    def test_multiple_categories_can_fire(self):
        s = _snap(
            calories_eaten=1500, calories_target=2343,
            is_training_day=True, session_type="push",
            protein_eaten=70, protein_target=150,
            hour_of_day=17,
            sleep_score=40,
            mobility_streak=0, mobility_done_today=False,
        )
        advice = evaluate_rules(s)
        categories = {a.category for a in advice}
        assert len(categories) >= 2

    def test_advice_structure(self):
        s = _snap(
            weight_stalled=True,
            avg_protein_pct_this_week=60.0,
        )
        advice = evaluate_rules(s)
        for a in advice:
            assert isinstance(a.severity, str)
            assert a.severity in ("positive", "info", "caution", "warning")
            assert len(a.headline) > 0
            assert len(a.detail) > 0
            assert len(a.action) > 0
            assert len(a.category) > 0
