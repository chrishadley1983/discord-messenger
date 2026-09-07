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

    def test_fewer_sets_than_prescribed_holds(self):
        # 2 clean sets of a 3-set prescription: volume incomplete, no load jump.
        h = _hist(("2026-09-06", [(10, 10, None, False)] * 2))
        rec = tp.recommend_exercise(PE, h, 2)
        assert rec["action"] == "hold" and rec["weight_kg"] == 10 and "2 of 3 sets" in rec["reason"]

    def test_short_reps_without_fail_flag_holds(self):
        h = _hist(("2026-09-05", [(10, 30, 0, False), (9, 30, 0, False), (8, 30, 0, False)]))
        rec = tp.recommend_exercise(PE, h, 2.5)
        assert rec["action"] == "hold" and "chase" in rec["reason"]




def _legacy_plan() -> dict:
    """The pre-7-Sep 3-day rotation (any days, rest day between, A/B order) — still a valid
    plan shape, used to exercise the generic rotation / order-variant / patch mechanics."""
    plan = tp.default_plan()
    plan.pop("schedule", None)
    plan.pop("schedule_from", None)
    plan["weekly"].update({"strength_sessions": 3, "cardio_easy": 5, "min_rest_days_between_strength": 1})
    plan["cardio"]["hard"]["modality_is_example"] = False
    plan["rotation"] = ["upper", "lower", "full_body"]
    plan["sessions"]["upper"] = {
        "label": "Upper body",
        "exercises": [tp._ex("lat-pulldown", 3, 8, 12, 10), tp._ex("chest-press", 3, 8, 12, 10),
                      tp._ex("seated-row", 3, 8, 12, 10), tp._ex("shoulder-press", 3, 8, 12, 10)],
        "order_variants": {"A": ["lat-pulldown", "chest-press", "seated-row", "shoulder-press"],
                           "B": ["shoulder-press", "seated-row", "chest-press", "lat-pulldown"]},
    }
    plan["sessions"]["lower"] = {"label": "Lower body", "status": "proposed",
                                 "exercises": [tp._ex("leg-press", 3, 8, 12, 10), tp._ex("seated-leg-curl", 3, 10, 15, 12)]}
    return plan


class TestDefaultPlanShape:
    def test_standing_week_from_7_sep(self):
        plan = tp.default_plan()
        assert plan["schedule_from"] == "2026-09-07"
        assert plan["schedule"] == ["upper_a", "lower_a", "cardio_hard", "upper_b", "cardio_easy", "full_body", "rest"]
        assert plan["rotation"] == ["upper_a", "lower_a", "upper_b", "full_body"]
        assert plan["weekly"] == {"strength_sessions": 4, "cardio_easy": 1, "cardio_hard": 1,
                                  "min_rest_days_between_strength": 0}
        assert tp.active_session_types(plan) == ["upper_a", "lower_a", "upper_b", "full_body"]

    def test_session_pages_and_durations(self):
        s = tp.default_plan()["sessions"]
        assert (s["upper_a"]["page"], s["upper_a"]["duration_min"]) == ("upper-a.html", 40)
        assert (s["lower_a"]["page"], s["lower_a"]["duration_min"]) == ("lower-a.html", 45)
        assert (s["upper_b"]["page"], s["upper_b"]["duration_min"]) == ("upper-b.html", 45)
        assert (s["full_body"]["page"], s["full_body"]["duration_min"]) == ("full-body.html", 40)
        assert s["upper"]["status"] == "retired" and s["upper_db"]["status"] == "retired"

    def test_upper_a_matches_the_page(self):
        exs = {e["slug"]: e for e in tp.default_plan()["sessions"]["upper_a"]["exercises"]}
        assert list(exs) == ["db-flat-bench-press", "db-incline-press", "shoulder-press", "db-flye", "db-incline-curl"]
        assert (exs["db-incline-press"]["sets"], exs["db-incline-press"]["target_reps"]) == (3, 8)
        assert exs["db-flye"]["sets"] == 2
        assert exs["db-incline-curl"]["sets"] == 4 and exs["db-incline-curl"]["unilateral"] is True

    def test_lower_a_and_upper_b_match_the_pages(self):
        s = tp.default_plan()["sessions"]
        assert [e["slug"] for e in s["lower_a"]["exercises"]] == [
            "leg-press", "db-romanian-deadlift", "seated-leg-curl", "db-split-squat", "hip-abduction", "leg-press-calf-raise"]
        assert [e["sets"] for e in s["lower_a"]["exercises"]] == [3, 3, 3, 2, 2, 3]
        assert [e["slug"] for e in s["upper_b"]["exercises"]] == [
            "lat-pulldown", "seated-row", "chest-press", "cable-face-pull", "lateral-raise", "triceps-pushdown"]
        assert [e["sets"] for e in s["upper_b"]["exercises"]] == [3, 3, 2, 2, 2, 2]
        assert next(e for e in s["upper_b"]["exercises"] if e["slug"] == "chest-press")["light"] is True

    def test_hard_cardio_modality_is_an_example(self):
        hard = tp.default_plan()["cardio"]["hard"]
        assert hard["modality"] == "stairmaster" and hard["modality_is_example"] is True
        assert "bike" in hard["modalities"] and hard["second_session_from_week"] == 6

    def test_plan_week_counts_from_schedule_start(self):
        plan = tp.default_plan()
        assert tp.plan_week(plan, date(2026, 9, 7)) == 1
        assert tp.plan_week(plan, date(2026, 9, 13)) == 1
        assert tp.plan_week(plan, date(2026, 9, 28)) == 4
        assert tp.plan_week(plan, date(2026, 10, 12)) == 6
        assert tp.plan_week(_legacy_plan(), date(2026, 9, 7)) is None


