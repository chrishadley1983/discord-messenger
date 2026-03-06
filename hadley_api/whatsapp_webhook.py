"""WhatsApp webhook receiver for Evolution API.

Receives incoming WhatsApp messages and forwards them to the DiscordBot's
internal server (port 8101) for Peter to process.

Uses a debounce queue per sender: messages are buffered for 3 seconds after
the last message arrives, then batched into a single payload. This prevents
Peter from responding to the first message before follow-ups arrive.

Evolution API sends webhooks for:
- MESSAGES_UPSERT: new incoming/outgoing messages
- CONNECTION_UPDATE: connection state changes
"""
import asyncio
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# --- Deduplication: track recently seen message IDs ---
# Evolution API can fire messages.upsert multiple times for the same message
_seen_message_ids: OrderedDict[str, float] = OrderedDict()
_SEEN_MAX_SIZE = 200
_SEEN_TTL_SECONDS = 300  # 5 minutes

# --- Debounce queues: batch rapid messages from the same sender ---
_DEBOUNCE_SECONDS = 3.0
_MAX_QUEUE_DEPTH = 5
_IDLE_CLEANUP_SECONDS = 60


@dataclass
class _SenderQueue:
    """Per-sender message queue with debounce timer."""
    messages: list[dict] = field(default_factory=list)
    timer_task: asyncio.Task | None = None
    last_activity: float = 0.0
    # Keep sender metadata from first message
    sender_name: str = ""
    sender_number: str = ""
    reply_to: str = ""
    is_group: bool = False


_sender_queues: dict[str, _SenderQueue] = {}


def _is_duplicate(message_id: str) -> bool:
    """Check if we've already processed this message ID. Thread-safe for asyncio."""
    now = time.monotonic()

    # Evict expired entries
    while _seen_message_ids:
        oldest_id, oldest_time = next(iter(_seen_message_ids.items()))
        if now - oldest_time > _SEEN_TTL_SECONDS:
            _seen_message_ids.pop(oldest_id)
        else:
            break

    if message_id in _seen_message_ids:
        return True

    _seen_message_ids[message_id] = now

    # Cap size
    while len(_seen_message_ids) > _SEEN_MAX_SIZE:
        _seen_message_ids.popitem(last=False)

    return False


router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

# Allowed senders — match by pushName (Evolution API uses LIDs, not phone numbers)
# Maps pushName -> (display_name, phone_number for replies)
ALLOWED_SENDERS_BY_NAME = {
    "Chris Hadley": ("Chris", "447855620978"),
    "Abby Hadley": ("Abby", "447856182831"),
}

# Also match by phone number (for webhooks that do use phone-based JIDs)
ALLOWED_SENDERS_BY_NUMBER = {
    "447855620978": ("Chris", "447855620978"),
    "447856182831": ("Abby", "447856182831"),
}

# DiscordBot internal server for WhatsApp message routing
DISCORDBOT_WHATSAPP_URL = "http://127.0.0.1:8101/whatsapp/message"


