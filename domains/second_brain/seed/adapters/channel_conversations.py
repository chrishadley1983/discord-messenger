"""Peter conversation ingestion from channel session transcripts.

The old discord:// conversation capture died on 20 Apr 2026 when the channel
migration removed the router_v2 path that fed it. This adapter restores it
for the channel era: it reads the Claude Code transcripts of the
peter-channel and whatsapp-channel sessions (same files the cost tail uses)
and emits one item per channel per completed day containing the
Chris↔Peter exchange.

Message anatomy in channel transcripts:
- Chris's turns are user messages starting with a '<channel source="...">'
  header; the real text follows the header and ends at the injected
  "[Recent channel history for context]" block (stripped — it repeats
  earlier turns).
- Peter's turns are mcp__<channel>__reply / voice_reply tool calls; the
  outbound text is in the tool input (plus any plain text blocks).

Session→channel labelling reuses the cost tail's logic and cache.
"""

import json
import re
from collections import defaultdict
from datetime import date, datetime, timezone

from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter

from domains.peterbot.channel_cost_tail import (
    TRANSCRIPT_DIR,
    CHANNEL_CACHE_PATH,
    _identify_channel,
    _load_json,
    _save_json,
)

CONVERSATION_CHANNELS = {"peter-channel", "whatsapp-channel"}
HISTORY_MARKER = "[Recent channel history"
HEADER_RE = re.compile(r'^<channel source="[^"]*"[^>]*>\s*', re.DOTALL)
MAX_DAYS_BACK = 30


def _chris_text(content) -> str | None:
    """Extract Chris's actual message from a channel-injected user turn."""
    if isinstance(content, list):
        content = "\n".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text")
    if not isinstance(content, str) or "<channel source=" not in content[:200]:
        return None
    text = HEADER_RE.sub("", content.strip())
    if HISTORY_MARKER in text:
        text = text[: text.index(HISTORY_MARKER)]
    text = text.replace("</channel>", "")
    return text.strip() or None


def _peter_texts(content) -> list[str]:
    """Peter's outbound replies from an assistant turn (reply tool inputs)."""
    if not isinstance(content, list):
        return []
    out = []
    for b in content:
        if not isinstance(b, dict) or b.get("type") != "tool_use":
            continue
        name = b.get("name", "")
        if "reply" not in name.lower():
            continue
        inp = b.get("input", {}) or {}
        text = inp.get("text") or inp.get("message") or ""
        if text:
            out.append(str(text))
    return out


@register_adapter
class ChannelConversationsAdapter(SeedAdapter):
    """Daily Chris↔Peter conversation extracts from channel transcripts."""

    name = "channel-conversations"
    description = "Peter conversations (Discord/WhatsApp channels) into Second Brain"
    source_system = "discord"  # continuity with the pre-channel capture

    async def validate(self) -> tuple[bool, str]:
        return True, ""  # WSL/UNC may be down — fetch no-ops

    async def fetch(self, limit: int = 60) -> list[SeedItem]:
        import asyncio
        return await asyncio.to_thread(self._fetch_sync, limit)

    def _fetch_sync(self, limit: int) -> list[SeedItem]:
        if not TRANSCRIPT_DIR.exists():
            logger.info("Channel transcript dir unreachable — skipping conversation ingest")
            return []

        cache = _load_json(CHANNEL_CACHE_PATH, {})
        today = date.today()

        # (channel, day) -> list[(dt, speaker, text)]
        by_day: dict[tuple[str, str], list] = defaultdict(list)

        for f in sorted(TRANSCRIPT_DIR.glob("*.jsonl")):
            channel = cache.get(f.stem) or _identify_channel(f, cache)
            if channel not in CONVERSATION_CHANNELS:
                continue
            try:
                lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError as e:
                logger.warning(f"channel-conversations: cannot read {f.name}: {e}")
                continue

            for line in lines:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = entry.get("message") or {}
                ts = entry.get("timestamp", "")
                try:
                    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    continue
                day = dt.date()
                if day >= today or (today - day).days > MAX_DAYS_BACK:
                    continue  # only completed, recent days

                if msg.get("role") == "user":
                    text = _chris_text(msg.get("content"))
                    if text:
                        by_day[(channel, day.isoformat())].append((dt, "Chris", text))
                elif msg.get("role") == "assistant":
                    for text in _peter_texts(msg.get("content")):
                        by_day[(channel, day.isoformat())].append((dt, "Peter", text))

        _save_json(CHANNEL_CACHE_PATH, cache)

        items: list[SeedItem] = []
        for (channel, day), msgs in sorted(by_day.items()):
            if len(msgs) < 2:
                continue  # no actual exchange
            msgs.sort()
            medium = "Discord" if channel == "peter-channel" else "WhatsApp"
            lines = [
                f"# {medium} conversation: Chris & Peter — {day}",
                "",
                f"**Messages:** {len(msgs)}",
                "",
            ]
            lines += [
                f"- {dt.strftime('%H:%M')} **{who}**: {text[:1500]}"
                for dt, who, text in msgs
            ]
            items.append(SeedItem(
                title=f"{medium}: Chris & Peter ({day})",
                content="\n".join(lines),
                source_url=f"channel://{channel}/{day}",
                topics=["peter", "chat-summary",
                        "discord" if medium == "Discord" else "whatsapp"],
                created_at=msgs[-1][0],
                metadata={"channel": channel, "message_count": len(msgs)},
                content_type="conversation_extract",
            ))

        logger.info(f"Channel conversations: {len(items)} daily items")
        return items[:limit]

    def get_default_topics(self) -> list[str]:
        return ["peter"]
