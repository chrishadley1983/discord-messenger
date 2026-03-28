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
import base64
import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass, field

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from hadley_api.auth import require_auth

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

# WhatsApp message routing — channel mode or bot.py handler
_WHATSAPP_USE_CHANNEL = os.getenv("WHATSAPP_USE_CHANNEL", "0") == "1"
DISCORDBOT_WHATSAPP_URL = (
    "http://127.0.0.1:8102/whatsapp/message"   # Channel MCP server
    if _WHATSAPP_USE_CHANNEL else
    "http://127.0.0.1:8101/whatsapp/message"    # bot.py handler (original)
)

# Evolution API config (for media download)
EVOLUTION_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8085")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "peter-whatsapp-2026-hadley")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "peter-whatsapp")


async def _download_media(message_key: dict) -> str | None:
    """Download media (image/video/doc) from an Evolution API message, return base64 string.

    Args:
        message_key: Full message key dict with id, remoteJid, and fromMe fields.
    """
    url = f"{EVOLUTION_URL}/chat/getBase64FromMediaMessage/{EVOLUTION_INSTANCE}"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={
                    "apikey": EVOLUTION_API_KEY,
                    "Content-Type": "application/json",
                },
                json={"message": {"key": message_key}, "convertToMp4": False},
                timeout=30,
            )
            if resp.status_code not in (200, 201):
                logger.error(f"Media download failed ({resp.status_code}): {resp.text[:200]}")
                return None
            data = resp.json()
            b64 = data.get("base64", "")
            if not b64:
                logger.error("Media download: empty base64")
                return None
            return b64
    except Exception as e:
        logger.error(f"Media download error: {e}")
        return None


async def _download_audio(message_key: dict) -> bytes | None:
    """Download audio from an Evolution API message via getBase64FromMediaMessage."""
    url = f"{EVOLUTION_URL}/chat/getBase64FromMediaMessage/{EVOLUTION_INSTANCE}"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={
                    "apikey": EVOLUTION_API_KEY,
                    "Content-Type": "application/json",
                },
                json={"message": {"key": message_key}, "convertToMp4": False},
                timeout=30,
            )
            if resp.status_code not in (200, 201):
                logger.error(f"Audio download failed ({resp.status_code}): {resp.text[:200]}")
                return None
            data = resp.json()
            b64 = data.get("base64", "")
            if not b64:
                logger.error("Audio download: empty base64")
                return None
            return base64.b64decode(b64)
    except Exception as e:
        logger.error(f"Audio download error: {e}")
        return None


def _resolve_recipient(to: str) -> str | None:
    """Resolve a recipient to a phone number or group JID.

    Accepts: contact name ("chris"), phone number ("447855620978"),
    group name ("extended-team"), or group JID ("...@g.us").
    Returns None if the recipient is not in the known allowlist.
    """
    from integrations.whatsapp import CONTACTS, GROUPS

    to_lower = to.lower().strip()

    # 1. Friendly name lookup
    if to_lower in CONTACTS:
        return CONTACTS[to_lower]
    if to_lower in GROUPS:
        return GROUPS[to_lower]

    # 2. Raw phone number — accept if it's a known contact's number
    known_numbers = set(CONTACTS.values())
    if to in known_numbers:
        return to

    # 3. Raw group JID — accept if it's a known group's JID
    known_jids = set(GROUPS.values())
    if to in known_jids:
        return to

    return None


# ---------------------------------------------------------------------------
# Recipient management — add/remove groups and contacts (admin-gated)
# ---------------------------------------------------------------------------

@router.get("/recipients")
async def list_recipients():
    """List all known contacts and groups."""
    from integrations.whatsapp import CONTACTS, GROUPS
    return {"contacts": CONTACTS, "groups": GROUPS}


@router.post("/recipients/groups", dependencies=[Depends(require_auth)])
async def add_group(name: str, jid: str):
    """Add a WhatsApp group to the known recipients list.

    Args:
        name: Friendly name for the group (e.g. "family-chat")
        jid: WhatsApp group JID (e.g. "120363424758610750@g.us")
    """
    from integrations.whatsapp import CONTACTS, GROUPS, _save_recipients, reload_recipients

    if not jid.endswith("@g.us"):
        return JSONResponse({"error": "Group JID must end with @g.us"}, status_code=400)

    name_lower = name.lower().strip()
    if not name_lower:
        return JSONResponse({"error": "Group name cannot be empty"}, status_code=400)

    GROUPS[name_lower] = jid
    _save_recipients(CONTACTS, GROUPS)
    reload_recipients()
    return {"status": "added", "name": name_lower, "jid": jid, "groups": GROUPS}


