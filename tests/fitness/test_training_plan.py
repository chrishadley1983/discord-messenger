"""Unit tests for the adaptive training plan engine (pure functions, no I/O)."""
from datetime import date

import pytest

from domains.fitness import training_plan as tp


def _hist(*sessions):
    """sessions: list of (date, [(reps, weight, rir, failed), ...]) newest first."""
    out = []
    for d, sets in sessions:
        out.append({
            "date": d, "session_type": "upper", "session_id": d,
            "sets": [{"set_no": i + 1, "reps": r, "weight_kg": w, "rir": rir, "failed": f, "target_reps": 10}
                     for i, (r, w, rir, f) in enumerate(sets)],
        })
    return out


PE = {"slug": "lat-pulldown", "sets": 3, "rep_range": [8, 12], "target_reps": 10}


class TestRecommendExercise:
    def test_no_history_is_start(self):
        rec = tp.recommend_exercise(PE, [], None)
        assert rec["action"] == "start" and rec["weight_kg"] is None

    def test_reps_in_reserve_goes_up_one_plate(self):
        # Chris, Sat 5 Sep: lat pulldown 33 kg 3x10, a few in reserve -> go up one plate
        h = _hist(("2026-09-05", [(10, 33, 3, False)] * 3))
        rec = tp.recommend_exercise(PE, h, None)
        assert rec["action"] == "increase"
        assert rec["weight_kg"] is None            # step unknown -> "one plate"
        assert "one plate" in rec["reason"]
        rec2 = tp.recommend_exercise(PE, h, 2.5)
        assert rec2["weight_kg"] == 35.5

    def test_failed_rep_holds(self):
        # chest press 25 kg, failed rep 7 of set 3 -> hold at 25, aim clean 3x10
        h = _hist(("2026-09-05", [(10, 25, 1, False), (10, 25, 0, False), (6, 25, 0, True)]))
        rec = tp.recommend_exercise(PE, h, 2.5)
        assert rec["action"] == "hold" and rec["weight_kg"] == 25
        assert "clean" in rec["reason"]

    def test_failed_twice_running_deloads(self):
        h = _hist(
            ("2026-09-12", [(10, 25, 0, False), (8, 25, 0, True), (6, 25, 0, True)]),
            ("2026-09-05", [(10, 25, 1, False), (10, 25, 0, False), (6, 25, 0, True)]),
        )
        rec = tp.recommend_exercise(PE, h, 2.5)
        assert rec["action"] == "deload"
        assert rec["weight_kg"] == 22.5             # 25 * 0.9 = 22.5, rounded to the step

    def test_hit_target_but_grinding_holds(self):
        h = _hist(("2026-09-05", [(10, 30, 1, False)] * 3))
        rec = tp.recommend_exercise(PE, h, 2.5)
        assert rec["action"] == "hold" and rec["weight_kg"] == 30

    def test_top_of_range_increases_even_without_rir(self):
        h = _hist(("2026-09-05", [(12, 30, None, False)] * 3))
        rec = tp.recommend_exercise(PE, h, 5)
        assert rec["action"] == "increase" and rec["weight_kg"] == 35

    def test_unreported_rir_at_target_is_treated_as_easy(self):
        h = _hist(("2026-09-05", [(10, 30, None, False)] * 3))
        assert tp.recommend_exercise(PE, h, None)["action"] == "increase"

    def test_short_reps_without_fail_flag_holds(self):
        h = _hist(("2026-09-05", [(10, 30, 0, False), (9, 30, 0, False), (8, 30, 0, False)]))
        rec = tp.recommend_exercise(PE, h, 2.5)
        assert rec["action"] == "hold" and "chase" in rec["reason"]


class TestRotation:
    def test_first_session_is_top_of_rotation(self):
        assert tp.next_session_type(tp.default_plan(), []) == "upper"

    def test_rotation_advances_after_last_strength(self):
        plan = tp.default_plan()
        assert tp.next_session_type(plan, [{"session_type": "upper", "session_date": "2026-09-05"}]) == "lower"
        assert tp.next_session_type(plan, [{"session_type": "full_body", "session_date": "2026-09-05"}]) == "upper"

    def test_non_strength_ignored(self):
        plan = tp.default_plan()
        recent = [{"session_type": "mobility", "session_date": "2026-09-06"},
                  {"session_type": "lower", "session_date": "2026-09-05"}]
        assert tp.next_session_type(plan, recent) == "full_body"

    def test_order_variant_alternates(self):
        plan = tp.default_plan()
        assert tp.order_variant(plan, "upper", 0) == "A"
        assert tp.order_variant(plan, "upper", 1) == "B"
        assert tp.order_variant(plan, "lower", 0) is None

    def test_rest_gap(self):
        plan = tp.default_plan()
        ok, gap = tp.rest_gap_ok(plan, [{"session_type": "upper", "session_date": "2026-09-05"}], date(2026, 9, 6))
        assert ok is False and gap == 1
        ok, gap = tp.rest_gap_ok(plan, [{"session_type": "upper", "session_date": "2026-09-05"}], date(2026, 9, 7))
        assert ok is True and gap == 2


