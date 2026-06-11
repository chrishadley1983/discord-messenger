"""WhatsApp chat ingestion via Evolution API.

Replaces the dead WhatsApp Web scraper (whatsapp_scraper.py, deleted ~17 Mar
2026, jobs silently "succeeding" since — see jobs/whatsapp_sync.py history).
Reads Chris's chats from the ``chris-whatsapp`` Evolution instance (his
account linked as a device — NOT peter-whatsapp, which is Peter's own number
and only sees Peter's chats).

Each run emits one item per chat per completed ISO week (Mon-Sun) containing
the message transcript. Media messages become explicit placeholders
("[image: caption]", "[document: filename]") instead of being silently
dropped — the failure mode that hid Sam's decorating quote on 15 Feb 2026.
The capture pipeline (Haiku) generates the summary/facts/topics.

The seed runner dedupes by source_url (whatsapp://<slug>/<isoweek>), so only
new completed weeks import on each nightly run. No-ops cleanly when the
instance isn't connected.
"""

import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import httpx

from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter

EVOLUTION_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8085")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "peter-whatsapp-2026-hadley")
CHRIS_INSTANCE = os.getenv("CHRIS_WHATSAPP_INSTANCE", "chris-whatsapp")

MAX_WEEKS_BACK = 8           # bound backfill window per run
MAX_MESSAGES_PER_CHAT = 2000  # findMessages page cap
MIN_MESSAGES_PER_WEEK = 2     # skip weeks with a lone message (no conversation)

MEDIA_LABELS = {
    "imageMessage": "image",
    "videoMessage": "video",
    "audioMessage": "voice note",
    "documentMessage": "document",
    "documentWithCaptionMessage": "document",
    "stickerMessage": "sticker",
    "locationMessage": "location",
    "contactMessage": "contact card",
}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "unknown"


def _headers() -> dict:
    return {"apikey": EVOLUTION_API_KEY}


def _extract_text(msg: dict) -> str:
    """Readable line for any message type; media become explicit placeholders."""
    m = msg.get("message") or {}
    text = m.get("conversation") or (m.get("extendedTextMessage") or {}).get("text")
    if text:
        return text

    mtype = msg.get("messageType", "")
    label = MEDIA_LABELS.get(mtype, mtype or "message")
    inner = m.get(mtype) or {}
    if isinstance(inner, dict):
        caption = inner.get("caption") or ""
        filename = inner.get("fileName") or ""
        detail = caption or filename
        if detail:
            return f"[{label}: {detail}]"
    return f"[{label}]"


def _iso_week_key(d: date) -> str:
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


@register_adapter
class WhatsAppEvolutionAdapter(SeedAdapter):
    """Weekly per-chat WhatsApp transcripts from Chris's linked account."""

    name = "whatsapp-evolution"
    description = "WhatsApp chat ingestion from the chris-whatsapp Evolution instance"
    source_system = "seed:whatsapp"

    async def validate(self) -> tuple[bool, str]:
        return True, ""  # not-connected is a normal state; fetch no-ops

    async def fetch(self, limit: int = 100) -> list[SeedItem]:
        async with httpx.AsyncClient(timeout=60) as client:
            try:
                state = await client.get(
                    f"{EVOLUTION_URL}/instance/connectionState/{CHRIS_INSTANCE}",
                    headers=_headers(),
                )
                if state.json().get("instance", {}).get("state") != "open":
                    logger.info(f"{CHRIS_INSTANCE} not connected — skipping WhatsApp ingest")
                    return []
            except Exception as e:
                logger.warning(f"Evolution unreachable: {e}")
                return []

            resp = await client.post(
                f"{EVOLUTION_URL}/chat/findChats/{CHRIS_INSTANCE}",
                headers=_headers(), json={},
            )
            chats = resp.json() if isinstance(resp.json(), list) else []

            cutoff = datetime.now(timezone.utc) - timedelta(weeks=MAX_WEEKS_BACK)
            this_week = _iso_week_key(date.today())
            items: list[SeedItem] = []

            for chat in chats:
                jid = chat.get("remoteJid", "")
                if not jid or jid.endswith("@broadcast"):
                    continue
                name = chat.get("pushName") or jid.split("@")[0]
                is_group = jid.endswith("@g.us")

                try:
                    mresp = await client.post(
                        f"{EVOLUTION_URL}/chat/findMessages/{CHRIS_INSTANCE}",
                        headers=_headers(),
                        json={"where": {"key": {"remoteJid": jid}},
                              "limit": MAX_MESSAGES_PER_CHAT},
                    )
                    mdata = mresp.json()
                    records = (mdata.get("messages", {}) or {}).get("records", []) \
                        if isinstance(mdata, dict) else mdata
                except Exception as e:
                    logger.warning(f"findMessages failed for {name}: {e}")
                    continue

                by_week: dict[str, list[tuple[datetime, str, str]]] = defaultdict(list)
                for r in records:
                    ts = r.get("messageTimestamp", 0)
                    try:
                        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                    except (ValueError, TypeError, OSError):
                        continue
                    if dt < cutoff:
                        continue
                    week = _iso_week_key(dt.date())
                    if week >= this_week:
                        continue  # only completed weeks — runner never updates items
                    sender = "Chris" if (r.get("key") or {}).get("fromMe") else (
                        r.get("pushName") or name)
                    by_week[week].append((dt, sender, _extract_text(r)))

                for week, msgs in sorted(by_week.items()):
                    if len(msgs) < MIN_MESSAGES_PER_WEEK:
                        continue
                    msgs.sort()
                    start, end = msgs[0][0].date(), msgs[-1][0].date()
                    lines = [
                        f"# WhatsApp: {name} ({start} to {end})",
                        "",
                        f"**Chat type:** {'group' if is_group else 'direct'}",
                        f"**Messages:** {len(msgs)}",
                        "",
                        "## Transcript",
                        "",
                    ]
                    lines += [
                        f"- {dt.strftime('%a %d %b %H:%M')} **{sender}**: {text}"
                        for dt, sender, text in msgs
                    ]
                    items.append(SeedItem(
                        title=f"WhatsApp: {name} ({start} to {end})",
                        content="\n".join(lines),
                        source_url=f"whatsapp://{_slug(name)}/{week}",
                        topics=["whatsapp", "chat-summary"]
                               + (["group-chat"] if is_group else []),
                        created_at=msgs[-1][0],
                        metadata={"jid": jid, "week": week, "message_count": len(msgs)},
                        content_type="conversation_extract",
                    ))

            logger.info(f"WhatsApp Evolution ingest: {len(items)} weekly chat items")
            return items[:limit]

    def get_default_topics(self) -> list[str]:
        return ["whatsapp"]
