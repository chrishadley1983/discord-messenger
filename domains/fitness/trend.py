"""Weight trend math.

Day-to-day weight fluctuates 0.5-1.5kg from water, sodium, carbs, stress.
The only honest measure is a smoothed trend line. We use:

1. 7-day simple moving average for the headline "trend weight"
2. Exponential moving average (alpha=0.1) as a smoother signal
3. Linear regression slope over last 14 days for "kg/week" trajectory

If trend stalls (slope > -0.1 kg/week over 10+ days) we flag an adjustment.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable


@dataclass
class TrendResult:
    readings_count: int
    latest_raw: float | None
    trend_7d: float | None         # 7-day simple moving average
    trend_ema: float | None        # EMA alpha=0.1
    slope_kg_per_week: float | None  # linear regression slope over window
    stalled: bool                  # slope > -0.1 and window >= 10 days
    message: str                   # human-readable summary


def sma(values: list[float], window: int = 7) -> float | None:
    """Simple moving average over the last `window` values."""
    if not values:
        return None
    tail = values[-window:]
    return sum(tail) / len(tail)


def ema(values: list[float], alpha: float = 0.1) -> float | None:
    """Exponential moving average. More weight on recent readings."""
    if not values:
        return None
    result = values[0]
    for v in values[1:]:
        result = alpha * v + (1 - alpha) * result
    return result


def linear_slope(points: list[tuple[int, float]]) -> float | None:
    """Least-squares slope of y vs x. Returns None if < 2 points.

    Input: list of (day_index, weight_kg) tuples.
    Returns slope in kg per day.
    """
    n = len(points)
    if n < 2:
        return None
    sum_x = sum(p[0] for p in points)
    sum_y = sum(p[1] for p in points)
    sum_xy = sum(p[0] * p[1] for p in points)
    sum_x2 = sum(p[0] * p[0] for p in points)
    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return None
    return (n * sum_xy - sum_x * sum_y) / denom


def compute_trend(
    readings: Iterable[dict],
    programme_start: date | None = None,
) -> TrendResult:
    """Compute the full trend summary from weight readings.

    Args:
        readings: Iterable of {"date": "YYYY-MM-DD", "value": float}
                  (oldest-first order is fine; we sort internally).
        programme_start: if set, drop readings before this date so an old
            pre-programme weight doesn't contaminate the new cut's trend.

    Returns:
        TrendResult with 7-day SMA, EMA, slope and stall flag.
    """
    items = sorted(
        (
            {"date": date.fromisoformat(r["date"]), "value": float(r["value"])}
            for r in readings
            if r.get("value") is not None
        ),
        key=lambda r: r["date"],
    )
    if programme_start is not None:
        items = [r for r in items if r["date"] >= programme_start]
    n = len(items)

    if n == 0:
        return TrendResult(0, None, None, None, None, False, "No weight readings yet")

    values = [r["value"] for r in items]
    latest_raw = values[-1]
    t_sma = sma(values, 7)
    t_ema = ema(values, alpha=0.1)

    # Slope over last 14 days (or all we have)
    window_items = items[-14:]
    if len(window_items) >= 2:
        base_day = window_items[0]["date"].toordinal()
        points = [(r["date"].toordinal() - base_day, r["value"]) for r in window_items]
        slope_per_day = linear_slope(points)
        slope_per_week = slope_per_day * 7 if slope_per_day is not None else None
    else:
        slope_per_week = None

    # Stall detection: need at least 3 readings spanning 10+ days with slope worse than -0.1 kg/wk.
    # Without the >=3 floor a single outlier vs one other reading can fake a stall.
    window_days = (window_items[-1]["date"] - window_items[0]["date"]).days if len(window_items) >= 2 else 0
    stalled = bool(
        slope_per_week is not None
        and len(window_items) >= 3
        and window_days >= 10
        and slope_per_week > -0.1
    )

    if stalled:
        message = (
            f"Trend stalled: {slope_per_week:+.2f} kg/wk over {window_days} days. "
            "Recommend -100 kcal and +2k daily steps."
        )
    elif slope_per_week is not None:
        message = f"On track: {slope_per_week:+.2f} kg/wk over {window_days} days."
    else:
        message = "Not enough data to compute trend (need 2+ readings)."

    return TrendResult(
        readings_count=n,
        latest_raw=latest_raw,
        trend_7d=t_sma,
        trend_ema=t_ema,
        slope_kg_per_week=slope_per_week,
        stalled=stalled,
        message=message,
    )