@router.delete("/recipients/groups/{name}", dependencies=[Depends(require_auth)])
async def remove_group(name: str):
    """Remove a WhatsApp group from the known recipients list."""
    from integrations.whatsapp import CONTACTS, GROUPS, _save_recipients, reload_recipients

    name_lower = name.lower().strip()
    if name_lower not in GROUPS:
        return JSONResponse({"error": f"Group '{name}' not found"}, status_code=404)

    removed_jid = GROUPS.pop(name_lower)
    _save_recipients(CONTACTS, GROUPS)
    reload_recipients()
    return {"status": "removed", "name": name_lower, "jid": removed_jid, "groups": GROUPS}


@router.post("/send", dependencies=[Depends(require_auth)])
async def whatsapp_send(to: str, message: str):
    """Send a WhatsApp text message via Evolution API.

    Args:
        to: Contact name, phone number, group name, or group JID
        message: Message text (Discord markdown auto-converted to WhatsApp format)
    """
    from integrations.whatsapp import send_text, CONTACTS, GROUPS

    # Resolve recipient — reject unknown
    number = _resolve_recipient(to)
    if not number:
        return JSONResponse(
            {"error": f"Unknown recipient '{to}'. Allowed: {list(CONTACTS.keys()) + list(GROUPS.keys())}"},
            status_code=400,
        )

    try:
        result = await send_text(number, message)
        if "error" in result:
            return JSONResponse(
                {"error": result["error"], "status": result.get("status", 500)},
                status_code=result.get("status", 500),
            )
        return JSONResponse({"status": "sent", "to": number})
    except Exception as e:
        logger.error(f"WhatsApp send API error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/status")
async def whatsapp_status():
    """Check WhatsApp connection status via Evolution API."""
    from integrations.whatsapp import check_connection

    try:
        result = await check_connection()
        if "error" in result:
            return JSONResponse({"connected": False, "error": result["error"]})
        state = result.get("instance", {}).get("state", "unknown")
        return JSONResponse({"connected": state == "open", "state": state})
    except Exception as e:
        logger.error(f"WhatsApp status check error: {e}")
        return JSONResponse({"connected": False, "error": str(e)})


