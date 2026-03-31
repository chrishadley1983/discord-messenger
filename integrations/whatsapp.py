"""Evolution API WhatsApp client.

Wraps the Evolution API REST endpoints for sending/receiving WhatsApp
messages via a self-hosted instance using the second number (+447784072956).

Replaces Twilio for all WhatsApp sending. Incoming messages are handled
via webhook (see hadley_api/routers/whatsapp_webhook.py).
"""
import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# Evolution API config
EVOLUTION_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8085")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "peter-whatsapp-2026-hadley")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "peter-whatsapp")

# Retry config
MAX_RETRIES = 3
RETRY_BACKOFF = [2, 5, 10]  # seconds between retries

# --- Recipient config: loaded from data/whatsapp_recipients.json ---
_RECIPIENTS_FILE = Path(__file__).parent.parent / "data" / "whatsapp_recipients.json"

_FALLBACK_CONTACTS = {"chris": "447855620978", "abby": "447856182831"}
_FALLBACK_GROUPS = {"extended-team": "120363424758610750@g.us"}


def _load_recipients() -> tuple[dict[str, str], dict[str, str]]:
    """Load contacts and groups from JSON config file."""
    try:
        data = json.loads(_RECIPIENTS_FILE.read_text(encoding="utf-8"))
        return data.get("contacts", _FALLBACK_CONTACTS), data.get("groups", _FALLBACK_GROUPS)
    except Exception:
        logger.warning("Could not load whatsapp_recipients.json, using fallback")
        return _FALLBACK_CONTACTS.copy(), _FALLBACK_GROUPS.copy()


def _save_recipients(contacts: dict[str, str], groups: dict[str, str]):
    """Persist contacts and groups to JSON config file."""
    _RECIPIENTS_FILE.write_text(
        json.dumps({"contacts": contacts, "groups": groups}, indent=2) + "\n",
        encoding="utf-8",
    )


def reload_recipients():
    """Reload CONTACTS and GROUPS from disk. Called after add/remove operations."""
    global CONTACTS, GROUPS
    CONTACTS, GROUPS = _load_recipients()


CONTACTS, GROUPS = _load_recipients()

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


def _send_with_retry(method: str, url: str, payload: dict, timeout: int = 15) -> dict:
    """Send a request to Evolution API with retry and backoff.

    Retries on connection errors and 5xx responses. Does NOT retry on
    4xx (bad request) since those won't self-heal.

    Returns:
        API response dict or error dict with "error" key
    """
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.request(
                method, url, headers=HEADERS, json=payload, timeout=timeout,
            )

            if resp.ok:
                if attempt > 0:
                    logger.info(f"WhatsApp send succeeded on retry {attempt}")
                return resp.json()

            # Don't retry client errors (4xx)
            if 400 <= resp.status_code < 500:
                logger.error(f"WhatsApp send failed ({resp.status_code}): {resp.text[:200]}")
                return {"error": resp.text, "status": resp.status_code}

            # Server error — retry
            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            logger.warning(f"WhatsApp send attempt {attempt + 1}/{MAX_RETRIES} "
                           f"failed ({resp.status_code}), retrying...")

        except requests.ConnectionError as e:
            last_error = f"Connection error: {e}"
            logger.warning(f"WhatsApp send attempt {attempt + 1}/{MAX_RETRIES} "
                           f"connection failed, retrying...")
        except requests.RequestException as e:
            last_error = str(e)
            logger.warning(f"WhatsApp send attempt {attempt + 1}/{MAX_RETRIES} "
                           f"error: {e}, retrying...")

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_BACKOFF[attempt])

    logger.error(f"WhatsApp send failed after {MAX_RETRIES} attempts: {last_error}")
    return {"error": last_error, "retries_exhausted": True}


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

    result = _send_with_retry(
        "POST",
        f"{EVOLUTION_URL}/message/sendText/{EVOLUTION_INSTANCE}",
        {"number": number, "text": text},
    )
    if "error" not in result:
        logger.info(f"WhatsApp sent to {number}")
    return result


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
        result = _send_with_retry(
            "POST",
            f"{EVOLUTION_URL}/message/sendText/{EVOLUTION_INSTANCE}",
            {"number": group_jid, "text": text},
        )
        if "error" not in result:
            logger.info(f"WhatsApp sent to group {group_key}")
        return result

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

    result = _send_with_retry(
        "POST",
        f"{EVOLUTION_URL}/message/sendWhatsAppAudio/{EVOLUTION_INSTANCE}",
        {"number": number, "audio": audio_base64},
        timeout=30,
    )
    if "error" not in result:
        logger.info(f"WhatsApp audio sent to {number}")
    return result


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
