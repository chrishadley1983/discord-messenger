"""Formatting helpers for currency, markdown tables, and period labels."""

from __future__ import annotations


def gbp(amount: float | int | None, show_sign: bool = False) -> str:
    """Format a number as GBP currency string."""
    if amount is None:
        return "£0.00"
    v = float(amount)
    sign = "+" if show_sign and v > 0 else ""
    if v < 0:
        return f"-£{abs(v):,.2f}"
    return f"{sign}£{v:,.2f}"


def pct(value: float | int | None, decimals: int = 1) -> str:
    """Format a number as a percentage string."""
    if value is None:
        return "0.0%"
    return f"{float(value):.{decimals}f}%"


def change_str(current: float, previous: float) -> str:
    """Return a formatted change string like '+£1,234 (+5.2%)'."""
    diff = current - previous
    if previous and previous != 0:
        pct_change = (diff / abs(previous)) * 100
        return f"{gbp(diff, show_sign=True)} ({pct(pct_change)})"
    return gbp(diff, show_sign=True)


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    """Build a simple markdown table."""
    if not rows:
        return "_No data_"
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def period_label(period: str) -> str:
    """Human-readable label for a period key."""
    labels = {
        "this_month": "This month",
        "last_month": "Last month",
        "this_quarter": "This quarter",
        "last_quarter": "Last quarter",
        "this_year": "This year",
        "last_year": "Last year",
        "all_time": "All time",
    }
    return labels.get(period, period)


def safe_float(val, default: float = 0.0) -> float:
    """Safely convert a value to float, returning default on failure."""
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default
