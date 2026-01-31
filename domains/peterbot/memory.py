"""Memory client for peterbot - context retrieval and capture."""

import asyncio
from collections import deque
from typing import Optional
import aiohttp

from logger import logger
from .config import (
    CONTEXT_ENDPOINT,
    MESSAGES_ENDPOINT,
    PROJECT_ID,
    RECENT_BUFFER_SIZE,
    FAILURE_QUEUE_MAX,
    RETRY_INTERVAL_SECONDS,
    MAX_RETRIES,
)

# Recent conversation buffer (shared across messages)
_recent_buffer: deque[dict] = deque(maxlen=RECENT_BUFFER_SIZE)

# Failure queue for retry
_failure_queue: deque[dict] = deque(maxlen=FAILURE_QUEUE_MAX)

# Retry task handle
_retry_task: Optional[asyncio.Task] = None


def add_to_buffer(role: str, content: str) -> None:
    """Add a message to the recent conversation buffer.

    Args:
        role: 'user' or 'assistant'
        content: Message content
    """
    _recent_buffer.append({
        "role": role,
        "content": content
    })


def get_recent_context() -> str:
    """Format buffer as context string for prompt injection.

    Returns:
        Formatted string of recent exchanges, or empty string if buffer is empty.
    """
    if not _recent_buffer:
        return ""

    lines = ["## Recent Conversation"]
    for msg in _recent_buffer:
        prefix = "User" if msg["role"] == "user" else "Assistant"
        # Truncate long messages for context
        content = msg["content"]
        if len(content) > 500:
            content = content[:500] + "..."
        lines.append(f"**{prefix}:** {content}")

    return "\n".join(lines)


async def get_memory_context(query: str) -> str:
    """Fetch memory context from peterbot-mem worker.

    Args:
        query: The user's message to search memory for

    Returns:
        Plain text memory context, or empty string on failure
    """
    params = {
        "project": PROJECT_ID,
        "query": query
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                CONTEXT_ENDPOINT,
                params=params,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    # Returns plain text context
                    context = await resp.text()
                    logger.debug(f"Memory context fetched: {len(context)} chars")
                    return context
                else:
                    text = await resp.text()
                    logger.warning(f"Memory context API error {resp.status}: {text}")
                    return ""
    except aiohttp.ClientError as e:
        logger.warning(f"Memory context connection error: {e}")
        return ""
    except Exception as e:
        logger.warning(f"Memory context unexpected error: {e}")
        return ""


def build_full_context(message: str, memory_context: str) -> str:
    """Build full context combining memory, recent buffer, and current message.

    Args:
        message: The current user message
        memory_context: Retrieved memory observations

    Returns:
        Combined context string
    """
    parts = []

    # Add memory context if available
    if memory_context and memory_context.strip():
        parts.append("## Memory Context")
        parts.append(memory_context.strip())
        parts.append("")

    # Add recent conversation buffer
    recent = get_recent_context()
    if recent:
        parts.append(recent)
        parts.append("")

    # Add current message
    parts.append("## Current Message")
    parts.append(message)

    return "\n".join(parts)


async def capture_message_pair(
    session_id: str,
    user_message: str,
    assistant_response: str
) -> bool:
    """Send conversation exchange to peterbot-mem for observation extraction.

    This is fire-and-forget - failures are queued for retry.

    Args:
        session_id: Unique session identifier (e.g., discord-123)
        user_message: The user's message
        assistant_response: The assistant's response

    Returns:
        True if successfully sent, False if queued for retry
    """
    payload = {
        "contentSessionId": session_id,
        "source": "discord",
        "channel": "peterbot",
        "userMessage": user_message,
        "assistantResponse": assistant_response,
        "metadata": {}
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                MESSAGES_ENDPOINT,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 202:
                    logger.info(f"Memory captured for session {session_id}")
                    return True
                else:
                    text = await resp.text()
                    logger.error(f"Memory capture error {resp.status}: {text}")
                    _queue_for_retry(payload)
                    return False
    except aiohttp.ClientError as e:
        logger.error(f"Memory capture connection error: {e}")
        _queue_for_retry(payload)
        return False
    except Exception as e:
        logger.error(f"Memory capture unexpected error: {e}")
        _queue_for_retry(payload)
        return False


def _queue_for_retry(payload: dict, retries: int = 0) -> None:
    """Add failed payload to retry queue."""
    if retries >= MAX_RETRIES:
        logger.error(f"Dropping payload after {MAX_RETRIES} retries")
        return

    payload["_retries"] = retries
    _failure_queue.append(payload)
    logger.debug(f"Queued for retry ({len(_failure_queue)} in queue)")


async def _retry_loop() -> None:
    """Background task to retry failed captures."""
    while True:
        await asyncio.sleep(RETRY_INTERVAL_SECONDS)

        if not _failure_queue:
            continue

        # Process one item per interval
        payload = _failure_queue.popleft()
        retries = payload.pop("_retries", 0)

        logger.info(f"Retrying memory capture (attempt {retries + 1})")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    MESSAGES_ENDPOINT,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 202:
                        logger.info("Retry successful")
                    else:
                        _queue_for_retry(payload, retries + 1)
        except Exception as e:
            logger.warning(f"Retry failed: {e}")
            _queue_for_retry(payload, retries + 1)


def start_retry_task() -> None:
    """Start the background retry task (call on bot startup)."""
    global _retry_task

    if _retry_task is not None and not _retry_task.done():
        logger.debug("Retry task already running")
        return

    loop = asyncio.get_event_loop()
    _retry_task = loop.create_task(_retry_loop())
    logger.info("Memory retry task started")
