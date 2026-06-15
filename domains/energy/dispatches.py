"""Intelligent Octopus Go planned dispatches (EV charging slots).

Octopus schedules the car's charging and exposes the slots via GraphQL —
this replaces threshold-guessing ("off-peak > 5 kWh = probably the car")
with ground truth for EV attribution.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .config import OCTOPUS_ACCOUNT

_QUERY = """
query($acc: String!) {
  plannedDispatches(accountNumber: $acc) {
    start end
    delta
    meta { source location }
  }
  completedDispatches(accountNumber: $acc) {
    start end
    delta
    meta { source location }
  }
}
"""


def get_dispatches() -> dict:
    """Planned + recent completed EV charge dispatches."""
    from .kraken import gql

    data = gql(_QUERY, {"acc": OCTOPUS_ACCOUNT})

    def _fmt(d):
        return {
            "start": d.get("start"),
            "end": d.get("end"),
            "kwh": abs(float(d.get("delta") or 0)),
            "source": (d.get("meta") or {}).get("source"),
        }

    return {
        "planned": [_fmt(d) for d in data.get("plannedDispatches") or []],
        "completed": [_fmt(d) for d in (data.get("completedDispatches") or [])[:10]],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def _parse_iso(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def in_dispatch_window(ts: datetime, dispatches: dict | None = None) -> bool:
    """True if ts falls inside a planned/completed dispatch slot.

    Compares as timezone-aware instants, not ISO strings. Octopus consumption
    timestamps carry a local offset (e.g. +01:00 during BST) while dispatch
    slots come back in UTC, so a raw string compare silently misfires by the
    BST offset — "23:30+01:00" sorts after "22:30+00:00" despite being the
    same instant.
    """
    if dispatches is None:
        try:
            dispatches = get_dispatches()
        except Exception:
            return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    for d in dispatches.get("planned", []) + dispatches.get("completed", []):
        start = _parse_iso(d.get("start"))
        end = _parse_iso(d.get("end"))
        if start and end and start <= ts <= end:
            return True
    return False
