"""Accountability tracker service.

CRUD operations for goals, milestones, and progress entries.
All queries use httpx + PostgREST against Supabase.
"""

import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
UK_TZ = ZoneInfo("Europe/London")

def _today() -> date:
    """Current date in UK timezone."""
    return datetime.now(UK_TZ).date()


GOALS_TABLE = "accountability_goals"
MILESTONES_TABLE = "accountability_milestones"
PROGRESS_TABLE = "accountability_progress"


def _headers(*, returning: bool = False) -> dict:
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if returning:
        h["Prefer"] = "return=representation"
    else:
        h["Prefer"] = "return=minimal"
    return h


def _read_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }


def _url(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"


# ── Goals CRUD ───────────────────────────────────────────────────────────


async def create_goal(
    title: str,
    goal_type: str,
    metric: str,
    target_value: float,
    category: str = "general",
    description: str | None = None,
    start_value: float = 0,
    direction: str = "up",
    frequency: str | None = None,
    deadline: str | None = None,
    auto_source: str | None = None,
) -> dict | None:
    """Create a new goal. Returns the created row or None on failure."""
    payload = {
        "title": title,
        "goal_type": goal_type,
        "metric": metric,
        "target_value": target_value,
        "current_value": start_value,
        "start_value": start_value,
        "category": category,
        "direction": direction,
    }
    if description:
        payload["description"] = description
    if frequency:
        payload["frequency"] = frequency
    if deadline:
        payload["deadline"] = deadline
    if auto_source:
        payload["auto_source"] = auto_source

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _url(GOALS_TABLE),
                headers=_headers(returning=True),
                json=payload,
            )
            if resp.status_code in (200, 201):
                rows = resp.json()
                return rows[0] if rows else None
            logger.error(f"Create goal failed ({resp.status_code}): {resp.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"Create goal error: {e}")
        return None


async def get_goals(status: str = "active") -> list[dict]:
    """Fetch goals filtered by status."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            params = {"select": "*", "order": "created_at.asc"}
            if status != "all":
                params["status"] = f"eq.{status}"
            resp = await client.get(
                _url(GOALS_TABLE), headers=_read_headers(), params=params
            )
            if resp.status_code == 200:
                return resp.json()
            logger.error(f"Get goals failed: {resp.status_code}")
            return []
    except Exception as e:
        logger.error(f"Get goals error: {e}")
        return []


async def get_goal(goal_id: str) -> dict | None:
    """Fetch a single goal by ID."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _url(GOALS_TABLE),
                headers=_read_headers(),
                params={"id": f"eq.{goal_id}", "select": "*"},
            )
            if resp.status_code == 200:
                rows = resp.json()
                return rows[0] if rows else None
            return None
    except Exception as e:
        logger.error(f"Get goal error: {e}")
        return None


async def update_goal(goal_id: str, **fields) -> bool:
    """Update goal fields. Returns True on success."""
    if not fields:
        return True
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.patch(
                _url(GOALS_TABLE),
                headers=_headers(),
                params={"id": f"eq.{goal_id}"},
                json=fields,
            )
            return resp.status_code in (200, 204)
    except Exception as e:
        logger.error(f"Update goal error: {e}")
        return False


async def delete_goal(goal_id: str) -> bool:
    """Soft-delete a goal by setting status to abandoned."""
    return await update_goal(goal_id, status="abandoned")


# ── Milestones ───────────────────────────────────────────────────────────


async def add_milestone(goal_id: str, title: str, target_value: float) -> dict | None:
    """Add a milestone to a goal."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _url(MILESTONES_TABLE),
                headers=_headers(returning=True),
                json={
                    "goal_id": goal_id,
                    "title": title,
                    "target_value": target_value,
                },
            )
            if resp.status_code in (200, 201):
                rows = resp.json()
                return rows[0] if rows else None
            return None
    except Exception as e:
        logger.error(f"Add milestone error: {e}")
        return None


async def get_milestones(goal_id: str) -> list[dict]:
    """Fetch milestones for a goal, ordered by target_value."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _url(MILESTONES_TABLE),
                headers=_read_headers(),
                params={
                    "goal_id": f"eq.{goal_id}",
                    "select": "*",
                    "order": "target_value.asc",
                },
            )
            return resp.json() if resp.status_code == 200 else []
    except Exception as e:
        logger.error(f"Get milestones error: {e}")
        return []


