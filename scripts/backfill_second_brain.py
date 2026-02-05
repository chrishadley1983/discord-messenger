"""Backfill Peter's responses to Second Brain.

Fetches Discord messages from peterbot channels and adds substantial
Peter responses to Second Brain for knowledge retrieval.

Usage:
    python scripts/backfill_second_brain.py [--dry-run] [--since YYYY-MM-DD] [--min-words N]

Example:
    python scripts/backfill_second_brain.py --since 2026-02-03  # Last 48 hours
    python scripts/backfill_second_brain.py --dry-run  # Preview without saving
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from typing import Optional

import aiohttp
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

# Configuration
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Peterbot channel IDs - main conversational channels
PETERBOT_CHANNEL_ID = int(os.getenv("PETERBOT_CHANNEL_ID", 0))
CHANNELS_TO_BACKFILL = {
    "#peterbot": PETERBOT_CHANNEL_ID,
}

# Bot user ID (Peter)
BOT_USER_ID = None  # Will be fetched from Discord API

# Patterns that indicate this is NOT valuable content (skip these)
SKIP_PATTERNS = [
    "executed at",           # Scheduled job confirmations
    "heartbeat",             # Heartbeat responses
    "logged:",               # Food logging confirmations
    "balance check",         # Balance reports
    "circuit breaker",       # System status
    "[scheduled job:",       # Scheduled job markers
]


async def get_bot_user_id(session: aiohttp.ClientSession) -> int:
    """Get the bot's user ID from Discord API."""
    url = "https://discord.com/api/v10/users/@me"
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}

    async with session.get(url, headers=headers) as resp:
        if resp.status != 200:
            raise Exception(f"Failed to get bot user: {await resp.text()}")
        data = await resp.json()
        return int(data["id"])


async def fetch_messages(
    session: aiohttp.ClientSession,
    channel_id: int,
    after_timestamp: datetime,
    limit: int = 100
) -> list[dict]:
    """Fetch messages from a Discord channel after a given timestamp."""
    discord_epoch = datetime(2015, 1, 1, tzinfo=timezone.utc)
    timestamp_ms = int((after_timestamp - discord_epoch).total_seconds() * 1000)
    after_snowflake = (timestamp_ms << 22)

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}

    all_messages = []
    last_id = after_snowflake

    while True:
        params = {"limit": limit, "after": last_id}

        async with session.get(url, headers=headers, params=params) as resp:
            if resp.status == 404:
                print(f"  Channel {channel_id} not found or no access")
                break
            if resp.status != 200:
                print(f"  Error fetching messages: {resp.status} - {await resp.text()}")
                break

            messages = await resp.json()

            if not messages:
                break

            all_messages.extend(messages)
            last_id = messages[0]["id"]

            print(f"  Fetched {len(messages)} messages (total: {len(all_messages)})")

            if len(messages) < limit:
                break

            await asyncio.sleep(0.5)

    return list(reversed(all_messages))


def extract_conversation_pairs(messages: list[dict], bot_user_id: int, min_words: int = 75) -> list[dict]:
    """Extract user question + Peter response pairs that are substantial.

    Args:
        messages: List of messages, oldest first
        bot_user_id: The bot's Discord user ID
        min_words: Minimum words in bot response to include

    Returns:
        List of pairs: {"user_msg": str, "bot_msg": str, "timestamp": str, "word_count": int}
    """
    pairs = []
    pending_user_msg = None

    for msg in messages:
        author_id = int(msg["author"]["id"])
        content = msg["content"]
        timestamp = msg["timestamp"]

        if not content or not content.strip():
            continue

        if author_id == bot_user_id:
            # This is a bot response
            word_count = len(content.split())

            # Skip short responses
            if word_count < min_words:
                continue

            # Skip responses matching skip patterns
            content_lower = content.lower()
            if any(pattern in content_lower for pattern in SKIP_PATTERNS):
                continue

            # Save the pair
            pairs.append({
                "user_msg": pending_user_msg or "(no user message)",
                "bot_msg": content,
                "timestamp": timestamp,
                "word_count": word_count,
            })
            pending_user_msg = None
        else:
            # This is a user message - save for context
            pending_user_msg = content

    return pairs


