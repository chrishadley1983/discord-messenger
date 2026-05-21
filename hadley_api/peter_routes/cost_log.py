"""Channel cost-logging endpoint.

The router_v2 path logs every CLI invocation to `data/cli_costs.jsonl` with
USD/GBP cost, model, duration, tools used (see `router_v2._log_cost`). When
messages flow through the channel path instead, none of that gets recorded
because the channel session is a long-running Claude Code process and we
don't have per-turn cost data.

This endpoint accepts best-effort observations from channel reply tools so
the dashboard at least shows traffic volume and duration. Cost fields are
optional and zero by default — we record what we can.

Format matches the existing JSONL schema so the existing cost analyser keeps
working without changes.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from domains.peterbot.config import USD_TO_GBP
from hadley_api.auth import require_auth
from logger import logger

router = APIRouter(prefix="/response", tags=["peter"])

COST_LOG_PATH = Path(__file__).resolve().parents[2] / "data" / "cli_costs.jsonl"


class CostLogRequest(BaseModel):
    source: str  # e.g. "channel:peter", "channel:whatsapp", "channel:jobs"
    channel: Optional[str] = None  # Discord channel name or "WhatsApp"
    message_preview: Optional[str] = ""
    duration_ms: Optional[float] = 0.0
    response_chars: Optional[int] = 0
    cost_usd: Optional[float] = 0.0
    model: Optional[str] = ""
    num_turns: Optional[int] = 0
    tools_used: Optional[list[str]] = None


@router.post("/cost", dependencies=[Depends(require_auth)])
async def log_cost(body: CostLogRequest):
    """Append a cost/volume entry to cli_costs.jsonl from a channel."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "source": body.source,
        "channel": body.channel or "",
        "message": (body.message_preview or "")[:80],
        "cost_usd": round(float(body.cost_usd or 0.0), 6),
        "cost_gbp": round(float(body.cost_usd or 0.0) * USD_TO_GBP, 6),
        "model": body.model or "",
        "duration_ms": round(float(body.duration_ms or 0.0), 1),
        "num_turns": int(body.num_turns or 0),
        "tools_used": body.tools_used or [],
        "response_chars": int(body.response_chars or 0),
    }
    try:
        COST_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(COST_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.debug(f"Cost log write failed: {e}")
        return {"status": "error", "error": str(e)}
    return {"status": "logged"}