@router.post("/webhook")
@router.post("/webhook/{event_type:path}")
async def whatsapp_webhook(request: Request, event_type: str = ""):
    """Receive Evolution API webhook events and forward messages to DiscordBot."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    event = body.get("event")

    if event == "messages.upsert":
        await _handle_message(body)
    elif event == "connection.update":
        _handle_connection_update(body)

    return JSONResponse({"status": "ok"})


async def _handle_message(body: dict):
    """Process an incoming message webhook — queue it for debounced delivery."""
    data = body.get("data", {})
    messages = data if isinstance(data, list) else [data]

    for msg in messages:
        key = msg.get("key", {})

        if key.get("fromMe"):
            return

        # Deduplicate — Evolution API can fire messages.upsert multiple times
        message_id = key.get("id", "")
        if message_id and _is_duplicate(message_id):
            logger.debug(f"WhatsApp duplicate skipped: {message_id}")
            return

        remote_jid = key.get("remoteJid", "")
        is_group = remote_jid.endswith("@g.us")

        # Identify sender — try pushName first (handles LID-based JIDs),
        # then fall back to participant (groups) or jid_number (DMs)
        push_name = msg.get("pushName", "")
        participant = key.get("participant", "")
        participant_number = participant.split("@")[0] if "@" in participant else ""
        jid_number = remote_jid.split("@")[0] if "@" in remote_jid else remote_jid

        sender_info = (
            ALLOWED_SENDERS_BY_NAME.get(push_name)
            or ALLOWED_SENDERS_BY_NUMBER.get(participant_number)
            or ALLOWED_SENDERS_BY_NUMBER.get(jid_number)
        )
        if not sender_info:
            return

        sender_name, sender_number = sender_info

        # Reply destination: group JID for group messages, sender number for DMs
        reply_to = remote_jid if is_group else sender_number

        message_content = msg.get("message", {})
        text = (
            message_content.get("conversation")
            or message_content.get("extendedTextMessage", {}).get("text")
            or ""
        )

        if not text.strip():
            return

        logger.info(f"WhatsApp from {sender_name} ({'group' if is_group else 'DM'}): {text[:100]}")

        # Queue the message for debounced delivery
        await _enqueue_message(
            sender_name=sender_name,
            sender_number=sender_number,
            reply_to=reply_to,
            is_group=is_group,
            text=text.strip(),
        )


async def _enqueue_message(
    sender_name: str,
    sender_number: str,
    reply_to: str,
    is_group: bool,
    text: str,
):
    """Add a message to the sender's debounce queue and reset the timer."""
    queue = _sender_queues.get(sender_number)

    if queue is None:
        queue = _SenderQueue(
            sender_name=sender_name,
            sender_number=sender_number,
            reply_to=reply_to,
            is_group=is_group,
        )
        _sender_queues[sender_number] = queue

    # Cap queue depth
    if len(queue.messages) >= _MAX_QUEUE_DEPTH:
        logger.warning(f"WhatsApp queue full for {sender_name}, dropping oldest")
        queue.messages.pop(0)

    queue.messages.append({"text": text})
    queue.last_activity = time.monotonic()

    # Cancel existing timer and start a new one (debounce reset)
    if queue.timer_task and not queue.timer_task.done():
        queue.timer_task.cancel()

    queue.timer_task = asyncio.create_task(_debounce_flush(sender_number))


async def _debounce_flush(sender_number: str):
    """Wait for the debounce window, then flush all queued messages as one payload."""
    await asyncio.sleep(_DEBOUNCE_SECONDS)

    queue = _sender_queues.get(sender_number)
    if not queue or not queue.messages:
        return

    # Collect all queued texts into a single payload
    texts = [m["text"] for m in queue.messages]
    combined_text = "\n".join(texts)
    msg_count = len(texts)

    # Clear the queue
    queue.messages.clear()
    queue.timer_task = None

    logger.info(
        f"WhatsApp debounce flush for {queue.sender_name}: "
        f"{msg_count} message(s) batched"
    )

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                DISCORDBOT_WHATSAPP_URL,
                json={
                    "sender_name": queue.sender_name,
                    "sender_number": queue.sender_number,
                    "reply_to": queue.reply_to,
                    "is_group": queue.is_group,
                    "text": combined_text,
                },
                timeout=600,
            )
            logger.info(f"WhatsApp forward to Peter: {resp.status_code}")
    except Exception as e:
        logger.error(f"WhatsApp forward failed: {e}")

    # Schedule cleanup of idle sender queues
    asyncio.create_task(_cleanup_idle_queue(sender_number))


async def _cleanup_idle_queue(sender_number: str):
    """Remove sender queue after it's been idle for a while."""
    await asyncio.sleep(_IDLE_CLEANUP_SECONDS)
    queue = _sender_queues.get(sender_number)
    if queue and not queue.messages and time.monotonic() - queue.last_activity > _IDLE_CLEANUP_SECONDS:
        del _sender_queues[sender_number]


def _handle_connection_update(body: dict):
    """Log connection state changes."""
    data = body.get("data", {})
    state = data.get("state", "unknown")
    logger.info(f"WhatsApp connection update: {state}")

    if state == "close":
        logger.warning("WhatsApp disconnected — may need QR code re-scan")