@router.post("/send-voice", dependencies=[Depends(require_auth)])
async def whatsapp_send_voice(to: str, message: str):
    """Send a WhatsApp voice note generated from text via TTS.

    Also sends the text as a regular message alongside the voice note.

    Args:
        to: Contact name (chris, abby) or group JID
        message: Text to convert to speech and send as voice note
    """
    from integrations.whatsapp import send_text, send_audio, CONTACTS, GROUPS

    # Resolve recipient — reject unknown
    number = _resolve_recipient(to)
    if not number:
        return JSONResponse(
            {"error": f"Unknown recipient '{to}'. Allowed: {list(CONTACTS.keys()) + list(GROUPS.keys())}"},
            status_code=400,
        )

    # Send text message first
    try:
        text_result = await send_text(number, message)
        if "error" in text_result:
            return JSONResponse(
                {"error": f"Text send failed: {text_result['error']}"},
                status_code=text_result.get("status", 500),
            )
    except Exception as e:
        logger.error(f"WhatsApp send-voice text error: {e}")
        return JSONResponse({"error": f"Text send failed: {e}"}, status_code=500)

    # Generate voice note via TTS
    try:
        from hadley_api.voice_engine import synthesise
        wav_bytes = await synthesise(message)
        audio_b64 = base64.b64encode(wav_bytes).decode()
    except Exception as e:
        logger.error(f"WhatsApp send-voice TTS error: {e}")
        return JSONResponse(
            {"status": "partial", "text_sent": True, "voice_error": str(e)},
            status_code=207,
        )

    # Send voice note
    try:
        audio_result = await send_audio(number, audio_b64)
        if "error" in audio_result:
            return JSONResponse(
                {"status": "partial", "text_sent": True, "voice_error": audio_result["error"]},
                status_code=207,
            )
        return JSONResponse({"status": "sent", "to": number, "text_sent": True, "voice_sent": True})
    except Exception as e:
        logger.error(f"WhatsApp send-voice audio error: {e}")
        return JSONResponse(
            {"status": "partial", "text_sent": True, "voice_error": str(e)},
            status_code=207,
        )


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

        # Check for voice note / audio message
        audio_msg = message_content.get("audioMessage")
        if audio_msg:
            logger.info(f"WhatsApp voice note from {sender_name} ({audio_msg.get('seconds', '?')}s)")
            await _handle_voice_note(
                message_key=key,
                message_content=message_content,
                sender_name=sender_name,
                sender_number=sender_number,
                reply_to=reply_to,
                is_group=is_group,
            )
            return

        # Check for location message (Feature #3: Location-Aware Food Finder)
        location_msg = message_content.get("locationMessage")
        if location_msg:
            lat = location_msg.get("degreesLatitude")
            lng = location_msg.get("degreesLongitude")
            if lat and lng:
                logger.info(f"WhatsApp location from {sender_name}: {lat}, {lng}")
                text = f"[Location shared: {lat}, {lng}] Find me the nearest food options from my current location. I'm at coordinates {lat}, {lng}."
                await _enqueue_message(
                    sender_name=sender_name,
                    sender_number=sender_number,
                    reply_to=reply_to,
                    is_group=is_group,
                    text=text,
                )
                return

        # Check for image message
        image_msg = message_content.get("imageMessage")
        if image_msg:
            caption = image_msg.get("caption", "")
            logger.info(f"WhatsApp image from {sender_name}: caption='{caption[:50]}'")

            # --- jd/ photo: save directly to photo book ---
            if caption.strip().startswith("jd/") or caption.strip().startswith("/jd"):
                try:
                    base64_data = image_msg.get("base64")
                    if not base64_data:
                        base64_data = await _download_media(key)
                    if base64_data:
                        import base64 as b64
                        from pathlib import Path
                        import uuid
                        img_dir = Path(__file__).parent.parent / "data" / "tmp" / "whatsapp_images"
                        img_dir.mkdir(parents=True, exist_ok=True)
                        ext = "jpg" if "jpeg" in image_msg.get("mimetype", "jpeg") else "png"
                        img_path = img_dir / f"{uuid.uuid4().hex[:12]}.{ext}"
                        img_path.write_bytes(b64.b64decode(base64_data))
                        c = caption.strip()
                        photo_caption = (c[3:] if c.startswith("jd/") or c.startswith("/jd") else c).strip()
                        await _handle_jd_photo(
                            local_path=str(img_path),
                            caption=photo_caption,
                            sender_name=sender_name,
                            reply_to=reply_to,
                        )
                    else:
                        from integrations.whatsapp import send_text
                        await send_text(reply_to, "❌ Couldn't download that image — try again?")
                except Exception as e:
                    logger.error(f"jd/ photo handling failed: {e}")
                    from integrations.whatsapp import send_text
                    await send_text(reply_to, f"❌ Photo save failed: {e}")
                return

            try:
                # Download image via Evolution API
                base64_data = image_msg.get("base64")
                if not base64_data:
                    base64_data = await _download_media(key)
                img_path = None
                if base64_data:
                    import base64 as b64
                    from pathlib import Path
                    import uuid
                    img_dir = Path(__file__).parent.parent / "data" / "tmp" / "whatsapp_images"
                    img_dir.mkdir(parents=True, exist_ok=True)
                    ext = "jpg" if "jpeg" in image_msg.get("mimetype", "jpeg") else "png"
                    img_path = img_dir / f"{uuid.uuid4().hex[:12]}.{ext}"
                    img_path.write_bytes(b64.b64decode(base64_data))

                # Build message text — always forward, even if image download failed
                if img_path:
                    text = f"[Photo shared] Image saved at {img_path}"
                    if caption:
                        text += f"\nMessage: {caption}"
                else:
                    text = f"[Photo shared — image could not be downloaded]"
                    if caption:
                        text += f"\nMessage: {caption}"
                    else:
                        text += "\n(No caption provided)"
                await _enqueue_message(
                    sender_name=sender_name,
                    sender_number=sender_number,
                    reply_to=reply_to,
                    is_group=is_group,
                    text=text,
                )
                return
            except Exception as e:
                logger.error(f"WhatsApp image handling failed: {e}")
                # Still try to forward the caption if we have one
                if caption:
                    await _enqueue_message(
                        sender_name=sender_name,
                        sender_number=sender_number,
                        reply_to=reply_to,
                        is_group=is_group,
                        text=f"[Photo shared — processing failed] {caption}",
                    )
                    return

        # Check for document message (WhatsApp sends images as documents sometimes)
        doc_msg = message_content.get("documentMessage")
        if doc_msg:
            mimetype = doc_msg.get("mimetype", "")
            caption = doc_msg.get("caption") or doc_msg.get("fileName", "")
            logger.info(f"WhatsApp document from {sender_name}: mimetype={mimetype}, caption='{caption[:50]}'")

            try:
                base64_data = doc_msg.get("base64")
                if not base64_data:
                    base64_data = await _download_media(key)
                img_path = None
                if base64_data and mimetype.startswith("image/"):
                    import base64 as b64
                    from pathlib import Path
                    import uuid
                    img_dir = Path(__file__).parent.parent / "data" / "tmp" / "whatsapp_images"
                    img_dir.mkdir(parents=True, exist_ok=True)
                    ext = mimetype.split("/")[-1].replace("jpeg", "jpg")
                    img_path = img_dir / f"{uuid.uuid4().hex[:12]}.{ext}"
                    img_path.write_bytes(b64.b64decode(base64_data))

                if img_path:
                    text = f"[Photo shared] Image saved at {img_path}"
                    if caption:
                        text += f"\nMessage: {caption}"
                elif mimetype.startswith("image/"):
                    text = f"[Photo shared — image could not be downloaded]"
                    if caption:
                        text += f"\nMessage: {caption}"
                    else:
                        text += "\n(No caption provided)"
                else:
                    text = f"[Document shared: {doc_msg.get('fileName', 'unknown')}]"
                    if caption:
                        text += f"\nMessage: {caption}"
                await _enqueue_message(
                    sender_name=sender_name,
                    sender_number=sender_number,
                    reply_to=reply_to,
                    is_group=is_group,
                    text=text,
                )
                return
            except Exception as e:
                logger.error(f"WhatsApp document handling failed: {e}")

        text = (
            message_content.get("conversation")
            or message_content.get("extendedTextMessage", {}).get("text")
            or ""
        )

        if not text.strip():
            return

        # --- jd/ command: photo book capture (handled directly, no LLM) ---
        stripped = text.strip()
        if stripped.startswith("jd/") or stripped.startswith("/jd"):
            # Normalise: strip the prefix (either "jd/" or "/jd") to get the content
            if stripped.startswith("jd/"):
                jd_content = stripped[3:].strip()
            else:
                jd_content = stripped[3:].strip()
            await _handle_jd_command(
                text="jd/" + jd_content,  # normalise to jd/ prefix
                sender_name=sender_name,
                reply_to=reply_to,
            )
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