class TestComputeNextSession:
    def test_upper_b_order_and_targets(self):
        plan = tp.default_plan()
        history = {
            "lat-pulldown": _hist(("2026-09-05", [(10, 33, 3, False)] * 3)),
            "chest-press": _hist(("2026-09-05", [(10, 25, 1, False), (10, 25, 0, False), (6, 25, 0, True)])),
            "seated-row": _hist(("2026-09-05", [(10, 30, 3, False)] * 3)),
            "shoulder-press": _hist(("2026-09-05", [(10, 25, 1, False), (10, 25, 0, False), (9, 25, 0, True)])),
        }
        meta = {s: {"name": s, "load_step_kg": None} for s in history}
        rec = tp.compute_next_session(plan, "upper", history, meta, prior_count=1)
        assert rec["order_variant"] == "B"
        slugs = [e["slug"] for e in rec["exercises"]]
        assert slugs == ["shoulder-press", "seated-row", "chest-press", "lat-pulldown"]
        actions = {e["slug"]: e["action"] for e in rec["exercises"]}
        assert actions == {"lat-pulldown": "increase", "chest-press": "hold",
                           "seated-row": "increase", "shoulder-press": "hold"}

    def test_unknown_session_type(self):
        rec = tp.compute_next_session(tp.default_plan(), "arms", {}, {})
        assert rec["known"] is False


class TestStallsAndWins:
    def test_stalled_after_three_flat_sessions(self):
        h = {"chest-press": _hist(("2026-09-19", [(10, 25, 0, False)] * 3),
                                  ("2026-09-12", [(10, 25, 0, False)] * 3),
                                  ("2026-09-05", [(10, 25, 0, False)] * 3))}
        st = tp.stalled_exercises(h, 3)
        assert st == [{"slug": "chest-press", "weight_kg": 25, "sessions": 3}]
        assert tp.stalled_exercises(h, 4) == []

    def test_progression_win_this_week(self):
        h = {"lat-pulldown": _hist(("2026-09-09", [(10, 35.5, 2, False)] * 3),
                                   ("2026-09-05", [(10, 33, 3, False)] * 3))}
        wins = tp.progressions_since(h, date(2026, 9, 7))
        assert wins == [{"slug": "lat-pulldown", "from_kg": 33, "to_kg": 35.5}]
        assert tp.progressions_since(h, date(2026, 9, 10)) == []


class TestCardio:
    def _last(self, peak_seconds, hard_level=9, peak_level=9, pain=False):
        proto = tp.build_protocol(tp._STAIRMASTER_PYRAMID, hard_level=hard_level, peak_level=peak_level,
                                  peak_seconds=peak_seconds)
        return {"protocol": proto, "pain_flag": pain, "intensity": "hard", "modality": "stairmaster"}

    def test_first_session_is_template(self):
        nxt = tp.next_cardio_hard(tp.default_plan(), None)
        assert nxt["stage"] == "start" and nxt["peak_seconds"] == 90

    def test_session_one_reduced_peak_next_extends_peak_at_same_level(self):
        # Chris: peak reduced to 90 s at L9, other hard blocks L9 -> next: all L9, push peak toward 120
        nxt = tp.next_cardio_hard(tp.default_plan(), self._last(90))
        assert nxt["stage"] == "extend_peak"
        assert nxt["peak_seconds"] == 120 and nxt["hard_level"] == 9 and nxt["peak_level"] == 9
        assert [b["seconds"] for b in nxt["protocol"] if b["phase"] == "hard"] == [60, 90, 90, 60]

    def test_full_peak_then_extends_shortest_hard_blocks(self):
        nxt = tp.next_cardio_hard(tp.default_plan(), self._last(120))
        assert nxt["stage"] == "extend_hard"
        assert [b["seconds"] for b in nxt["protocol"] if b["phase"] == "hard"] == [90, 90, 90, 90]

    def test_then_raises_level(self):
        last = self._last(120)
        for b in last["protocol"]:
            if b["phase"] == "hard":
                b["seconds"] = 90
        nxt = tp.next_cardio_hard(tp.default_plan(), last)
        assert nxt["stage"] == "raise_level" and nxt["hard_level"] == 10 and nxt["peak_level"] == 10

    def test_pain_swaps_to_bike(self):
        nxt = tp.next_cardio_hard(tp.default_plan(), self._last(90, pain=True))
        assert nxt["stage"] == "pain_swap" and nxt["modality"] == "bike"

    def test_week4_note(self):
        nxt = tp.next_cardio_hard(tp.default_plan(), self._last(90), week_no=4)
        assert "25-30 min" in nxt.get("note", "")

    def test_week_summary(self):
        plan = tp.default_plan()
        s = tp.cardio_week_summary(plan, [{"intensity": "hard", "duration_min": 20}, {"intensity": "easy", "duration_min": 30}])
        assert s == {"easy_done": 1, "easy_target": 5, "hard_done": 1, "hard_target": 1, "minutes": 50}