class TestRotation:
    def test_first_session_is_top_of_rotation(self):
        assert tp.next_session_type(tp.default_plan(), []) == "upper_a"
        assert tp.next_session_type(_legacy_plan(), []) == "upper"

    def test_rotation_advances_after_last_strength(self):
        plan = tp.default_plan()
        assert tp.next_session_type(plan, [{"session_type": "upper_a", "session_date": "2026-09-07"}]) == "lower_a"
        assert tp.next_session_type(plan, [{"session_type": "full_body", "session_date": "2026-09-12"}]) == "upper_a"

    def test_retired_session_restarts_rotation(self):
        # 6 Sep upper_db was the last lift before the standing week -> Monday is Upper A
        plan = tp.default_plan()
        assert tp.next_session_type(plan, [{"session_type": "upper_db", "session_date": "2026-09-06"}]) == "upper_a"

    def test_non_strength_ignored(self):
        plan = tp.default_plan()
        recent = [{"session_type": "mobility", "session_date": "2026-09-09"},
                  {"session_type": "lower_a", "session_date": "2026-09-08"}]
        assert tp.next_session_type(plan, recent) == "upper_b"

    def test_order_variant_alternates(self):
        plan = _legacy_plan()
        assert tp.order_variant(plan, "upper", 0) == "A"
        assert tp.order_variant(plan, "upper", 1) == "B"
        assert tp.order_variant(tp.default_plan(), "upper_a", 0) is None

    def test_rest_gap_legacy_needs_a_day_between(self):
        plan = _legacy_plan()
        ok, gap = tp.rest_gap_ok(plan, [{"session_type": "upper", "session_date": "2026-09-05"}], date(2026, 9, 6))
        assert ok is False and gap == 1
        ok, gap = tp.rest_gap_ok(plan, [{"session_type": "upper", "session_date": "2026-09-05"}], date(2026, 9, 7))
        assert ok is True and gap == 2

    def test_rest_gap_standing_week_allows_consecutive_days(self):
        # Mon Upper A -> Tue Lower A is by design
        plan = tp.default_plan()
        ok, gap = tp.rest_gap_ok(plan, [{"session_type": "upper_a", "session_date": "2026-09-07"}], date(2026, 9, 8))
        assert ok is True and gap == 1
        ok, gap = tp.rest_gap_ok(plan, [{"session_type": "upper_a", "session_date": "2026-09-07"}], date(2026, 9, 7))
        assert ok is False and gap == 0


