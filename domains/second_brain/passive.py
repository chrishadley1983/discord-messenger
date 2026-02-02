"""Passive capture detection for Second Brain.

Detects URLs and ideas in regular messages and captures them
with low priority (0.3) for later retrieval.
"""

import re
from typing import Optional

from logger import logger
from .types import PassiveCaptureMatch
from .config import IDEA_SIGNAL_PHRASES, EXCLUDE_PATTERNS
from .pipeline import process_passive_capture


# URL pattern - matches common URL formats
URL_PATTERN = re.compile(
    r'https?://[^\s<>"\')\]]+',
    re.IGNORECASE
)

# Excluded domains (don't capture links to Discord, local, etc.)
EXCLUDED_DOMAINS = [
    'discord.com',
    'discordapp.com',
    'discord.gg',
    'localhost',
    '127.0.0.1',
    'tenor.com',  # GIFs
    'giphy.com',
]

# Min message length for idea detection (words)
MIN_IDEA_LENGTH = 5


def detect_passive_captures(message: str) -> list[PassiveCaptureMatch]:
    """Detect URLs and ideas worth passively capturing.

    Args:
        message: Discord message content

    Returns:
        List of detected passive captures
    """
    captures = []
    message_lower = message.lower().strip()

    # Skip if message is a question/command to Peter
    if _is_question_or_command(message_lower):
        return captures

    # Detect URLs
    urls = detect_urls(message)
    for url in urls:
        if not _is_excluded_url(url):
            captures.append(PassiveCaptureMatch(url=url))

    # Detect ideas (only if no URLs found - avoid double-capture)
    if not urls:
        idea = detect_idea(message)
        if idea:
            captures.append(PassiveCaptureMatch(idea_text=idea))

    return captures


def detect_urls(message: str) -> list[str]:
    """Extract URLs from message.

    Args:
        message: Message content

    Returns:
        List of URL strings
    """
    # Find all URLs
    matches = URL_PATTERN.findall(message)

    # Clean up URLs (remove trailing punctuation)
    cleaned = []
    for url in matches:
        # Remove common trailing chars that get captured
        url = url.rstrip('.,;:!?')
        # Remove trailing paren if not balanced
        if url.endswith(')') and url.count('(') < url.count(')'):
            url = url[:-1]
        cleaned.append(url)

    return cleaned


def detect_idea(message: str) -> Optional[str]:
    """Detect if message contains an idea worth capturing.

    Looks for signal phrases that indicate the user is expressing
    an idea, thought, or note to self.

    Args:
        message: Message content

    Returns:
        The idea text if detected, None otherwise
    """
    message_lower = message.lower()

    # Check for signal phrases
    signal_found = None
    for phrase in IDEA_SIGNAL_PHRASES:
        if phrase in message_lower:
            signal_found = phrase
            break

    if not signal_found:
        return None

    # Check minimum length
    words = message.split()
    if len(words) < MIN_IDEA_LENGTH:
        return None

    return message


def _is_question_or_command(message_lower: str) -> bool:
    """Check if message is a question or command to Peter.

    These shouldn't be captured as knowledge - they're requests,
    not information to store.
    """
    for pattern in EXCLUDE_PATTERNS:
        if pattern in message_lower:
            return True

    # Also exclude if starts with a command prefix
    if message_lower.startswith(('!', '/', 'hey peter', 'peter,')):
        return True

    return False


def _is_excluded_url(url: str) -> bool:
    """Check if URL should be excluded from capture."""
    url_lower = url.lower()

    for domain in EXCLUDED_DOMAINS:
        if domain in url_lower:
            return True

    return False


async def process_passive_message(
    message: str,
    channel_name: str = None,
) -> list[str]:
    """Process a message for passive captures.

    Called from the message handler to detect and capture
    URLs/ideas passively.

    Args:
        message: Discord message content
        channel_name: Optional channel name for context

    Returns:
        List of item IDs for created passive captures
    """
    captures = detect_passive_captures(message)

    if not captures:
        return []

    created_ids = []
    context = f"From #{channel_name}" if channel_name else None

    for capture in captures:
        try:
            if capture.url:
                logger.info(f"Passive URL capture: {capture.url}")
                item = await process_passive_capture(capture.url, context=context)
            elif capture.idea_text:
                logger.info(f"Passive idea capture: {capture.idea_text[:50]}...")
                item = await process_passive_capture(capture.idea_text, context=context)
            else:
                continue

            if item and item.id:
                created_ids.append(item.id)

        except Exception as e:
            logger.warning(f"Passive capture failed: {e}")
            continue

    return created_ids


def should_capture_message(message: str) -> bool:
    """Quick check if message might contain capturable content.

    Fast pre-filter before more expensive detection.

    Args:
        message: Message content

    Returns:
        True if message might have capturable content
    """
    # Has URL?
    if 'http' in message.lower():
        return True

    # Has idea signal?
    message_lower = message.lower()
    for phrase in IDEA_SIGNAL_PHRASES:
        if phrase in message_lower:
            return True

    return False
