"""Discord Peter interactions adapter.

Imports Q&A exchanges from Peter chat channels using the Discord REST API.
Pairs consecutive user/bot messages as knowledge items.
"""

import os
from datetime import datetime, timedelta, timezone

import httpx

from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter


# Peter chat channel IDs — add more as needed
PETER_CHAT_CHANNELS = [
    os.getenv("PETER_CHAT_CHANNEL_ID", ""),  # Primary #peter-chat
]

# Filter out channels that are empty strings
PETER_CHAT_CHANNELS = [c for c in PETER_CHAT_CHANNELS if c]

DISCORD_API_BASE = "https://discord.com/api/v10"


@register_adapter
class PeterInteractionsAdapter(SeedAdapter):
    """Import Peter chat Q&A exchanges from Discord."""

    name = "peter-interactions"
    description = "Peter bot Q&A exchanges from Discord"
    source_system = "seed:peter"

    def get_default_topics(self) -> list[str]:
        return ["peter", "conversation"]

    async def validate(self) -> tuple[bool, str]:
        token = os.getenv("DISCORD_TOKEN")
        if not token:
            return False, "DISCORD_TOKEN not set"
        channels = self.config.get("channel_ids", PETER_CHAT_CHANNELS)
        if not channels:
            return False, "No Peter chat channel IDs configured (set PETER_CHAT_CHANNEL_ID)"
        return True, ""

    async def fetch(self, limit: int = 50) -> list[SeedItem]:
        items = []
        token = os.getenv("DISCORD_TOKEN")
        if not token:
            return items

        channels = self.config.get("channel_ids", PETER_CHAT_CHANNELS)
        days_back = self.config.get("days_back", 7)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

        headers = {
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            for channel_id in channels:
                if not channel_id:
                    continue

                try:
                    messages = await self._fetch_channel_messages(
                        client, headers, channel_id, limit=200
                    )

                    # Pair user messages with bot responses
                    pairs = self._pair_qa_messages(messages, cutoff)

                    for question, answer in pairs:
                        q_content = question.get("content", "")
                        a_content = answer.get("content", "")

                        if not q_content or not a_content:
                            continue

                        # Skip very short exchanges
                        if len(q_content) < 10 and len(a_content) < 50:
                            continue

                        q_author = question.get("author", {}).get("username", "User")
                        timestamp = question.get("timestamp", "")
                        msg_id = question.get("id", "")

                        content = f"**{q_author}:** {q_content}\n\n**Peter:** {a_content}"

                        created_at = None
                        if timestamp:
                            try:
                                created_at = datetime.fromisoformat(
                                    timestamp.replace("Z", "+00:00")
                                )
                            except ValueError:
                                pass

                        items.append(SeedItem(
                            title=f"Peter Chat: {q_content[:60]}",
                            content=content,
                            source_url=f"peter-chat://{channel_id}/{msg_id}",
                            source_id=f"peter-{channel_id}-{msg_id}",
                            topics=["peter", "conversation"],
                            created_at=created_at,
                            content_type="conversation_extract",
                        ))

                        if len(items) >= limit:
                            break

                except Exception as e:
                    logger.warning(f"Failed to fetch Peter chat from channel {channel_id}: {e}")

        logger.info(f"Fetched {len(items)} Peter interactions")
        return items[:limit]

    async def _fetch_channel_messages(
        self,
        client: httpx.AsyncClient,
        headers: dict,
        channel_id: str,
        limit: int = 200,
    ) -> list[dict]:
        """Fetch recent messages from a Discord channel."""
        messages = []
        params = {"limit": min(limit, 100)}

        while len(messages) < limit:
            response = await client.get(
                f"{DISCORD_API_BASE}/channels/{channel_id}/messages",
                headers=headers,
                params=params,
            )

            if response.status_code != 200:
                logger.warning(f"Discord API error {response.status_code}: {response.text[:200]}")
                break

            batch = response.json()
            if not batch:
                break

            messages.extend(batch)

            if len(batch) < 100:
                break

            # Paginate with before parameter
            params["before"] = batch[-1]["id"]

        return messages

    def _pair_qa_messages(
        self,
        messages: list[dict],
        cutoff: datetime,
    ) -> list[tuple[dict, dict]]:
        """Pair user questions with bot responses.

        Messages come newest-first from Discord API, so reverse for chronological.
        """
        # Reverse to chronological order
        messages = list(reversed(messages))

        pairs = []
        for i, msg in enumerate(messages):
            # Check if this is a user message (not a bot)
            author = msg.get("author", {})
            if author.get("bot"):
                continue

            # Check timestamp
            timestamp = msg.get("timestamp", "")
            if timestamp:
                try:
                    msg_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    if msg_time < cutoff:
                        continue
                except ValueError:
                    continue

            # Look for the next bot response
            for j in range(i + 1, min(i + 5, len(messages))):
                next_msg = messages[j]
                next_author = next_msg.get("author", {})
                if next_author.get("bot"):
                    pairs.append((msg, next_msg))
                    break

        return pairs