async def _handle_jd_command(text: str, sender_name: str, reply_to: str):
    """Handle jd/ text command — save as highlight or diary entry directly."""
    from integrations.whatsapp import send_text

    content = text[3:].strip()  # strip "jd/" prefix
    logger.info(f"jd/ command from {sender_name}: '{content[:80]}' reply_to={reply_to}")

    if not content:
        await send_text(reply_to, "Send jd/ followed by a moment, diary entry, or photo")
        return

    API = "http://127.0.0.1:8100/japan"

    # Count sentences (rough: split on ". " or newlines)
    sentence_count = len([s for s in content.replace("\n", ". ").split(". ") if s.strip()])
    logger.info(f"jd/ classified as {'diary' if sentence_count >= 3 else 'highlight'} ({sentence_count} sentences)")

    try:
        if sentence_count >= 3:
            # Diary entry (longer text)
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{API}/photobook/diary",
                    json={"content": content, "source": "text", "sender": sender_name},
                )
            if resp.status_code in (200, 201):
                data = resp.json()
                word_count = len(content.split())
                await send_text(reply_to, f"📝 Day {data.get('day_number', '?')} — {word_count} words")
            else:
                await send_text(reply_to, f"❌ Save failed: {resp.text[:100]}")
        else:
            # Highlight (short text)
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{API}/photobook/highlight",
                    json={"text": content, "sender": sender_name},
                )
            if resp.status_code in (200, 201):
                data = resp.json()
                await send_text(reply_to, f"✨ Day {data.get('day_number', '?')}")
            else:
                await send_text(reply_to, f"❌ Save failed: {resp.text[:100]}")
    except Exception as e:
        logger.error(f"jd/ command failed: {e}", exc_info=True)
        await send_text(reply_to, f"❌ Error: {e}")

    # Also feed the content into Peter's conversation buffer so he has context
    try:
        from domains.peterbot import memory
        WHATSAPP_VIRTUAL_CHANNEL_ID = 9999999999
        saved_type = "diary" if sentence_count >= 3 else "highlight"
        memory.add_to_buffer("user", f"[{sender_name} saved {saved_type} via jd/]: {content}", WHATSAPP_VIRTUAL_CHANNEL_ID)
    except Exception:
        pass


