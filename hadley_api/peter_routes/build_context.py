"""Shared context builder for Peter channels.

Channels (peter-channel, whatsapp-channel) and scheduler.py POST here before
pushing into a Claude Code session. Mirrors the work done inline in
`router_v2.handle_message` so the channel path has feature parity with the
v2 fallback path.

Bundles:
- Channel isolation header
- Current UK time
- Second Brain surfacing (semantic search + decay + access boost)
- Japan trip context (WhatsApp during Apr 3-19, 2026)
- Pending actions block (WhatsApp confirm/cancel flows)
- Attachment block with Read-tool guidance
- The original user message

Background: `bot.py:797` and `whatsapp_webhook.py:99-102` route channel
traffic past `router_v2`, so anything that lives only in
`memory.build_full_context` was silently bypassed. This endpoint is the
shared single source of truth.

Drift warning: the parallel implementation in `domains/peterbot/memory.py`
(`build_full_context`) is still the codepath used by router_v2 itself.
Changes here should be mirrored there (and vice versa) until v2 is also
refactored to call this endpoint.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from zoneinfo import ZoneInfo

from hadley_api.auth import require_auth
from logger import logger

router = APIRouter(prefix="/peter", tags=["peter"])

UK_TZ = ZoneInfo("Europe/London")


class BuildContextRequest(BaseModel):
    message: str
    # Channel ID kept as string: Discord snowflakes exceed JS Number safe
    # range, so the TS callers pass them raw. Python code that needs an
    # int can int(body.channel_id) — Python has arbitrary precision.
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None
    sender_number: Optional[str] = None
    is_whatsapp: bool = False
    attachment_urls: Optional[list[dict]] = None
    include_surfacing: bool = True


class BuildContextResponse(BaseModel):
    context: str
    surfaced_count: int
    blocks: list[str]


@router.post(
    "/build-context",
    response_model=BuildContextResponse,
    dependencies=[Depends(require_auth)],
)
async def build_context(body: BuildContextRequest) -> BuildContextResponse:
    """Build the full context block a channel should push into its Claude session."""
    parts: list[str] = []
    blocks: list[str] = []
    surfaced_count = 0

    channel_name = body.channel_name or (
        "WhatsApp" if body.is_whatsapp else (f"Channel {body.channel_id}" if body.channel_id else "unknown")
    )

    # 1. Channel isolation
    parts.append("# CHANNEL CONTEXT")
    parts.append(f"**Active Channel:** {channel_name}")
    parts.append("You are responding to a message in THIS channel only.")
    parts.append("Do NOT reference conversations or context from other channels.")
    parts.append("")
    blocks.append("channel_isolation")

    # 2. Current UK time
    now = datetime.now(UK_TZ)
    parts.append("## Current Time")
    parts.append(f"{now.strftime('%A, %B %d, %Y at %H:%M')} (UK)")
    parts.append("")
    blocks.append("current_time")

    # 3. Japan trip context (WhatsApp only, trip window only)
    if body.is_whatsapp:
        try:
            from domains.peterbot.japan_context import get_japan_context
            japan_ctx = get_japan_context()
            if japan_ctx:
                parts.append(japan_ctx)
                parts.append("")
                blocks.append("japan_context")
        except Exception as e:
            logger.debug(f"Japan context fetch failed: {e}")

    # 4. Pending actions (WhatsApp + sender_number)
    if body.is_whatsapp and body.sender_number:
        try:
            from domains.peterbot.pending_actions import get_pending_for_sender
            pending = get_pending_for_sender(str(body.sender_number))
            if pending:
                parts.append("## PENDING CONFIRMATION")
                parts.append("The user has a pending action awaiting their response:")
                for p in pending:
                    parts.append(f"- **{p['description']}** (ID: `{p['id']}`)")
                parts.append("")
                parts.append("If user says yes/confirm/go ahead -> `curl -s -X POST http://172.19.64.1:8100/schedule/pending-actions/{id}/confirm`")
                parts.append("If user says no/cancel/never mind -> `curl -s -X POST http://172.19.64.1:8100/schedule/pending-actions/{id}/cancel`")
                parts.append("")
                blocks.append("pending_actions")
        except Exception as e:
            logger.debug(f"Pending actions fetch failed: {e}")

    # 5. Second Brain surfacing
    if body.include_surfacing and body.message and len(body.message.strip()) >= 10:
        try:
            from domains.second_brain.surfacing import get_context_for_message
            knowledge_context = await get_context_for_message(body.message)
            if knowledge_context and knowledge_context.strip():
                parts.append(knowledge_context.strip())
                parts.append("")
                blocks.append("surfacing")
                # Count surfaced items by looking for ### headers in the formatted block
                surfaced_count = knowledge_context.count("\n### ")
        except Exception as e:
            logger.debug(f"Surfacing fetch failed: {e}")

    # 6. Current message (with Windows/WSL media-path scrub via memory helper)
    try:
        from domains.peterbot.memory import _scrub_windows_media_paths
        cleaned_message = _scrub_windows_media_paths(body.message)
    except Exception:
        cleaned_message = body.message
    parts.append("## Current Message")
    parts.append(cleaned_message)
    blocks.append("message")

    # 7. Attachments
    if body.attachment_urls:
        parts.append("")
        parts.append("## Attachments")
        for att in body.attachment_urls:
            is_image = att.get("content_type", "").startswith("image/")
            if is_image:
                path = att.get("local_path") or att.get("url", "")
                parts.append(
                    f"- **Image:** `{att.get('filename', 'image')}` - Use the Read tool on this path to view: {path}"
                )
            else:
                parts.append(
                    f"- **File:** `{att.get('filename', 'file')}` ({att.get('content_type', 'unknown')}) - {att.get('url', '')}"
                )
        if any(a.get("content_type", "").startswith("image/") for a in body.attachment_urls):
            parts.append("")
            parts.append(
                "**IMPORTANT:** The user sent image(s). Use the Read tool with the path above to see the image content."
            )
        blocks.append("attachments")

    return BuildContextResponse(
        context="\n".join(parts),
        surfaced_count=surfaced_count,
        blocks=blocks,
    )
