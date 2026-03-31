"""Commitment tracking API endpoints.

Provides REST access to the commitments table for Peter's nudge job
and for Chris to manage (resolve/dismiss) detected commitments.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from hadley_api.auth import require_auth

from domains.commitments import (
    get_open_commitments,
    update_commitment,
    record_nudge,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/commitments", tags=["commitments"])


@router.get("", dependencies=[Depends(require_auth)])
async def list_commitments(
    status: str = Query("open", description="Filter by status: open, resolved, dismissed"),
    min_age_hours: int = Query(0, description="Only show commitments older than N hours"),
    limit: int = Query(20, description="Max results"),
):
    """List commitments, defaulting to open ones."""
    items = await get_open_commitments(min_age_hours=min_age_hours, limit=limit)
    return {"count": len(items), "commitments": items}


@router.post("/{commitment_id}/resolve", dependencies=[Depends(require_auth)])
async def resolve_commitment(commitment_id: str):
    """Mark a commitment as resolved (Chris followed through)."""
    ok = await update_commitment(commitment_id, "resolved")
    if ok:
        return {"status": "resolved", "id": commitment_id}
    return JSONResponse({"error": "Failed to resolve"}, status_code=500)


@router.post("/{commitment_id}/dismiss", dependencies=[Depends(require_auth)])
async def dismiss_commitment(commitment_id: str, reason: Optional[str] = None):
    """Dismiss a commitment (false positive or no longer relevant)."""
    ok = await update_commitment(commitment_id, "dismissed", reason=reason)
    if ok:
        return {"status": "dismissed", "id": commitment_id, "reason": reason}
    return JSONResponse({"error": "Failed to dismiss"}, status_code=500)


@router.post("/{commitment_id}/nudge", dependencies=[Depends(require_auth)])
async def nudge_commitment(commitment_id: str):
    """Record that a nudge was sent for this commitment."""
    ok = await record_nudge(commitment_id)
    if ok:
        return {"status": "nudged", "id": commitment_id}
    return JSONResponse({"error": "Failed to record nudge"}, status_code=500)
