"""Discord communication: webhook sends + REST API polling for replies.

Uses aiohttp for async HTTP. The ReplyPoller switches between active (500ms)
and idle (3s) polling intervals to balance responsiveness and rate limits.
"""

import asyncio
import logging
import time

import aiohttp

from config import (
    DISCORD_TOKEN,
    DISCORD_API,
    PETERBOT_CHANNEL_ID,
    WEBHOOK_URL,
    POLL_INTERVAL_ACTIVE,
    POLL_INTERVAL_IDLE,
    POLL_TIMEOUT,
    get_bot_user_id,
    set_bot_user_id,
)

log = logging.getLogger(__name__)


async def discover_bot_user_id(session: aiohttp.ClientSession) -> str:
    """Fetch bot's own user ID via GET /users/@me and cache it."""
    cached = get_bot_user_id()
    if cached:
        return cached

    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    async with session.get(f"{DISCORD_API}/users/@me", headers=headers) as resp:
        resp.raise_for_status()
        data = await resp.json()
        user_id = data["id"]
        set_bot_user_id(user_id)
        log.info("Discovered bot user ID: %s", user_id)
        return user_id


async def send_to_peter(session: aiohttp.ClientSession, text: str) -> None:
    """Send a message to the Peterbot channel via webhook as 'Chris (Voice)'."""
    payload = {
        "content": text,
        "username": "Chris (Voice)",
    }
    async with session.post(WEBHOOK_URL, json=payload) as resp:
        if resp.status == 204 or resp.status == 200:
            log.info("Sent voice message: %s", text[:80])
        else:
            body = await resp.text()
            log.error("Webhook send failed (%d): %s", resp.status, body)


class ReplyPoller:
    """Polls Discord REST API for new messages from Peter's bot account.

    Modes:
    - Active: 500ms interval, engaged after sending a message
    - Idle: 3s interval, catches scheduled messages / typed conversation replies
    """

    def __init__(self):
        self._last_message_id: str | None = None
        self._bot_user_id: str | None = None
        self._active_until: float = 0
        self._was_active: bool = False
        self._session: aiohttp.ClientSession | None = None
        self._callback = None  # async callable(str)
        self._on_timeout = None  # async callable() — called when active→idle
        self._running = False
        self._rate_limit_until: float = 0

    async def start(
        self,
        session: aiohttp.ClientSession,
        callback,
        bot_user_id: str,
        on_timeout=None,
    ) -> None:
        """Begin polling. callback receives each new bot message text."""
        self._session = session
        self._callback = callback
        self._on_timeout = on_timeout
        self._bot_user_id = bot_user_id
        self._running = True

        # Seed last_message_id with the most recent message
        await self._seed_last_id()

        log.info("Reply poller started (idle mode)")
        while self._running:
            interval = self._current_interval()
            await asyncio.sleep(interval)
            if not self._running:
                break
            await self._poll()

    async def _seed_last_id(self) -> None:
        """Get the latest message ID so we only detect new messages."""
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        url = f"{DISCORD_API}/channels/{PETERBOT_CHANNEL_ID}/messages?limit=1"
        try:
            async with self._session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    messages = await resp.json()
                    if messages:
                        self._last_message_id = messages[0]["id"]
                        log.debug("Seeded last_message_id: %s", self._last_message_id)
        except Exception as e:
            log.warning("Failed to seed last message ID: %s", e)

    def activate(self) -> None:
        """Switch to active polling (after sending a message)."""
        self._active_until = time.monotonic() + POLL_TIMEOUT
        self._was_active = True
        log.debug("Poller active for %ds", POLL_TIMEOUT)

    def stop(self) -> None:
        self._running = False

    def _current_interval(self) -> float:
        now = time.monotonic()
        # Respect rate limit backoff
        if now < self._rate_limit_until:
            return self._rate_limit_until - now
        if now < self._active_until:
            return POLL_INTERVAL_ACTIVE
        # Transition from active → idle: notify timeout
        if self._was_active:
            self._was_active = False
            if self._on_timeout:
                import asyncio
                asyncio.ensure_future(self._on_timeout())
        return POLL_INTERVAL_IDLE

    async def _poll(self) -> None:
        """Fetch new messages and dispatch bot replies."""
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        url = f"{DISCORD_API}/channels/{PETERBOT_CHANNEL_ID}/messages?limit=10"
        if self._last_message_id:
            url += f"&after={self._last_message_id}"

        try:
            async with self._session.get(url, headers=headers) as resp:
                if resp.status == 429:
                    retry_after = (await resp.json()).get("retry_after", 5)
                    log.warning("Rate limited, backing off %.1fs", retry_after)
                    self._rate_limit_until = time.monotonic() + retry_after + 0.5
                    return
                if resp.status != 200:
                    log.warning("Poll failed (%d)", resp.status)
                    return

                messages = await resp.json()
        except Exception as e:
            log.warning("Poll error: %s", e)
            return

        if not messages:
            return

        # Messages come newest-first, process oldest-first
        messages.sort(key=lambda m: m["id"])
        self._last_message_id = messages[-1]["id"]

        is_active = time.monotonic() < self._active_until
        for msg in messages:
            author_id = msg.get("author", {}).get("id")
            if author_id == self._bot_user_id and self._callback:
                content = msg.get("content", "")
                if content:
                    log.info("Peter replied (%s): %s", "active" if is_active else "idle", content[:80])
                    await self._callback(content, is_active)