async def save_to_second_brain(
    user_msg: str,
    bot_msg: str,
    timestamp: str,
    dry_run: bool = False
) -> Optional[str]:
    """Save a Peter response to Second Brain.

    Args:
        user_msg: User's original question
        bot_msg: Peter's response
        timestamp: When the response was created
        dry_run: If True, just print without saving

    Returns:
        Item ID if saved, None otherwise
    """
    # Import here to avoid circular imports and only when needed
    from domains.second_brain.pipeline import process_capture
    from domains.second_brain.types import CaptureType

    # Create a title from the user question (used as first line for extraction)
    title_preview = user_msg[:60].strip() if user_msg else "Peter response"
    if len(user_msg) > 60:
        title_preview += "..."
    title = f"Peter: {title_preview}"

    # Format the content with title as first line (for proper extraction)
    content = f"""{title}

User asked: {user_msg}

Peter's response:
{bot_msg}

---
Source: Discord #peterbot, {timestamp}
Backfilled to Second Brain
"""

    if dry_run:
        safe_title = title.encode('ascii', 'replace').decode('ascii')
        print(f"  [DRY RUN] Would save: {safe_title}")
        return "dry-run-id"

    try:
        item = await process_capture(
            source=content,
            capture_type=CaptureType.PASSIVE,  # Use passive for backfilled content
            user_note=f"Backfilled from Discord at {timestamp}",
            source_url=f"discord-backfill-{timestamp}",
        )

        if item:
            return str(item.id)
        return None

    except Exception as e:
        print(f"  Error saving to Second Brain: {e}")
        return None


async def backfill_channel(
    session: aiohttp.ClientSession,
    channel_name: str,
    channel_id: int,
    after_timestamp: datetime,
    bot_user_id: int,
    min_words: int = 75,
    dry_run: bool = False
) -> tuple[int, int]:
    """Backfill a single channel to Second Brain.

    Returns:
        Tuple of (pairs_found, pairs_saved)
    """
    print(f"\nBackfilling {channel_name} to Second Brain (ID: {channel_id})")

    if channel_id == 0:
        print(f"  Skipping - channel ID not configured")
        return 0, 0

    # Fetch messages
    messages = await fetch_messages(session, channel_id, after_timestamp)
    print(f"  Total messages fetched: {len(messages)}")

    # Extract substantial conversation pairs
    pairs = extract_conversation_pairs(messages, bot_user_id, min_words)
    print(f"  Substantial responses found (>{min_words} words): {len(pairs)}")

    # Save to Second Brain
    saved = 0
    for i, pair in enumerate(pairs, 1):
        print(f"  Processing {i}/{len(pairs)}: {pair['word_count']} words")

        item_id = await save_to_second_brain(
            pair["user_msg"],
            pair["bot_msg"],
            pair["timestamp"],
            dry_run=dry_run
        )

        if item_id:
            saved += 1
            if not dry_run:
                print(f"    Saved as {item_id}")

        # Rate limit protection
        if not dry_run:
            await asyncio.sleep(0.5)

    return len(pairs), saved


async def main():
    parser = argparse.ArgumentParser(description="Backfill Peter's responses to Second Brain")
    parser.add_argument(
        "--since",
        type=str,
        default="2026-02-03",  # Default to 48 hours ago
        help="Backfill messages since this date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--min-words",
        type=int,
        default=75,
        help="Minimum words in response to include (default: 75)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without saving to Second Brain"
    )
    args = parser.parse_args()

    # Parse date
    try:
        since_date = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        print(f"Invalid date format: {args.since}. Use YYYY-MM-DD")
        sys.exit(1)

    print(f"Backfilling Peter's responses to Second Brain since {args.since}")
    print(f"Minimum words per response: {args.min_words}")
    if args.dry_run:
        print("DRY RUN MODE - no data will be saved")

    # Check configuration
    if not DISCORD_TOKEN:
        print("Error: DISCORD_TOKEN not set")
        sys.exit(1)

    async with aiohttp.ClientSession() as session:
        # Get bot user ID
        global BOT_USER_ID
        try:
            BOT_USER_ID = await get_bot_user_id(session)
            print(f"Bot user ID: {BOT_USER_ID}")
        except Exception as e:
            print(f"Error getting bot user ID: {e}")
            sys.exit(1)

        # Backfill each channel
        total_pairs = 0
        total_saved = 0

        for channel_name, channel_id in CHANNELS_TO_BACKFILL.items():
            pairs, saved = await backfill_channel(
                session,
                channel_name,
                channel_id,
                since_date,
                BOT_USER_ID,
                min_words=args.min_words,
                dry_run=args.dry_run
            )
            total_pairs += pairs
            total_saved += saved

        # Summary
        print(f"\n{'='*50}")
        print(f"Second Brain Backfill Complete!")
        print(f"  Substantial responses found: {total_pairs}")
        print(f"  Items saved to Second Brain: {total_saved}")
        if args.dry_run:
            print("  (Dry run - no data was actually saved)")


if __name__ == "__main__":
    asyncio.run(main())
