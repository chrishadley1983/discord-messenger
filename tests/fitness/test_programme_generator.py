"""Unit tests for the 12-week programme generator."""

import pytest

from domains.fitness.programme_generator import (
    generate_week,
    generate_programme,
    session_to_dict,
    _progress,
)


class TestProgressFunction:
    def test_reps_increase_with_week(self):
        # Week 1: base 10
        reps_w1, hold_w1 = _progress(10, None, 1)
        reps_w4, hold_w4 = _progress(10, None, 4)
        assert reps_w1 == 10
        assert reps_w4 == 13
        assert hold_w1 is None

    def test_hold_increases_by_5s(self):
        reps, hold = _progress(None, 30, 4)
        assert hold == 30 + 3 * 5   # week 4 = base + (4-1)*5
        assert reps is None

    def test_rep_cap_at_double(self):
        # Base 10, week 15 would be 24 — capped at 20
        reps, _ = _progress(10, None, 15)
        assert reps == 20

    def test_hold_cap_at_double(self):
        _, hold = _progress(None, 30, 20)
        assert hold == 60


class TestGenerateWeek:
    def test_5x_short_returns_7_days(self):
        week = generate_week("5x_short", 1)
        assert len(week) == 7

    def test_weekend_is_recovery_and_rest(self):
        week = generate_week("5x_short", 1)
        days_by_dow = {s.day_of_week: s for s in week}
        assert days_by_dow[5].session_type == "mobility"
        assert days_by_dow[6].session_type == "rest"
        assert days_by_dow[6].is_rest is True

    def test_all_weekdays_have_strength_session(self):
        week = generate_week("5x_short", 1)
        weekdays = [s for s in week if s.day_of_week < 5]
        assert len(weekdays) == 5
        for s in weekdays:
            assert s.is_rest is False
            assert s.duration_min == 20
            assert len(s.exercises) >= 4   # 4-5 exercises per session

    def test_progression_increases_volume(self):
        week1 = generate_week("5x_short", 1)
        week6 = generate_week("5x_short", 6)

        # Find the push session in both
        push_w1 = next(s for s in week1 if s.session_type == "push")
        push_w6 = next(s for s in week6 if s.session_type == "push")

        # First rep-based exercise should have more reps in week 6
        w1_reps = next(e for e in push_w1.exercises if e.reps is not None)
        w6_reps = next(
            e for e in push_w6.exercises if e.exercise_slug == w1_reps.exercise_slug
        )
        assert w6_reps.reps > w1_reps.reps

    def test_unknown_split_raises(self):
        with pytest.raises(NotImplementedError):
            generate_week("unknown_split", 1)  # type: ignore


class TestGenerateProgramme:
    def test_13_weeks_default(self):
        programme = generate_programme("5x_short")
        assert len(programme) == 13
        assert all(len(week) == 7 for week in programme)

    def test_custom_duration(self):
        programme = generate_programme("5x_short", weeks=8)
        assert len(programme) == 8


class TestSessionSerialisation:
    def test_serialises_to_expected_shape(self):
        week = generate_week("5x_short", 1)
        push = next(s for s in week if s.session_type == "push")
        d = session_to_dict(push)
        assert d["session_type"] == "push"
        assert d["day_of_week"] == 0
        assert d["duration_min"] == 20
        assert isinstance(d["exercises"], list)
        assert all("exercise_slug" in e for e in d["exercises"])
