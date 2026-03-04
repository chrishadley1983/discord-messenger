"""Memory client for peterbot - context retrieval and capture via Second Brain."""

import asyncio
from collections import deque
from typing import Optional

from logger import logger
from .config import (
    RECENT_BUFFER_SIZE,
)

# Per-channel recent conversation buffers
# Each channel has its own deque to avoid context mixing
_recent_buffers: dict[int, deque] = {}


def _get_buffer(channel_id: int) -> deque:
    """Get or create buffer for a channel."""
    if channel_id not in _recent_buffers:
        _recent_buffers[channel_id] = deque(maxlen=RECENT_BUFFER_SIZE)
    return _recent_buffers[channel_id]


def is_buffer_empty(channel_id: int) -> bool:
    """Check if channel buffer is empty (needs Discord history fetch)."""
    return channel_id not in _recent_buffers or len(_recent_buffers[channel_id]) == 0


def populate_buffer_from_history(channel_id: int, messages: list[dict]) -> int:
    """Populate buffer from Discord message history.

    Called after restart to restore context from Discord.

    Args:
        channel_id: Discord channel ID
        messages: List of {'role': 'user'|'assistant', 'content': str}
                  in chronological order (oldest first)

    Returns:
        Number of messages added to buffer
    """
    buffer = _get_buffer(channel_id)
    buffer.clear()

    for msg in messages:
        buffer.append({
            "role": msg["role"],
            "content": msg["content"]
        })

    logger.info(f"Populated buffer for channel {channel_id} with {len(messages)} messages from Discord history")
    return len(messages)


def add_to_buffer(role: str, content: str, channel_id: int) -> None:
    """Add a message to the channel's recent conversation buffer.

    Args:
        role: 'user' or 'assistant'
        content: Message content
        channel_id: Discord channel ID
    """
    buffer = _get_buffer(channel_id)
    buffer.append({
        "role": role,
        "content": content
    })


def get_recent_context(channel_id: int) -> str:
    """Format buffer as context string for prompt injection.

    Args:
        channel_id: Discord channel ID

    Returns:
        Formatted string of recent exchanges, or empty string if buffer is empty.
    """
    buffer = _get_buffer(channel_id)
    if not buffer:
        return ""

    lines = ["## Recent Conversation"]
    for msg in buffer:
        prefix = "User" if msg["role"] == "user" else "Assistant"
        content = msg["content"]
        if len(content) > 500:
            content = content[:500] + "..."
        lines.append(f"**{prefix}:** {content}")

    return "\n".join(lines)


def build_full_context(
    message: str,
    channel_id: int,
    channel_name: str = "",
    knowledge_context: str = "",
    attachment_urls: list[dict] | None = None,
) -> str:
    """Build full context combining knowledge, recent buffer, and current message.

    Args:
        message: The current user message
        channel_id: Discord channel ID for per-channel buffer
        channel_name: Discord channel name (e.g., "#food-log")
        knowledge_context: Optional additional knowledge context
        attachment_urls: Optional list of attachment dicts with url, filename, content_type, size

    Returns:
        Combined context string
    """
    from datetime import datetime

    parts = []

    # Channel isolation header (prevents cross-channel context bleeding)
    parts.append("# CHANNEL CONTEXT")
    parts.append(f"**Active Channel:** {channel_name or f'Channel {channel_id}'}")
    parts.append("You are responding to a message in THIS channel only.")
    parts.append("Do NOT reference conversations or context from other channels.")
    parts.append("")

    # Add current date/time
    now = datetime.now()
    parts.append(f"## Current Time")
    parts.append(f"{now.strftime('%A, %B %d, %Y at %H:%M')} (UK)")
    parts.append("")

    # Add additional knowledge context if available
    if knowledge_context and knowledge_context.strip():
        parts.append(knowledge_context.strip())
        parts.append("")

    # Add recent conversation buffer (per-channel)
    recent = get_recent_context(channel_id)
    if recent:
        parts.append(recent)
        parts.append("")

    # Add current message
    parts.append("## Current Message")
    parts.append(message)

    # Add attachments if present
    if attachment_urls:
        parts.append("")
        parts.append("## Attachments")
        for att in attachment_urls:
            is_image = att.get("content_type", "").startswith("image/")
            if is_image:
                path = att.get("local_path") or att["url"]
                parts.append(f"- **Image:** `{att['filename']}` — Use the Read tool on this path to view: {path}")
            else:
                parts.append(f"- **File:** `{att['filename']}` ({att.get('content_type', 'unknown')}) — {att['url']}")
        if any(att.get("content_type", "").startswith("image/") for att in attachment_urls):
            parts.append("")
            parts.append("**IMPORTANT:** The user sent image(s). Use the Read tool with the path above to see the image content. This is essential for food logging, screenshots, and visual content.")

    return "\n".join(parts)


async def capture_message_pair(
    session_id: str,
    user_message: str,
    assistant_response: str,
    channel_id: str | None = None,
    message_id: str | None = None,
) -> bool:
    """Capture conversation exchange into Second Brain.

    On failure, queues the capture locally in capture_store for later replay.

    Args:
        session_id: Unique session identifier (e.g., discord-123)
        user_message: The user's message
        assistant_response: The assistant's response
        channel_id: Discord channel ID
        message_id: Discord message ID

    Returns:
        True if successfully captured, False on failure
    """
    try:
        from domains.second_brain.conversation import capture_conversation

        item = await capture_conversation(
            user_message=user_message,
            assistant_response=assistant_response,
            channel_id=channel_id or session_id,
            message_id=message_id,
        )

        if item:
            logger.info(f"Captured conversation to Second Brain: {item.id}")
            return True
        else:
            logger.debug("Conversation not captured (too short or failed)")
            return False

    except Exception as e:
        logger.error(f"Second Brain capture failed, queuing locally: {e}")
        try:
            from . import capture_store
            capture_store.add_capture(
                session_id=session_id,
                user_message=user_message,
                assistant_response=assistant_response,
                channel=channel_id or session_id,
            )
            logger.info("Capture queued locally for retry")
        except Exception as queue_err:
            logger.error(f"Local queue also failed: {queue_err}")
        return False


