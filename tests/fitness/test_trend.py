"""Unit tests for the weight trend math."""

from datetime import date, timedelta

import pytest

from domains.fitness.trend import (
    sma,
    ema,
    linear_slope,
    compute_trend,
)


def _gen(start_day: date, values: list[float]) -> list[dict]:
    return [
        {"date": (start_day + timedelta(days=i)).isoformat(), "value": v}
        for i, v in enumerate(values)
    ]


class TestSMA:
    def test_empty(self):
        assert sma([]) is None

    def test_less_than_window(self):
        assert sma([90, 91]) == pytest.approx(90.5)

    def test_uses_tail(self):
        # Window=3, values [80,81,82,90,91,92] -> avg(90,91,92)
        assert sma([80, 81, 82, 90, 91, 92], window=3) == pytest.approx(91.0)


class TestEMA:
    def test_empty(self):
        assert ema([]) is None

    def test_single_value(self):
        assert ema([94.0]) == 94.0

    def test_weights_recent_higher(self):
        values = [100, 100, 100, 100, 90]
        e = ema(values, alpha=0.5)
        # Recent 90 pulls the EMA below 100
        assert 90 < e < 100


class TestLinearSlope:
    def test_too_few_points(self):
        assert linear_slope([]) is None
        assert linear_slope([(0, 90)]) is None

    def test_exact_line(self):
        pts = [(0, 100.0), (1, 99.0), (2, 98.0), (3, 97.0)]
        slope = linear_slope(pts)
        assert slope == pytest.approx(-1.0)

    def test_flat_line(self):
        pts = [(0, 90.0), (1, 90.0), (2, 90.0)]
        assert linear_slope(pts) == pytest.approx(0.0)


class TestComputeTrend:
    def test_no_readings(self):
        r = compute_trend([])
        assert r.readings_count == 0
        assert r.latest_raw is None
        assert r.trend_7d is None
        assert "No weight" in r.message

    def test_clear_downtrend(self):
        # Linear loss of 0.5kg/day over 14 days = 3.5kg/week (unrealistic but tests math)
        start = date(2026, 5, 1)
        values = [94.0 - 0.1 * i for i in range(14)]
        readings = _gen(start, values)
        r = compute_trend(readings)
        assert r.readings_count == 14
        assert r.latest_raw == pytest.approx(92.7)
        assert r.slope_kg_per_week is not None
        assert r.slope_kg_per_week < -0.6
        assert r.stalled is False

    def test_stall_detection(self):
        # Flat for 14 days
        start = date(2026, 5, 1)
        readings = _gen(start, [93.0] * 14)
        r = compute_trend(readings)
        assert r.stalled is True
        assert "STALL" in r.message.upper() or "stalled" in r.message.lower()

    def test_slight_loss_not_stalled(self):
        # -0.5 kg/week = slope -0.5 → not stalled
        start = date(2026, 5, 1)
        values = [94.0 - (0.5 / 7) * i for i in range(14)]
        r = compute_trend(_gen(start, values))
        assert r.stalled is False

    def test_handles_string_dates_and_floats(self):
        readings = [
            {"date": "2026-05-01", "value": "94.2"},
            {"date": "2026-05-02", "value": 94.0},
        ]
        r = compute_trend(readings)
        assert r.readings_count == 2
        assert r.latest_raw == 94.0

    def test_ignores_none_values(self):
        readings = [
            {"date": "2026-05-01", "value": 94.0},
            {"date": "2026-05-02", "value": None},
            {"date": "2026-05-03", "value": 93.7},
        ]
        r = compute_trend(readings)
        assert r.readings_count == 2