class TestComputeNextSession:
    def test_upper_b_order_and_targets(self):
        plan = _legacy_plan()
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

    def test_upper_a_carries_page_duration_and_notes(self):
        plan = tp.default_plan()
        rec = tp.compute_next_session(plan, "upper_a", {}, {})
        assert rec["duration_min"] == 40 and rec["page"] == "upper-a.html" and rec["order_variant"] is None
        curl = next(e for e in rec["exercises"] if e["slug"] == "db-incline-curl")
        assert curl["unilateral"] is True and "left" in curl["note"]
        assert [e["slug"] for e in rec["exercises"]] == [
            "db-flat-bench-press", "db-incline-press", "shoulder-press", "db-flye", "db-incline-curl"]

    def test_lower_a_duration(self):
        assert tp.compute_next_session(tp.default_plan(), "lower_a", {}, {})["duration_min"] == 45

    def test_unknown_session_type(self):
        rec = tp.compute_next_session(tp.default_plan(), "arms", {}, {})
        assert rec["known"] is False


class TestStallsAndWins:
    def test_stalled(self):
        h = {"chest-press": _hist(("2026-09-19", [(10, 25, 0, False)] * 3),
                                  ("2026-09-12", [(10, 25, 0, False)] * 3),
                                  ("2026-09-05", [(10, 25, 0, False)] * 3))}
        st = tp.stalled_exercises(h, 3)
        assert st == [{"slug": "chest-press", "weight_kg": 25, "sessions": 3}]

    def test_progressions_since(self):
        h = {"lat-pulldown": _hist(("2026-09-09", [(10, 35.5, 2, False)] * 3),
                                   ("2026-09-05", [(10, 33, 3, False)] * 3))}
        wins = tp.progressions_since(h, date(2026, 9, 7))
        assert wins == [{"slug": "lat-pulldown", "from_kg": 33, "to_kg": 35.5}]


