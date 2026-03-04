"""Conversation capture for Second Brain.

Captures Discord conversation pairs (user message + assistant response)
as structured knowledge items with facts and concepts extraction.
"""

from typing import Optional

from logger import logger
from .types import CaptureType, ContentType, KnowledgeItem
from .pipeline import process_capture


async def capture_conversation(
    user_message: str,
    assistant_response: str,
    channel_id: str | None = None,
    message_id: str | None = None,
) -> Optional[KnowledgeItem]:
    """Capture a conversation exchange into Second Brain.

    Combines user message and assistant response into structured text,
    then runs through the full pipeline (title, summary, topics,
    structured extraction, chunking, embedding, storage).

    Args:
        user_message: The user's message text
        assistant_response: The assistant's response text
        channel_id: Discord channel ID (stored in user_note for context)
        message_id: Discord message ID (stored as source_message_id)

    Returns:
        Created KnowledgeItem or None if failed/skipped
    """
    # Skip trivially short exchanges
    combined_length = len(user_message) + len(assistant_response)
    if combined_length < 50:
        logger.debug("Conversation too short for capture, skipping")
        return None

    # Format as structured conversation text
    text = _format_conversation(user_message, assistant_response)

    # Build context note
    context = f"Discord channel: {channel_id}" if channel_id else None

    # Build a deterministic source ID for dedup (CR-002)
    source_id = f"discord://{channel_id or 'unknown'}/{message_id or 'unknown'}"

    try:
        item = await process_capture(
            source=source_id,
            text=text,
            capture_type=CaptureType.PASSIVE,
            user_note=context,
            content_type_override=ContentType.CONVERSATION_EXTRACT,
            source_message_id=message_id,
            source_system="discord",
        )

        if item:
            logger.info(
                f"Captured conversation: {item.title or 'untitled'} "
                f"({len(item.facts)} facts, {len(item.concepts)} concepts)"
            )
        return item

    except Exception as e:
        logger.error(f"Conversation capture failed: {e}")
        return None


def _format_conversation(user_message: str, assistant_response: str) -> str:
    """Format a conversation pair as structured text for the pipeline."""
    return (
        f"User: {user_message}\n\n"
        f"Assistant: {assistant_response}"
    )
