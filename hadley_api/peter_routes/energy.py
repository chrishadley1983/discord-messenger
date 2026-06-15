"""Live energy endpoints (Octopus Home Mini).

- GET /energy/live    — current demand W, today-so-far kWh/£, current rate
- GET /energy/today   — today's 1-minute demand curve + totals
- GET /energy/summary — recent complete daily summaries (both fuels)

Read-only; data via domains.energy.service (Kraken GraphQL + Supabase).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from domains.energy import service

router = APIRouter(prefix="/energy", tags=["energy"])


@router.get("/live")
async def energy_live():
    try:
        return await asyncio.to_thread(service.live_status)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"live energy unavailable: {e}")


@router.get("/today")
async def energy_today(include_curve: bool = False):
    try:
        data = await asyncio.to_thread(service.today_curve)
        if not include_curve:
            data.pop("curve", None)
        return data
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"today energy unavailable: {e}")


@router.get("/summary")
async def energy_summary(days: int = 7):
    try:
        return {"days": await asyncio.to_thread(service.recent_summary, days)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"energy summary unavailable: {e}")


@router.get("/ev")
async def energy_ev():
    """Planned + recent completed Intelligent Go EV charge dispatches."""
    from domains.energy import dispatches
    try:
        return await asyncio.to_thread(dispatches.get_dispatches)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"dispatches unavailable: {e}")


@router.get("/events")
async def energy_events(hours: int = 24):
    """Detected appliance events (kettle/oven/EV/spikes)."""
    from datetime import datetime, timedelta, timezone
    import httpx
    from domains.energy.config import SUPABASE_KEY, SUPABASE_URL
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    try:
        resp = await asyncio.to_thread(
            httpx.get, f"{SUPABASE_URL}/rest/v1/energy_events",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"select": "started_at,ended_at,event_type,avg_demand_w,peak_demand_w,energy_kwh,cost_pence,detail",
                    "started_at": f"gte.{since}", "order": "started_at.desc"},
            timeout=15,
        )
        return {"events": resp.json()}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"events unavailable: {e}")