class TestCardio:
    def _last(self, peak_seconds, hard_level=9, peak_level=9, pain=False, modality="stairmaster"):
        proto = tp.build_protocol(tp._STAIRMASTER_PYRAMID, hard_level=hard_level, peak_level=peak_level,
                                  peak_seconds=peak_seconds)
        return {"protocol": proto, "pain_flag": pain, "intensity": "hard", "modality": modality}

    def test_first_session_is_template(self):
        nxt = tp.next_cardio_hard(tp.default_plan(), None, today=date(2026, 9, 7))
        assert nxt["stage"] == "start" and nxt["peak_seconds"] == 90
        assert nxt["modality"] == "stairmaster" and nxt["modality_is_example"] is True
        assert "interchangeable" in nxt["modality_note"]

    def test_session_one_reduced_peak_next_extends_peak_at_same_level(self):
        # Chris: peak reduced to 90 s at L9, other hard blocks L9 -> next: all L9, push peak toward 120
        nxt = tp.next_cardio_hard(tp.default_plan(), self._last(90), today=date(2026, 9, 7))
        assert nxt["stage"] == "extend_peak"
        assert nxt["peak_seconds"] == 120 and nxt["hard_level"] == 9 and nxt["peak_level"] == 9
        assert [b["seconds"] for b in nxt["protocol"] if b["phase"] == "hard"] == [60, 90, 90, 60]

    def test_full_peak_then_extends_shortest_hard_blocks(self):
        nxt = tp.next_cardio_hard(tp.default_plan(), self._last(120), today=date(2026, 9, 7))
        assert nxt["stage"] == "extend_hard"
        assert [b["seconds"] for b in nxt["protocol"] if b["phase"] == "hard"] == [90, 90, 90, 90]

    def test_then_raises_level(self):
        last = self._last(120)
        for b in last["protocol"]:
            if b["phase"] == "hard":
                b["seconds"] = 90
        nxt = tp.next_cardio_hard(tp.default_plan(), last, today=date(2026, 9, 7))
        assert nxt["stage"] == "raise_level" and nxt["hard_level"] == 10 and nxt["peak_level"] == 10

    def test_pain_swaps_to_bike(self):
        nxt = tp.next_cardio_hard(tp.default_plan(), self._last(90, pain=True), today=date(2026, 9, 7))
        assert nxt["stage"] == "pain_swap" and nxt["modality"] == "bike"

    def test_hard_modality_is_interchangeable_and_follows_the_last_session(self):
        # A hard bike pyramid last week -> the next prescription stays on the bike, same progression.
        nxt = tp.next_cardio_hard(tp.default_plan(), self._last(90, modality="bike"), today=date(2026, 9, 7))
        assert nxt["modality"] == "bike" and nxt["stage"] == "extend_peak"
        # Legacy plan (no modality_is_example) keeps the fixed modality
        nxt = tp.next_cardio_hard(_legacy_plan(), self._last(90, modality="bike"))
        assert nxt["modality"] == "stairmaster"

    def test_extension_note_uses_plan_week_not_programme_week(self):
        # Programme week 4 (programme started 17 Aug) is only plan week 1 -> no extension note yet.
        nxt = tp.next_cardio_hard(tp.default_plan(), self._last(90), week_no=4, today=date(2026, 9, 9))
        assert "note" not in nxt
        # Plan week 4 = w/c 28 Sep -> extend toward 25-30 min
        nxt = tp.next_cardio_hard(tp.default_plan(), self._last(90), week_no=7, today=date(2026, 9, 30))
        assert "25-30 min" in nxt.get("note", "")

    def test_week4_note_legacy_uses_programme_week(self):
        nxt = tp.next_cardio_hard(_legacy_plan(), self._last(90), week_no=4)
        assert "25-30 min" in nxt.get("note", "")

    def test_week_summary(self):
        plan = tp.default_plan()
        s = tp.cardio_week_summary(plan, [{"intensity": "hard", "duration_min": 20}, {"intensity": "easy", "duration_min": 30}])
        assert s == {"easy_done": 1, "easy_target": 1, "hard_done": 1, "hard_target": 1, "minutes": 50}
        s = tp.cardio_week_summary(_legacy_plan(), [{"intensity": "easy", "duration_min": 30}])
        assert s["easy_target"] == 5


class TestReconcile:
    def test_off_plan_exercise_is_added(self):
        plan = _legacy_plan()
        sets = [{"exercise_slug": "lat-pulldown", "reps": 10, "target_reps": 10},
                {"exercise_slug": "pec-fly", "reps": 12}, {"exercise_slug": "pec-fly", "reps": 12}]
        new, changes = tp.reconcile_plan(plan, "upper", sets)
        slugs = [e["slug"] for e in new["sessions"]["upper"]["exercises"]]
        assert "pec-fly" in slugs and any("pec-fly" in c for c in changes)
        added = next(e for e in new["sessions"]["upper"]["exercises"] if e["slug"] == "pec-fly")
        assert added == {"slug": "pec-fly", "sets": 2, "rep_range": [10, 14], "target_reps": 12}
        assert "pec-fly" in new["sessions"]["upper"]["order_variants"]["A"]
        assert plan["sessions"]["upper"]["exercises"][-1]["slug"] == "shoulder-press"  # original untouched

    def test_off_plan_exercise_added_to_upper_a(self):
        new, changes = tp.reconcile_plan(tp.default_plan(), "upper_a", [{"exercise_slug": "cable-curl", "reps": 12}])
        assert [e["slug"] for e in new["sessions"]["upper_a"]["exercises"]][-1] == "cable-curl"

    def test_new_session_type_is_added_to_rotation(self):
        new, changes = tp.reconcile_plan(tp.default_plan(), "arms", [{"exercise_slug": "cable-curl", "reps": 12}])
        assert "arms" in new["sessions"] and new["rotation"][-1] == "arms"

    def test_proposed_session_confirmed_by_training_it(self):
        new, changes = tp.reconcile_plan(tp.default_plan(), "full_body", [{"exercise_slug": "goblet-squat", "reps": 10}])
        assert new["sessions"]["full_body"]["status"] == "active"
        assert any("confirmed" in c for c in changes)

    def test_no_change_when_on_plan(self):
        plan = tp.default_plan()
        new, changes = tp.reconcile_plan(plan, "upper_b", [{"exercise_slug": "lat-pulldown", "reps": 10}])
        assert changes == [] and new == plan

    def test_cardio_and_mobility_ignored(self):
        plan = tp.default_plan()
        assert tp.reconcile_plan(plan, "mobility", [{"exercise_slug": "cat-cow", "reps": 10}]) == (plan, [])


