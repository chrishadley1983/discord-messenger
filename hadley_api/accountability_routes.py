"""Accountability tracker API endpoints.

CRUD for goals, milestones, and progress entries.
Powers the dashboard UI and Peter's conversational updates.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from hadley_api.auth import require_auth

from domains.accountability.service import (
    create_goal,
    get_goals,
    get_goal,
    update_goal,
    delete_goal,
    add_milestone,
    get_milestones,
    log_progress,
    get_progress,
    get_daily_summary,
    get_report_data,
    compute_goal_status,
)
from domains.accountability.auto_sources import run_auto_updates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/accountability", tags=["accountability"])


# ── Request Models ───────────────────────────────────────────────────────


class CreateGoalRequest(BaseModel):
    title: str
    goal_type: str  # "target" or "habit"
    metric: str
    target_value: float
    category: str = "general"
    description: Optional[str] = None
    start_value: float = 0
    direction: str = "up"
    frequency: Optional[str] = None
    deadline: Optional[str] = None
    auto_source: Optional[str] = None


class UpdateGoalRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    target_value: Optional[float] = None
    status: Optional[str] = None
    deadline: Optional[str] = None
    auto_source: Optional[str] = None


class CreateMilestoneRequest(BaseModel):
    title: str
    target_value: float


class LogProgressRequest(BaseModel):
    value: float
    source: str = "manual"
    note: Optional[str] = None
    date: Optional[str] = None


# ── Goals ────────────────────────────────────────────────────────────────


@router.get("/goals", dependencies=[Depends(require_auth)])
async def list_goals(
    status: str = Query("active", description="Filter: active, paused, completed, abandoned, all"),
):
    """List goals with computed status metrics."""
    goals = await get_goals(status=status)
    enriched = []
    for g in goals:
        progress = await get_progress(g["id"], days=30)
        computed = compute_goal_status(g, progress)
        enriched.append({**g, "computed": computed})
    return {"count": len(enriched), "goals": enriched}


@router.post("/goals", dependencies=[Depends(require_auth)])
async def create_goal_endpoint(req: CreateGoalRequest):
    """Create a new goal."""
    goal = await create_goal(
        title=req.title,
        goal_type=req.goal_type,
        metric=req.metric,
        target_value=req.target_value,
        category=req.category,
        description=req.description,
        start_value=req.start_value,
        direction=req.direction,
        frequency=req.frequency,
        deadline=req.deadline,
        auto_source=req.auto_source,
    )
    if goal:
        return {"status": "created", "goal": goal}
    return JSONResponse({"error": "Failed to create goal"}, status_code=500)


@router.get("/goals/{goal_id}", dependencies=[Depends(require_auth)])
async def get_goal_endpoint(goal_id: str):
    """Get goal detail with recent progress."""
    goal = await get_goal(goal_id)
    if not goal:
        return JSONResponse({"error": "Goal not found"}, status_code=404)
    progress = await get_progress(goal_id, days=30)
    computed = compute_goal_status(goal, progress)
    milestones = await get_milestones(goal_id)
    return {
        **goal,
        "computed": computed,
        "milestones": milestones,
        "recent_progress": progress[:10],
    }


@router.patch("/goals/{goal_id}", dependencies=[Depends(require_auth)])
async def update_goal_endpoint(goal_id: str, req: UpdateGoalRequest):
    """Update goal fields."""
    fields = req.model_dump(exclude_unset=True)
    if not fields:
        return {"status": "no changes"}
    ok = await update_goal(goal_id, **fields)
    if ok:
        return {"status": "updated", "id": goal_id}
    return JSONResponse({"error": "Failed to update goal"}, status_code=500)


@router.delete("/goals/{goal_id}", dependencies=[Depends(require_auth)])
async def delete_goal_endpoint(goal_id: str):
    """Soft-delete (abandon) a goal."""
    ok = await delete_goal(goal_id)
    if ok:
        return {"status": "abandoned", "id": goal_id}
    return JSONResponse({"error": "Failed to delete goal"}, status_code=500)


# ── Milestones ───────────────────────────────────────────────────────────


@router.post("/goals/{goal_id}/milestones", dependencies=[Depends(require_auth)])
async def create_milestone_endpoint(goal_id: str, req: CreateMilestoneRequest):
    """Add a milestone to a goal."""
    milestone = await add_milestone(goal_id, req.title, req.target_value)
    if milestone:
        return {"status": "created", "milestone": milestone}
    return JSONResponse({"error": "Failed to create milestone"}, status_code=500)


@router.get("/goals/{goal_id}/milestones", dependencies=[Depends(require_auth)])
async def list_milestones_endpoint(goal_id: str):
    """List milestones for a goal."""
    milestones = await get_milestones(goal_id)
    return {"count": len(milestones), "milestones": milestones}


# ── Progress ─────────────────────────────────────────────────────────────


@router.post("/goals/{goal_id}/progress", dependencies=[Depends(require_auth)])
async def log_progress_endpoint(goal_id: str, req: LogProgressRequest):
    """Log a progress entry."""
    entry = await log_progress(
        goal_id=goal_id,
        value=req.value,
        source=req.source,
        note=req.note,
        log_date=req.date,
    )
    if entry:
        return {"status": "logged", "entry": entry}
    return JSONResponse({"error": "Failed to log progress"}, status_code=500)


@router.get("/goals/{goal_id}/progress", dependencies=[Depends(require_auth)])
async def get_progress_endpoint(
    goal_id: str,
    days: int = Query(30, description="Number of days of history"),
):
    """Get progress history for a goal."""
    progress = await get_progress(goal_id, days=days)
    return {"count": len(progress), "progress": progress}


# ── Summary & Reports ────────────────────────────────────────────────────


@router.get("/summary", dependencies=[Depends(require_auth)])
async def get_summary():
    """All-goals summary for the dashboard."""
    return await get_daily_summary()


@router.get("/report", dependencies=[Depends(require_auth)])
async def get_report(
    period: str = Query("week", description="Report period: week or month"),
):
    """Aggregated report data for weekly/monthly reports."""
    return await get_report_data(period=period)


@router.post("/auto-update", dependencies=[Depends(require_auth)])
async def trigger_auto_update():
    """Manually trigger auto-updates for all goals with auto_source."""
    result = await run_auto_updates()
    return result