async def _handle_jd_photo(local_path: str, caption: str, sender_name: str, reply_to: str):
    """Handle jd/ photo — upload to Google Drive + Supabase via photobook API."""
    from integrations.whatsapp import send_text

    API = "http://127.0.0.1:8100/japan"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{API}/photobook/upload",
                json={
                    "local_path": local_path,
                    "caption": caption or "Photo",
                    "sender": sender_name,
                },
            )
        if resp.status_code in (200, 201):
            data = resp.json()
            day = data.get("day_number", "?")
            await send_text(reply_to, f"📸 Day {day}")
            # Feed into Peter's buffer
            try:
                from domains.peterbot import memory
                memory.add_to_buffer("user", f"[{sender_name} saved photo via jd/]: {caption or 'Photo'}", 9999999999)
            except Exception:
                pass
        else:
            await send_text(reply_to, f"❌ Upload failed: {resp.text[:100]}")
    except Exception as e:
        logger.error(f"jd/ photo upload failed: {e}")
        await send_text(reply_to, f"❌ Photo error: {e}")


async def _handle_voice_note(
    message_key: dict,
    message_content: dict,
    sender_name: str,
    sender_number: str,
    reply_to: str,
    is_group: bool,
):
    """Handle an incoming voice note — transcribe and queue as text."""
    # Try base64 from payload first (if webhookBase64 is enabled)
    b64_data = message_content.get("base64")
    if b64_data:
        audio_bytes = base64.b64decode(b64_data)
    else:
        # Download via Evolution API
        audio_bytes = await _download_audio(message_key)

    if not audio_bytes:
        logger.error(f"Could not get audio for voice note {message_id}")
        return

    # Transcribe using voice engine
    try:
        from hadley_api.voice_engine import transcribe
        text = await transcribe(audio_bytes, source_format="ogg")
    except Exception as e:
        logger.error(f"Voice note transcription failed: {e}")
        return

    if not text.strip():
        logger.info("Voice note transcribed to empty text, ignoring")
        return

    logger.info(f"WhatsApp voice from {sender_name}: {text[:100]}")

    # Queue transcribed text with [Voice] tag — goes through normal debounce
    await _enqueue_message(
        sender_name=sender_name,
        sender_number=sender_number,
        reply_to=reply_to,
        is_group=is_group,
        text=text.strip(),
        is_voice=True,
    )


async def _enqueue_message(
    sender_name: str,
    sender_number: str,
    reply_to: str,
    is_group: bool,
    text: str,
    is_voice: bool = False,
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

    queue.messages.append({"text": text, "is_voice": is_voice})
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
    has_voice = any(m.get("is_voice") for m in queue.messages)
    combined_text = "\n".join(texts)
    msg_count = len(texts)

    # Clear the queue
    queue.messages.clear()
    queue.timer_task = None

    logger.info(
        f"WhatsApp debounce flush for {queue.sender_name}: "
        f"{msg_count} message(s) batched{' (voice)' if has_voice else ''}"
    )

    _payload = {
        "sender_name": queue.sender_name,
        "sender_number": queue.sender_number,
        "reply_to": queue.reply_to,
        "is_group": queue.is_group,
        "text": combined_text,
        "is_voice": has_voice,
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                DISCORDBOT_WHATSAPP_URL,
                json=_payload,
                timeout=600,
            )
            logger.info(f"WhatsApp forward to Peter: {resp.status_code}")
    except Exception as e:
        logger.error(f"WhatsApp forward failed: {e}")
        # Smart fallback: if channel mode is on but unreachable, try bot.py handler
        if _WHATSAPP_USE_CHANNEL:
            logger.warning("Channel unreachable — falling back to bot.py handler")
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        "http://127.0.0.1:8101/whatsapp/message",
                        json=_payload,
                        timeout=600,
                    )
                    logger.info(f"WhatsApp fallback to bot.py: {resp.status_code}")
            except Exception as e2:
                logger.error(f"WhatsApp fallback also failed: {e2}")

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