class TestPatch:
    def test_swap_exercise(self):
        plan = _legacy_plan()
        new, changes = tp.apply_plan_patch(plan, {"session_type": "upper", "remove": ["chest-press"],
                                                  "add": [{"slug": "incline-chest-press", "sets": 3, "rep_range": [8, 12], "target_reps": 10}]})
        slugs = [e["slug"] for e in new["sessions"]["upper"]["exercises"]]
        assert "chest-press" not in slugs and "incline-chest-press" in slugs
        assert "chest-press" not in new["sessions"]["upper"]["order_variants"]["B"]
        assert len(changes) == 2

    def test_swap_on_upper_b(self):
        new, changes = tp.apply_plan_patch(tp.default_plan(), {"session_type": "upper_b", "remove": ["triceps-pushdown"],
                                                              "add": [{"slug": "cable-curl", "sets": 2, "rep_range": [10, 15], "target_reps": 12}]})
        slugs = [e["slug"] for e in new["sessions"]["upper_b"]["exercises"]]
        assert "triceps-pushdown" not in slugs and slugs[-1] == "cable-curl"

    def test_weekly_and_constraints(self):
        new, changes = tp.apply_plan_patch(tp.default_plan(), {"weekly": {"cardio_easy": 4}, "constraints_add": ["No leg press until the hip settles"]})
        assert new["weekly"]["cardio_easy"] == 4 and new["constraints"][-1].startswith("No leg press")


