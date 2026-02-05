"""Backfill missed peterbot conversations to memory.

Fetches Discord messages from peterbot channels since the last observation
and sends them to the memory endpoint for observation extraction.

Usage:
    python scripts/backfill_memory.py [--dry-run] [--since YYYY-MM-DD]

Example:
    python scripts/backfill_memory.py --since 2026-02-01
    python scripts/backfill_memory.py --dry-run  # Preview without sending
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
MEMORY_ENDPOINT = os.getenv("PETERBOT_MEM_URL", "http://localhost:37777")
MESSAGES_ENDPOINT = f"{MEMORY_ENDPOINT}/api/sessions/messages"
PROJECT_ID = "peterbot"

# Peterbot channel IDs - main conversational channels
PETERBOT_CHANNEL_ID = int(os.getenv("PETERBOT_CHANNEL_ID", 0))
CHANNELS_TO_BACKFILL = {
    "#peterbot": PETERBOT_CHANNEL_ID,
    "#food-log": 1465294449038069912,
}

# Bot user ID (Peter)
BOT_USER_ID = None  # Will be fetched from Discord API


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
    """Fetch messages from a Discord channel after a given timestamp.

    Args:
        session: aiohttp session
        channel_id: Discord channel ID
        after_timestamp: Fetch messages after this time
        limit: Max messages per request (max 100)

    Returns:
        List of message dicts, oldest first
    """
    # Convert timestamp to Discord snowflake
    # Discord epoch is 2015-01-01 00:00:00 UTC
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
            last_id = messages[0]["id"]  # Messages are returned newest first

            print(f"  Fetched {len(messages)} messages (total: {len(all_messages)})")

            if len(messages) < limit:
                break

            # Rate limit protection
            await asyncio.sleep(0.5)

    # Return oldest first for pairing
    return list(reversed(all_messages))


def pair_messages(messages: list[dict], bot_user_id: int) -> list[dict]:
    """Pair user messages with bot responses.

    Args:
        messages: List of messages, oldest first
        bot_user_id: The bot's Discord user ID

    Returns:
        List of pairs: {"user_id": int, "user_msg": str, "bot_msg": str, "timestamp": str}
    """
    pairs = []
    pending_user_msg = None
    pending_user_id = None

    for msg in messages:
        author_id = int(msg["author"]["id"])
        content = msg["content"]
        timestamp = msg["timestamp"]

        # Skip empty messages
        if not content or not content.strip():
            continue

        # Skip bot commands that aren't conversations
        if content.startswith("!") and not content.startswith("!skill"):
            continue

        if author_id == bot_user_id:
            # This is a bot response
            if pending_user_msg:
                pairs.append({
                    "user_id": pending_user_id,
                    "user_msg": pending_user_msg,
                    "bot_msg": content,
                    "timestamp": timestamp
                })
                pending_user_msg = None
                pending_user_id = None
        else:
            # This is a user message - save it for pairing
            # If there's already a pending user message, it means the bot didn't respond
            # to the previous one - we'll skip that orphaned message
            pending_user_msg = content
            pending_user_id = author_id

    return pairs


async def send_to_memory(
    session: aiohttp.ClientSession,
    user_id: int,
    user_msg: str,
    bot_msg: str,
    dry_run: bool = False
) -> bool:
    """Send a conversation pair to the memory endpoint.

    Args:
        session: aiohttp session
        user_id: Discord user ID
        user_msg: User's message
        bot_msg: Bot's response
        dry_run: If True, just print without sending

    Returns:
        True if successful (or dry run), False otherwise
    """
    payload = {
        "contentSessionId": f"backfill-discord-{user_id}",
        "project": PROJECT_ID,
        "source": "discord-backfill",
        "channel": "peterbot",
        "userMessage": user_msg,
        "assistantResponse": bot_msg,
        "metadata": {"backfilled": True}
    }

    if dry_run:
        # Sanitize for Windows console output
        user_preview = user_msg[:50].encode('ascii', 'replace').decode('ascii')
        bot_preview = bot_msg[:50].encode('ascii', 'replace').decode('ascii')
        print(f"  [DRY RUN] Would send: {user_preview}... -> {bot_preview}...")
        return True

    try:
        async with session.post(MESSAGES_ENDPOINT, json=payload, timeout=10) as resp:
            if resp.status == 202:
                return True
            else:
                text = await resp.text()
                print(f"  Error: {resp.status} - {text}")
                return False
    except Exception as e:
        print(f"  Error sending to memory: {e}")
        return False


async def backfill_channel(
    session: aiohttp.ClientSession,
    channel_name: str,
    channel_id: int,
    after_timestamp: datetime,
    bot_user_id: int,
    dry_run: bool = False
) -> tuple[int, int]:
    """Backfill a single channel.

    Returns:
        Tuple of (pairs_found, pairs_sent)
    """
    print(f"\nBackfilling {channel_name} (ID: {channel_id})")

    if channel_id == 0:
        print(f"  Skipping - channel ID not configured")
        return 0, 0

    # Fetch messages
    messages = await fetch_messages(session, channel_id, after_timestamp)
    print(f"  Total messages fetched: {len(messages)}")

    # Pair messages
    pairs = pair_messages(messages, bot_user_id)
    print(f"  Conversation pairs found: {len(pairs)}")

    # Send to memory
    sent = 0
    for pair in pairs:
        success = await send_to_memory(
            session,
            pair["user_id"],
            pair["user_msg"],
            pair["bot_msg"],
            dry_run=dry_run
        )
        if success:
            sent += 1

        # Rate limit protection
        if not dry_run:
            await asyncio.sleep(0.2)

    return len(pairs), sent


async def main():
    parser = argparse.ArgumentParser(description="Backfill peterbot conversations to memory")
    parser.add_argument(
        "--since",
        type=str,
        default="2026-02-01",
        help="Backfill messages since this date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without sending to memory"
    )
    args = parser.parse_args()

    # Parse date
    try:
        since_date = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        print(f"Invalid date format: {args.since}. Use YYYY-MM-DD")
        sys.exit(1)

    print(f"Backfilling peterbot conversations since {args.since}")
    if args.dry_run:
        print("DRY RUN MODE - no data will be sent")

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

        # Check memory endpoint health
        try:
            async with session.get(f"{MEMORY_ENDPOINT}/health") as resp:
                if resp.status != 200:
                    print(f"Warning: Memory endpoint not healthy: {resp.status}")
        except Exception as e:
            print(f"Warning: Cannot reach memory endpoint: {e}")
            if not args.dry_run:
                print("Aborting - memory endpoint unreachable")
                sys.exit(1)

        # Backfill each channel
        total_pairs = 0
        total_sent = 0

        for channel_name, channel_id in CHANNELS_TO_BACKFILL.items():
            pairs, sent = await backfill_channel(
                session,
                channel_name,
                channel_id,
                since_date,
                BOT_USER_ID,
                dry_run=args.dry_run
            )
            total_pairs += pairs
            total_sent += sent

        # Summary
        print(f"\n{'='*50}")
        print(f"Backfill complete!")
        print(f"  Total conversation pairs found: {total_pairs}")
        print(f"  Pairs sent to memory: {total_sent}")
        if args.dry_run:
            print("  (Dry run - no data was actually sent)")


if __name__ == "__main__":
    asyncio.run(main())
