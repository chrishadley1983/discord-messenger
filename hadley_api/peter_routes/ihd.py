"""Peter access to the IHD (in-home display) + Pi capabilities.

Thin proxy over the running IHD app (192.168.0.110:3000) so Peter can read and
control the home dashboard's devices: smart plug, kids' pocket money, dad jokes,
Tamagotchi pets, media/TV, the screen, and the homework/spellings summary.

Read endpoints are open (LAN-trusted, read-only); mutating endpoints require the
x-api-key header (require_auth), matching the rest of the Hadley API. See
domains.ihd.service. Temperature/humidity live + trends live under /home/sensors.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from domains.ihd import service
from hadley_api.auth import require_auth

router = APIRouter(prefix="/ihd", tags=["ihd"])


# ---------------------------------------------------------------- Smart plug
@router.get("/plug")
async def plug():
    """Smart plug state (ON/OFF), link quality, friendly name."""
    try:
        return await asyncio.to_thread(service.plug_status)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"plug unavailable: {e}")


class PlugSet(BaseModel):
    state: str  # "ON" | "OFF" (case-insensitive)


@router.post("/plug", dependencies=[Depends(require_auth)])
async def plug_set(body: PlugSet):
    """Turn the smart plug ON or OFF."""
    on = body.state.strip().upper() == "ON"
    try:
        return await asyncio.to_thread(service.plug_set, on)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"plug control failed: {e}")


# ------------------------------------------------------------- Pocket money
@router.get("/pocket-money")
async def pocket_money(full: bool = False):
    """Balances summary (default) or full balances + transactions (full=true). Pence."""
    try:
        fn = service.pocket_money_full if full else service.pocket_money_summary
        return await asyncio.to_thread(fn)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"pocket money unavailable: {e}")


class PocketMoneyAdd(BaseModel):
    child: str            # "emmie" | "max"
    amount_pence: int     # positive credit / negative debit
    description: str = ""
    category: str = "pocket_money"


@router.post("/pocket-money", dependencies=[Depends(require_auth)])
async def pocket_money_add(body: PocketMoneyAdd):
    """Credit (+) or debit (-) a child's balance, in pence."""
    if body.child not in ("emmie", "max"):
        raise HTTPException(status_code=400, detail="child must be 'emmie' or 'max'")
    if body.amount_pence == 0:
        raise HTTPException(status_code=400, detail="amount_pence must be non-zero")
    try:
        return await asyncio.to_thread(
            service.pocket_money_add, body.child, body.amount_pence,
            body.description, body.category)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"pocket money update failed: {e}")


@router.get("/pocket-money/grid")
async def pocket_money_grid(week: str | None = None):
    """Weekly chore grid (week=YYYY-MM-DD Monday; defaults to current week)."""
    try:
        return await asyncio.to_thread(service.pocket_money_grid, week)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"pocket money grid unavailable: {e}")


@router.get("/pocket-money/calculate")
async def pocket_money_calculate(week: str | None = None):
    """Computed pocket-money totals from the chore grid (formatted message + per-child)."""
    try:
        return await asyncio.to_thread(service.pocket_money_calculate, week)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"pocket money calc unavailable: {e}")


# -------------------------------------------------------------- Dad jokes
@router.get("/jokes")
async def jokes():
    """Today's dad jokes (the 'Peter says...' card on the kids screen)."""
    try:
        return await asyncio.to_thread(service.jokes)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"jokes unavailable: {e}")


class JokeAdd(BaseModel):
    text: str


@router.post("/jokes", dependencies=[Depends(require_auth)])
async def jokes_add(body: JokeAdd):
    """Add a dad joke to today's rotation on the kids screen."""
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="joke text required")
    try:
        return await asyncio.to_thread(service.jokes_add, body.text.strip())
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"joke add failed: {e}")


# ------------------------------------------------------------------- Pets
@router.get("/pets")
async def pets():
    """Tamagotchi pet status for max + emmie (hunger/happiness/cleanliness, stage)."""
    try:
        return await asyncio.to_thread(service.pets)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"pets unavailable: {e}")


# ------------------------------------------------- Kids homework / spellings
@router.get("/kids")
async def kids():
    """Homework/spellings/11PlusMate summary for Emmie + Max."""
    try:
        return await asyncio.to_thread(service.kids_summary)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"kids summary unavailable: {e}")


# -------------------------------------------------------------- Media / TV
class MediaControl(BaseModel):
    action: str             # "launch" | "close"
    app: str | None = None  # "netflix" | "youtube" | "nowtv"


@router.post("/media", dependencies=[Depends(require_auth)])
async def media(body: MediaControl):
    """Launch or close streaming (Netflix/YouTube/NowTV) on the kitchen screen."""
    if body.action not in ("launch", "close"):
        raise HTTPException(status_code=400, detail="action must be 'launch' or 'close'")
    app = (body.app or "").lower() or None
    if body.action == "launch" and app not in ("netflix", "youtube", "nowtv"):
        raise HTTPException(status_code=400, detail="app must be netflix|youtube|nowtv")
    try:
        return await asyncio.to_thread(service.media, body.action, app)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"media control failed: {e}")


# ----------------------------------------------------------------- Screen
@router.get("/screen")
async def screen():
    """Display state: on/off, idle seconds, night mode."""
    try:
        return await asyncio.to_thread(service.screen_status)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"screen unavailable: {e}")


@router.post("/screen/wake", dependencies=[Depends(require_auth)])
async def screen_wake():
    """Wake the kitchen display (simulated motion event)."""
    try:
        return await asyncio.to_thread(service.screen_wake)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"screen wake failed: {e}")