class TestWeekView:
    def test_standing_week_projects_fixed_days(self):
        plan = tp.default_plan()
        ws = date(2026, 9, 7)
        week = tp.build_week_sessions(plan, ws, [], today=ws)
        assert [s.session_type for s in week] == ["upper_a", "lower_a", "cardio", "upper_b", "cardio", "full_body", "rest"]
        assert week[0].duration_min == 40 and week[1].duration_min == 45 and week[3].duration_min == 45
        assert "stairmaster pyramid or equivalent" in week[2].label
        assert week[4].label.startswith("Easy cardio 30–40 min") and week[6].is_rest

    def test_standing_week_logged_sessions_sit_on_their_days(self):
        plan = tp.default_plan()
        ws = date(2026, 9, 7)
        logged = [{"session_type": "upper_a", "session_date": "2026-09-07"}]
        week = tp.build_week_sessions(plan, ws, logged, today=date(2026, 9, 8))
        assert week[0].session_type == "upper_a" and week[0].label.endswith("✓")
        assert week[1].session_type == "lower_a" and not week[1].label.endswith("✓")

    def test_standing_week_missed_day_is_marked_not_moved(self):
        # Wednesday with Monday and Tuesday unlogged: they show as missed, the week carries on.
        plan = tp.default_plan()
        ws = date(2026, 9, 7)
        week = tp.build_week_sessions(plan, ws, [], today=date(2026, 9, 9))
        assert week[0].is_rest and "missed" in week[0].label and week[1].is_rest
        assert week[3].session_type == "upper_b" and week[5].session_type == "full_body"

    def test_off_schedule_day_logged_still_shows(self):
        # A lift logged on the Wednesday replaces the hard-cardio slot for that day.
        plan = tp.default_plan()
        ws = date(2026, 9, 7)
        logged = [{"session_type": "lower_a", "session_date": "2026-09-09"}]
        week = tp.build_week_sessions(plan, ws, logged, today=date(2026, 9, 9))
        assert week[2].session_type == "lower_a" and week[2].label.endswith("✓")

    # ── legacy rotation behaviour (no fixed schedule) ──
    def test_logged_session_sits_on_its_day_and_rest_is_projected(self):
        plan = _legacy_plan()
        ws = date(2026, 8, 31)  # Mon
        logged = [{"session_type": "upper", "session_date": "2026-09-05"}]  # Sat
        week = tp.build_week_sessions(plan, ws, logged, today=date(2026, 9, 5))
        assert len(week) == 7
        assert week[5].session_type == "upper" and week[5].label.endswith("✓")
        # Sunday is the day after a strength day -> rest gap keeps it as cardio
        assert week[6].session_type == "cardio"
        assert all(s.session_type in ("upper", "cardio") for s in week)

    def test_fresh_week_projects_three_sessions_with_gaps(self):
        plan = _legacy_plan()
        ws = date(2026, 9, 7)
        week = tp.build_week_sessions(plan, ws, [], today=ws)
        strength_days = [s.day_of_week for s in week if s.session_type in plan["rotation"]]
        assert strength_days == [0, 2, 4]
        assert [week[d].session_type for d in strength_days] == ["upper", "lower", "full_body"]

    def test_fresh_week_continues_rotation_and_rest_gap_from_last_week(self):
        plan = _legacy_plan()
        ws = date(2026, 9, 7)  # Mon after a Saturday upper session
        recent = [{"session_type": "upper", "session_date": "2026-09-05"}]
        week = tp.build_week_sessions(plan, ws, [], today=ws, recent_sessions=recent)
        strength = [(s.day_of_week, s.session_type) for s in week if s.session_type in plan["rotation"]]
        assert strength == [(0, "lower"), (2, "full_body"), (4, "upper")]
        # Sunday-trained case: Monday must be a rest/cardio day
        recent = [{"session_type": "upper", "session_date": "2026-09-06"}]
        week = tp.build_week_sessions(plan, ws, [], today=ws, recent_sessions=recent)
        strength = [(s.day_of_week, s.session_type) for s in week if s.session_type in plan["rotation"]]
        assert strength == [(1, "lower"), (3, "full_body"), (5, "upper")]