async def check_milestones(goal_id: str, current_value: float, direction: str = "up") -> list[dict]:
    """Check for newly-reached milestones. Returns list of just-reached milestones."""
    milestones = await get_milestones(goal_id)
    newly_reached = []
    now = datetime.now(timezone.utc).isoformat()

    for m in milestones:
        if m.get("reached_at"):
            continue  # Already reached
        reached = (
            current_value >= m["target_value"]
            if direction == "up"
            else current_value <= m["target_value"]
        )
        if reached:
            # Mark as reached
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.patch(
                        _url(MILESTONES_TABLE),
                        headers=_headers(),
                        params={"id": f"eq.{m['id']}"},
                        json={"reached_at": now},
                    )
                m["reached_at"] = now
                newly_reached.append(m)
            except Exception as e:
                logger.error(f"Mark milestone reached error: {e}")

    return newly_reached


# ── Progress ─────────────────────────────────────────────────────────────


async def log_progress(
    goal_id: str,
    value: float,
    source: str = "manual",
    note: str | None = None,
    log_date: str | None = None,
) -> dict | None:
    """Log a progress entry. Handles dedup for auto-sources via upsert.

    For auto-sources, updates existing entry for the same (goal_id, date, source).
    For manual/peter_chat, always creates a new entry.
    """
    target_date = log_date or _today().isoformat()

    # Calculate delta from previous entry
    delta = None
    prev = await _get_latest_progress(goal_id)
    if prev is not None:
        delta = value - prev

    payload = {
        "goal_id": goal_id,
        "value": value,
        "delta": delta,
        "source": source,
        "date": target_date,
    }
    if note:
        payload["note"] = note

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if source not in ("manual", "peter_chat"):
                # Auto-sources: check-then-upsert to dedup (partial unique index
                # can't be used with PostgREST on_conflict param)
                existing = await client.get(
                    _url(PROGRESS_TABLE),
                    headers=_read_headers(),
                    params={
                        "goal_id": f"eq.{goal_id}",
                        "date": f"eq.{target_date}",
                        "source": f"eq.{source}",
                        "select": "id",
                        "limit": "1",
                    },
                )
                if existing.status_code == 200 and existing.json():
                    # Update existing row
                    row_id = existing.json()[0]["id"]
                    resp = await client.patch(
                        _url(PROGRESS_TABLE),
                        headers=_headers(returning=True),
                        params={"id": f"eq.{row_id}"},
                        json=payload,
                    )
                else:
                    # Insert new row
                    resp = await client.post(
                        _url(PROGRESS_TABLE),
                        headers=_headers(returning=True),
                        json=payload,
                    )
            else:
                # Manual/chat: always insert new
                resp = await client.post(
                    _url(PROGRESS_TABLE),
                    headers=_headers(returning=True),
                    json=payload,
                )

            if resp.status_code in (200, 201, 204):
                rows = resp.json() if resp.status_code != 204 else []
                entry = rows[0] if rows else payload

                # Update current_value on the goal
                goal = await get_goal(goal_id)
                if goal:
                    await _update_goal_current_value(goal, value)

                return entry
            logger.error(f"Log progress failed ({resp.status_code}): {resp.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"Log progress error: {e}")
        return None


async def _get_latest_progress(goal_id: str) -> float | None:
    """Get the most recent progress value for a goal."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _url(PROGRESS_TABLE),
                headers=_read_headers(),
                params={
                    "goal_id": f"eq.{goal_id}",
                    "select": "value",
                    "order": "logged_at.desc",
                    "limit": "1",
                },
            )
            if resp.status_code == 200:
                rows = resp.json()
                return float(rows[0]["value"]) if rows else None
            return None
    except Exception:
        return None


async def _update_goal_current_value(goal: dict, new_value: float) -> None:
    """Update the cached current_value and streak on a goal."""
    updates: dict[str, Any] = {"current_value": new_value}
    today = _today()

    # Streak tracking for habits
    if goal["goal_type"] == "habit" and goal.get("target_value"):
        target = float(goal["target_value"])
        direction = goal.get("direction", "up")
        hit = new_value >= target if direction == "up" else new_value <= target

        if hit:
            last_hit = goal.get("last_hit_date")
            current_streak = goal.get("current_streak", 0)
            best_streak = goal.get("best_streak", 0)

            if last_hit:
                last_hit_date = date.fromisoformat(last_hit) if isinstance(last_hit, str) else last_hit
                days_gap = (today - last_hit_date).days
                if days_gap <= 1:
                    # Consecutive day (or same day update)
                    if days_gap == 1:
                        current_streak += 1
                else:
                    # Streak broken, start new
                    current_streak = 1
            else:
                current_streak = 1

            updates["current_streak"] = current_streak
            updates["best_streak"] = max(best_streak, current_streak)
            updates["last_hit_date"] = today.isoformat()

    # Check if target goal is now complete
    if goal["goal_type"] == "target":
        target = float(goal["target_value"])
        direction = goal.get("direction", "up")
        complete = new_value >= target if direction == "up" else new_value <= target
        if complete and goal.get("status") == "active":
            updates["status"] = "completed"
            updates["completed_at"] = datetime.now(timezone.utc).isoformat()

    await update_goal(goal["id"], **updates)

    # Check milestones
    await check_milestones(
        goal["id"], new_value, direction=goal.get("direction", "up")
    )


async def get_progress(goal_id: str, days: int = 30) -> list[dict]:
    """Fetch progress history for a goal."""
    cutoff = (_today() - timedelta(days=days)).isoformat()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _url(PROGRESS_TABLE),
                headers=_read_headers(),
                params={
                    "goal_id": f"eq.{goal_id}",
                    "date": f"gte.{cutoff}",
                    "select": "*",
                    "order": "date.desc",
                },
            )
            return resp.json() if resp.status_code == 200 else []
    except Exception as e:
        logger.error(f"Get progress error: {e}")
        return []


# ── Computed Status ──────────────────────────────────────────────────────


def compute_goal_status(goal: dict, progress: list[dict]) -> dict:
    """Compute derived metrics for a goal.

    Returns:
        Dict with pct, on_track, trend, streak info, hit_rate
    """
    current = float(goal.get("current_value", 0))
    target = float(goal["target_value"])
    start = float(goal.get("start_value", 0))
    direction = goal.get("direction", "up")

    # Percentage complete
    if goal["goal_type"] == "target":
        denom = abs(target - start) if target != start else 1
        if direction == "up":
            pct = max(0, min(100, (current - start) / denom * 100))
        else:
            pct = max(0, min(100, (start - current) / denom * 100))
    else:
        # Habit: today's value vs target
        pct = max(0, min(100, current / target * 100)) if target else 0

    # On-track score (target goals only)
    on_track = None
    if goal["goal_type"] == "target" and goal.get("deadline") and goal.get("start_date"):
        start_date = date.fromisoformat(goal["start_date"]) if isinstance(goal["start_date"], str) else goal["start_date"]
        deadline = date.fromisoformat(goal["deadline"]) if isinstance(goal["deadline"], str) else goal["deadline"]
        total_days = (deadline - start_date).days or 1
        elapsed_days = (_today() - start_date).days
        expected_pct = min(100, elapsed_days / total_days * 100)
        on_track = round(pct / expected_pct * 100) if expected_pct > 0 else 100

    # Trend: compare last 7 days avg to previous 7 days avg
    trend = _compute_trend(progress)

    # Hit rate for habits (last 7 and 30 days)
    hit_rate_7 = None
    hit_rate_30 = None
    if goal["goal_type"] == "habit":
        hit_rate_7 = _compute_hit_rate(progress, target, direction, days=7)
        hit_rate_30 = _compute_hit_rate(progress, target, direction, days=30)

    return {
        "pct": round(pct, 1),
        "on_track": on_track,
        "trend": trend,
        "current_streak": goal.get("current_streak", 0),
        "best_streak": goal.get("best_streak", 0),
        "hit_rate_7": hit_rate_7,
        "hit_rate_30": hit_rate_30,
    }


def _compute_trend(progress: list[dict]) -> str:
    """Compare last 7 days avg to previous 7 days avg. Returns ↑, ↓, or →."""
    today = _today()
    recent = []
    previous = []

    for p in progress:
        p_date = date.fromisoformat(p["date"]) if isinstance(p["date"], str) else p["date"]
        days_ago = (today - p_date).days
        if days_ago < 7:
            recent.append(float(p["value"]))
        elif days_ago < 14:
            previous.append(float(p["value"]))

    if not recent or not previous:
        return "→"

    recent_avg = sum(recent) / len(recent)
    prev_avg = sum(previous) / len(previous)

    if prev_avg == 0:
        return "→"

    change_pct = (recent_avg - prev_avg) / abs(prev_avg) * 100
    if change_pct > 2:
        return "↑"
    elif change_pct < -2:
        return "↓"
    return "→"


def _compute_hit_rate(
    progress: list[dict], target: float, direction: str, days: int
) -> dict:
    """Compute habit hit rate over a period."""
    today = _today()
    cutoff = today - timedelta(days=days)
    hits = 0
    total = 0

    for p in progress:
        p_date = date.fromisoformat(p["date"]) if isinstance(p["date"], str) else p["date"]
        if p_date >= cutoff:
            total += 1
            val = float(p["value"])
            hit = val >= target if direction == "up" else val <= target
            if hit:
                hits += 1

    # Denominator is the number of days in the window, not entries logged.
    # Days with no entry count as misses for daily habits.
    return {"hits": hits, "total": days, "days": days}


# ── Summary & Reports ────────────────────────────────────────────────────


async def get_daily_summary(target_date: str | None = None) -> dict:
    """All active goals with their computed status for today."""
    goals = await get_goals(status="active")
    result = []

    for goal in goals:
        progress = await get_progress(goal["id"], days=30)
        status = compute_goal_status(goal, progress)
        milestones = await get_milestones(goal["id"])
        result.append({
            **goal,
            "computed": status,
            "milestones": milestones,
        })

    return {"goals": result, "count": len(result), "date": target_date or _today().isoformat()}


async def get_report_data(period: str = "week") -> dict:
    """Aggregated report data for weekly or monthly reports."""
    goals = await get_goals(status="active")
    days = 7 if period == "week" else 30

    goal_reports = []
    total_on_track = []

    for goal in goals:
        progress = await get_progress(goal["id"], days=days)
        status = compute_goal_status(goal, progress)
        milestones = await get_milestones(goal["id"])

        # Find milestones reached this period
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        newly_reached = [
            m for m in milestones
            if m.get("reached_at") and not m.get("celebrated")
            and datetime.fromisoformat(m["reached_at"].replace("Z", "+00:00")) > cutoff
        ]

        # Period delta (sum of deltas in period)
        period_delta = sum(
            float(p.get("delta", 0) or 0) for p in progress
            if p.get("date") and date.fromisoformat(p["date"]) >= _today() - timedelta(days=days)
        )

        goal_reports.append({
            **goal,
            "computed": status,
            "milestones": milestones,
            "newly_reached_milestones": newly_reached,
            "period_delta": round(period_delta, 2),
            "progress_entries": len(progress),
        })

        if status.get("on_track") is not None:
            total_on_track.append(status["on_track"])
        elif status.get("hit_rate_7"):
            hr = status["hit_rate_7"]
            if hr["days"] > 0:
                total_on_track.append(hr["hits"] / max(hr["days"], 1) * 100)

    # Overall score
    avg_on_track = sum(total_on_track) / len(total_on_track) if total_on_track else 0
    grade = _score_to_grade(avg_on_track)

    return {
        "period": period,
        "days": days,
        "goals": goal_reports,
        "count": len(goal_reports),
        "overall_score": round(avg_on_track, 1),
        "grade": grade,
        "report_date": _today().isoformat(),
    }


def _score_to_grade(score: float) -> str:
    """Convert on-track percentage to letter grade."""
    if score >= 90:
        return "A"
    elif score >= 80:
        return "B+"
    elif score >= 70:
        return "B"
    elif score >= 60:
        return "C+"
    elif score >= 50:
        return "C"
    elif score >= 40:
        return "D"
    return "F"
