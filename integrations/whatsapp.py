"""Evolution API WhatsApp client.

Wraps the Evolution API REST endpoints for sending/receiving WhatsApp
messages via a self-hosted instance using the second number (+447784072956).

Replaces Twilio for all WhatsApp sending. Incoming messages are handled
via webhook (see hadley_api/routers/whatsapp_webhook.py).
"""
import asyncio
import logging
import os
import re

import requests

logger = logging.getLogger(__name__)

# Evolution API config
EVOLUTION_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8085")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "peter-whatsapp-2026-hadley")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "peter-whatsapp")

# Known contacts
CONTACTS = {
    "chris": "447855620978",
    "abby": "447856182831",
}

# Known groups (JID format: <id>@g.us)
GROUPS = {
    "extended-team": "120363424758610750@g.us",
}

HEADERS = {
    "apikey": EVOLUTION_API_KEY,
    "Content-Type": "application/json",
}


def _format_number(number: str) -> str:
    """Ensure number is in international format without + prefix."""
    number = number.strip().replace(" ", "").replace("-", "")
    if number.startswith("+"):
        number = number[1:]
    if number.startswith("0"):
        number = "44" + number[1:]
    return number


def _discord_to_whatsapp_markdown(text: str) -> str:
    """Convert Discord markdown to WhatsApp format.

    Discord uses **bold** and __underline__, WhatsApp uses *bold* and _italic_.
    """
    # **bold** -> *bold*
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    # __text__ -> _text_
    text = re.sub(r"__(.+?)__", r"_\1_", text)
    # ~~strike~~ -> ~strike~
    text = re.sub(r"~~(.+?)~~", r"~\1~", text)
    # ```code``` -> ```code```  (same in WhatsApp)
    return text


def send_text_sync(number: str, text: str) -> dict:
    """Send a text message synchronously.

    Args:
        number: Phone number (any format) or group JID (xxx@g.us)
        text: Message text (Discord markdown auto-converted)

    Returns:
        API response dict or error dict
    """
    # Don't mangle group JIDs
    if "@" not in number:
        number = _format_number(number)
    text = _discord_to_whatsapp_markdown(text)

    try:
        resp = requests.post(
            f"{EVOLUTION_URL}/message/sendText/{EVOLUTION_INSTANCE}",
            headers=HEADERS,
            json={
                "number": number,
                "text": text,
            },
            timeout=15,
        )

        if resp.ok:
            logger.info(f"WhatsApp sent to {number}")
            return resp.json()
        else:
            logger.error(f"WhatsApp send failed ({resp.status_code}): {resp.text[:200]}")
            return {"error": resp.text, "status": resp.status_code}

    except requests.RequestException as e:
        logger.error(f"WhatsApp send error: {e}")
        return {"error": str(e)}


async def send_text(number: str, text: str) -> dict:
    """Send a text message asynchronously."""
    return await asyncio.to_thread(send_text_sync, number, text)


async def send_to_recipients(text: str, recipients: list[str] = None) -> list[dict]:
    """Send a message to multiple recipients.

    Args:
        text: Message text
        recipients: List of phone numbers. Defaults to Chris + Abby.

    Returns:
        List of (number, success, result) tuples
    """
    if recipients is None:
        recipients = [CONTACTS["chris"], CONTACTS["abby"]]

    results = []
    for number in recipients:
        result = await send_text(number, text)
        success = "error" not in result
        results.append({
            "number": number,
            "success": success,
            "result": result,
        })

    return results


async def send_to_group(group_key: str, text: str) -> dict:
    """Send a message to a WhatsApp group.

    Args:
        group_key: Key from GROUPS dict (e.g. "extended-team") or raw JID
        text: Message text
    """
    group_jid = GROUPS.get(group_key, group_key)
    text = _discord_to_whatsapp_markdown(text)

    def _send():
        try:
            resp = requests.post(
                f"{EVOLUTION_URL}/message/sendText/{EVOLUTION_INSTANCE}",
                headers=HEADERS,
                json={"number": group_jid, "text": text},
                timeout=15,
            )
            if resp.ok:
                logger.info(f"WhatsApp sent to group {group_key}")
                return resp.json()
            else:
                logger.error(f"WhatsApp group send failed ({resp.status_code}): {resp.text[:200]}")
                return {"error": resp.text, "status": resp.status_code}
        except requests.RequestException as e:
            logger.error(f"WhatsApp group send error: {e}")
            return {"error": str(e)}

    return await asyncio.to_thread(_send)


def send_audio_sync(number: str, audio_base64: str) -> dict:
    """Send an audio message (voice note) synchronously.

    Args:
        number: Phone number (any format) or group JID (xxx@g.us)
        audio_base64: Base64-encoded audio data

    Returns:
        API response dict or error dict
    """
    if "@" not in number:
        number = _format_number(number)

    try:
        resp = requests.post(
            f"{EVOLUTION_URL}/message/sendWhatsAppAudio/{EVOLUTION_INSTANCE}",
            headers=HEADERS,
            json={
                "number": number,
                "audio": audio_base64,
            },
            timeout=30,
        )

        if resp.ok:
            logger.info(f"WhatsApp audio sent to {number}")
            return resp.json()
        else:
            logger.error(f"WhatsApp audio send failed ({resp.status_code}): {resp.text[:200]}")
            return {"error": resp.text, "status": resp.status_code}

    except requests.RequestException as e:
        logger.error(f"WhatsApp audio send error: {e}")
        return {"error": str(e)}


async def send_audio(number: str, audio_base64: str) -> dict:
    """Send an audio message (voice note) asynchronously."""
    return await asyncio.to_thread(send_audio_sync, number, audio_base64)


async def send_to_chris(text: str) -> dict:
    """Send a message to Chris only."""
    return await send_text(CONTACTS["chris"], text)


async def send_to_abby(text: str) -> dict:
    """Send a message to Abby only."""
    return await send_text(CONTACTS["abby"], text)


def check_connection_sync() -> dict:
    """Check if the WhatsApp instance is connected."""
    try:
        resp = requests.get(
            f"{EVOLUTION_URL}/instance/connectionState/{EVOLUTION_INSTANCE}",
            headers=HEADERS,
            timeout=10,
        )
        if resp.ok:
            return resp.json()
        return {"error": resp.text, "status": resp.status_code}
    except requests.RequestException as e:
        return {"error": str(e)}


async def check_connection() -> dict:
    """Check if the WhatsApp instance is connected (async)."""
    return await asyncio.to_thread(check_connection_sync)


async def is_connected() -> bool:
    """Quick check if WhatsApp is connected and ready."""
    result = await check_connection()
    state = result.get("instance", {}).get("state", "")
    return state == "open"