class TestReviewFixes:
    """7 Sep 2026 pre-merge review: M1 schedule-aware next, M2 Fitbod mapping, m1-m4/m8 guards."""

    def test_next_session_follows_the_schedule_not_the_rotation(self):
        plan = tp.default_plan()
        mon = [{"session_type": "upper_a", "session_date": "2026-09-07"}]
        # Thursday after Tuesday was skipped -> Upper B (Lower A is "missed", not carried forward)
        assert tp.next_session_type(plan, mon, date(2026, 9, 10)) == "upper_b"
        # Tuesday morning, Monday logged -> Lower A
        assert tp.next_session_type(plan, mon, date(2026, 9, 8)) == "lower_a"
        # Monday not yet logged -> Upper A; Monday already logged -> Lower A (tomorrow)
        assert tp.next_session_type(plan, [], date(2026, 9, 7)) == "upper_a"
        assert tp.next_session_type(plan, mon, date(2026, 9, 7)) == "lower_a"
        # Saturday evening after full body logged -> wraps to Monday's Upper A
        sat = [{"session_type": "full_body", "session_date": "2026-09-12"}]
        assert tp.next_session_type(plan, sat, date(2026, 9, 12)) == "upper_a"
        # Sunday / Wednesday (non-lift days) -> the next scheduled lift
        assert tp.next_session_type(plan, [], date(2026, 9, 13)) == "upper_a"
        assert tp.next_session_type(plan, [], date(2026, 9, 9)) == "upper_b"
        # without today the legacy rotation still applies
        assert tp.next_session_type(plan, mon) == "lower_a"

    def test_resolve_session_type_maps_fitbod_regions_to_active_types(self):
        plan = tp.default_plan()
        assert tp.resolve_session_type(plan, "lower", date(2026, 9, 8)) == "lower_a"      # Tue leg day
        assert tp.resolve_session_type(plan, "upper", date(2026, 9, 10)) == "upper_b"     # Thu pull day
        assert tp.resolve_session_type(plan, "upper", date(2026, 9, 9)) == "upper_a"      # off-schedule -> first upper
        assert tp.resolve_session_type(plan, "lower", date(2026, 9, 12)) == "lower_a"     # Sat is full body, region differs
        assert tp.resolve_session_type(plan, "full_body", date(2026, 9, 8)) == "full_body"
        assert tp.resolve_session_type(plan, "upper_a", None) == "upper_a"
        assert tp.resolve_session_type(_legacy_plan(), "upper", date(2026, 9, 8)) == "upper"
        assert tp.resolve_session_type(plan, "arms", None) == "arms"                       # unknown region -> as is
        # and reconcile never sees a retired / unknown type from an import
        new, changes = tp.reconcile_plan(plan, tp.resolve_session_type(plan, "lower", date(2026, 9, 8)),
                                         [{"exercise_slug": "leg-press", "reps": 10}])
        assert new["rotation"] == plan["rotation"] and changes == []

    def test_bad_schedule_from_is_ignored_not_raised(self):
        plan = tp.default_plan()
        plan["schedule_from"] = "7 Sep 2026"
        assert tp.plan_week(plan, date(2026, 9, 7)) is None
        nxt = tp.next_cardio_hard(plan, None, week_no=4, today=date(2026, 9, 7))
        assert nxt["stage"] == "start"

    def test_malformed_schedule_falls_back_to_rotation(self):
        plan = tp.default_plan()
        for bad in (["upper_a", None, "cardio_hard", "upper_b", "cardio_easy", "full_body", "rest"],
                    ["upper_a", "lower", "cardio_hard", "upper_b", "cardio_easy", "full_body", "rest"],
                    ["upper", "lower_a", "cardio_hard", "upper_b", "cardio_easy", "full_body", "rest"],   # retired
                    ["upper_a", "lower_a", "cardio_hard"], "upper_a", None):
            plan["schedule"] = bad
            assert tp.schedule_for(plan) is None, bad
            week = tp.build_week_sessions(plan, date(2026, 9, 7), [], today=date(2026, 9, 7))
            assert len(week) == 7 and not any("missed" in s.label for s in week)

    def test_hard_modality_outside_the_list_reverts_to_the_example(self):
        proto = tp.build_protocol(tp._STAIRMASTER_PYRAMID, peak_seconds=90)
        last = {"protocol": proto, "modality": "walk", "intensity": "hard"}
        nxt = tp.next_cardio_hard(tp.default_plan(), last, today=date(2026, 9, 7))
        assert nxt["modality"] == "stairmaster" and nxt["stage"] == "extend_peak"
        last["modality"] = "rower"
        assert tp.next_cardio_hard(tp.default_plan(), last, today=date(2026, 9, 7))["modality"] == "rower"

    def test_patching_a_retired_session_does_not_resurrect_it(self):
        plan = tp.default_plan()
        new, changes = tp.apply_plan_patch(plan, {"session_type": "upper", "add": [{"slug": "pec-fly", "sets": 3}]})
        assert new["rotation"] == plan["rotation"] and "upper" not in new["rotation"]
        assert any("pec-fly" in c for c in changes)
        assert tp.active_session_types(new) == ["upper_a", "lower_a", "upper_b", "full_body"]

    def test_short_duration_range_does_not_crash_week_view(self):
        plan = tp.default_plan()
        plan["cardio"]["easy"]["duration_range_min"] = [30]
        plan["cardio"]["easy"]["rpe"] = None
        week = tp.build_week_sessions(plan, date(2026, 9, 7), [], today=date(2026, 9, 7))
        assert week[4].label.startswith("Easy cardio 30–30 min · RPE 3–4")

    def test_next_cardio_hard_without_today_uses_programme_week(self):
        proto = tp.build_protocol(tp._STAIRMASTER_PYRAMID, peak_seconds=90)
        nxt = tp.next_cardio_hard(tp.default_plan(), {"protocol": proto, "modality": "stairmaster"}, week_no=4)
        assert "25-30 min" in nxt.get("note", "")
