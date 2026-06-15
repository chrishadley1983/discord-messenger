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


def in_dispatch_window(ts: datetime, dispatches: dict | None = None) -> bool:
    """True if ts falls inside a planned/completed dispatch slot."""
    if dispatches is None:
        try:
            dispatches = get_dispatches()
        except Exception:
            return False
    iso = ts.isoformat()
    for d in dispatches.get("planned", []) + dispatches.get("completed", []):
        if d.get("start") and d.get("end") and d["start"] <= iso <= d["end"]:
            return True
    return False
