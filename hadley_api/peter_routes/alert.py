"""Generic #alerts posting endpoint.

Peter's channel sessions have no direct way to reach the #alerts Discord
channel mid-conversation — scheduled jobs post to the channel their
SCHEDULE.md row defines, and the alerts webhook URL is a Windows-side
secret. This endpoint lets any Peter session surface an operational
problem (e.g. a claude.ai MCP connector with an expired token) the moment
it is encountered, instead of silently degrading the answer.

Throttled per (source, message) so a repeated failure doesn't flood the
channel: identical alerts within the throttle window return
``{"status": "throttled"}`` and are not re-posted.
"""

from __future__ import annotations

import os
import time

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from hadley_api.auth import require_auth
from logger import logger

router = APIRouter(tags=["peter"])

DEFAULT_THROTTLE_MINUTES = 60

# (source, message) -> last posted epoch seconds
_recent: dict[tuple[str, str], float] = {}


class AlertRequest(BaseModel):
    message: str
    source: str = "peter"
    throttle_minutes: int = DEFAULT_THROTTLE_MINUTES


@router.post("/alert", dependencies=[Depends(require_auth)])
async def post_alert(body: AlertRequest):
    """Post a one-line alert to the #alerts Discord channel (throttled)."""
    webhook = os.environ.get("DISCORD_WEBHOOK_ALERTS", "")
    if not webhook:
        return {"status": "error", "error": "DISCORD_WEBHOOK_ALERTS not configured"}

    key = (body.source, body.message.strip())
    now = time.time()
    last = _recent.get(key, 0.0)
    throttle_secs = max(0, body.throttle_minutes) * 60
    if throttle_secs and now - last < throttle_secs:
        return {"status": "throttled", "retry_after_secs": int(throttle_secs - (now - last))}

    content = f"⚠️ **{body.source}**: {body.message}"[:1900]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook, json={"content": content})
            resp.raise_for_status()
    except Exception as e:
        logger.warning(f"/alert webhook post failed: {e}")
        return {"status": "error", "error": str(e)}

    _recent[key] = now
    return {"status": "posted"}