class TestReconcile:
    def test_off_plan_exercise_is_added(self):
        plan = tp.default_plan()
        sets = [{"exercise_slug": "lat-pulldown", "reps": 10, "target_reps": 10},
                {"exercise_slug": "pec-fly", "reps": 12}, {"exercise_slug": "pec-fly", "reps": 12}]
        new, changes = tp.reconcile_plan(plan, "upper", sets)
        slugs = [e["slug"] for e in new["sessions"]["upper"]["exercises"]]
        assert "pec-fly" in slugs and any("pec-fly" in c for c in changes)
        added = next(e for e in new["sessions"]["upper"]["exercises"] if e["slug"] == "pec-fly")
        assert added == {"slug": "pec-fly", "sets": 2, "rep_range": [10, 14], "target_reps": 12}
        assert "pec-fly" in new["sessions"]["upper"]["order_variants"]["A"]
        assert plan["sessions"]["upper"]["exercises"][-1]["slug"] == "shoulder-press"  # original untouched

    def test_new_session_type_is_added_to_rotation(self):
        new, changes = tp.reconcile_plan(tp.default_plan(), "arms", [{"exercise_slug": "cable-curl", "reps": 12}])
        assert "arms" in new["sessions"] and new["rotation"][-1] == "arms"

    def test_proposed_session_confirmed_by_training_it(self):
        new, changes = tp.reconcile_plan(tp.default_plan(), "lower", [{"exercise_slug": "leg-press", "reps": 10}])
        assert new["sessions"]["lower"]["status"] == "active"
        assert any("confirmed" in c for c in changes)

    def test_no_change_when_on_plan(self):
        plan = tp.default_plan()
        new, changes = tp.reconcile_plan(plan, "upper", [{"exercise_slug": "lat-pulldown", "reps": 10}])
        assert changes == [] and new == plan

    def test_cardio_and_mobility_ignored(self):
        plan = tp.default_plan()
        assert tp.reconcile_plan(plan, "mobility", [{"exercise_slug": "cat-cow", "reps": 10}]) == (plan, [])


class TestPatch:
    def test_swap_exercise(self):
        plan = tp.default_plan()
        new, changes = tp.apply_plan_patch(plan, {"session_type": "upper", "remove": ["chest-press"],
                                                  "add": [{"slug": "incline-chest-press", "sets": 3, "rep_range": [8, 12], "target_reps": 10}]})
        slugs = [e["slug"] for e in new["sessions"]["upper"]["exercises"]]
        assert "chest-press" not in slugs and "incline-chest-press" in slugs
        assert "chest-press" not in new["sessions"]["upper"]["order_variants"]["B"]
        assert len(changes) == 2

    def test_weekly_and_constraints(self):
        new, changes = tp.apply_plan_patch(tp.default_plan(), {"weekly": {"cardio_easy": 4}, "constraints_add": ["No leg press until the hip settles"]})
        assert new["weekly"]["cardio_easy"] == 4 and new["constraints"][-1].startswith("No leg press")


class TestWeekView:
    def test_logged_session_sits_on_its_day_and_rest_is_projected(self):
        plan = tp.default_plan()
        ws = date(2026, 8, 31)  # Mon
        logged = [{"session_type": "upper", "session_date": "2026-09-05"}]  # Sat
        week = tp.build_week_sessions(plan, ws, logged, today=date(2026, 9, 5))
        assert len(week) == 7
        assert week[5].session_type == "upper" and week[5].label.endswith("✓")
        # Sunday is the day after a strength day -> rest gap keeps it as cardio
        assert week[6].session_type == "cardio"
        assert all(s.session_type in ("upper", "cardio") for s in week)

    def test_fresh_week_projects_three_sessions_with_gaps(self):
        plan = tp.default_plan()
        ws = date(2026, 9, 7)
        week = tp.build_week_sessions(plan, ws, [], today=ws)
        strength_days = [s.day_of_week for s in week if s.session_type in plan["rotation"]]
        assert strength_days == [0, 2, 4]
        assert [week[d].session_type for d in strength_days] == ["upper", "lower", "full_body"]
