"""Contextual surfacing for Second Brain.

Injects relevant knowledge items into Peter's context when responding
to user messages. Surfaces items that match the current conversation
topic with sufficient similarity and decay score.
"""

from typing import Optional

from logger import logger
from .types import KnowledgeItem, SearchResult
from .config import (
    SIMILARITY_THRESHOLD,
    MAX_CONTEXT_ITEMS,
    SEARCH_MIN_DECAY,
)
from .db import semantic_search, boost_access


async def get_relevant_context(
    message: str,
    max_items: int = MAX_CONTEXT_ITEMS,
    min_similarity: float = SIMILARITY_THRESHOLD,
    min_decay: float = SEARCH_MIN_DECAY,
) -> list[SearchResult]:
    """Get relevant knowledge items for a user message.

    Called before Claude Code processes a message to inject
    relevant context from the Second Brain.

    Args:
        message: User's message text
        max_items: Maximum items to return
        min_similarity: Minimum similarity threshold
        min_decay: Minimum decay score (filter out stale items)

    Returns:
        List of relevant SearchResult objects
    """
    if not message or len(message) < 10:
        return []

    try:
        results = await semantic_search(
            query=message,
            min_similarity=min_similarity,
            min_decay_score=min_decay,
            limit=max_items,
        )

        # Boost access for surfaced items
        for result in results:
            if result.item.id:
                try:
                    await boost_access(result.item.id)
                except Exception:
                    pass  # Non-critical

        if results:
            logger.info(f"Surfacing {len(results)} items for message: {message[:50]}...")

        return results

    except Exception as e:
        logger.warning(f"Contextual surfacing failed: {e}")
        return []


def format_context_for_claude(results: list[SearchResult]) -> str:
    """Format search results as context for Claude.

    Generates a concise context block that can be injected
    into the prompt without being too verbose.

    Args:
        results: Search results to format

    Returns:
        Formatted context string
    """
    if not results:
        return ""

    lines = [
        "## Relevant Knowledge (from Second Brain)",
        "",
    ]

    for i, result in enumerate(results, 1):
        item = result.item
        similarity = int(result.best_similarity * 100)

        # Title and similarity
        title = item.title or "Untitled"
        if len(title) > 60:
            title = title[:57] + "..."
        lines.append(f"### {i}. {title} ({similarity}% match)")

        # Summary (most important)
        if item.summary:
            lines.append(item.summary)

        # Best matching excerpt if different from summary
        if result.relevant_excerpts:
            excerpt = result.relevant_excerpts[0]
            if excerpt and excerpt != item.summary:
                lines.append(f"\n> {excerpt[:200]}...")

        # Source
        if item.source and item.source.startswith('http'):
            lines.append(f"\nSource: {item.source}")

        # Tags
        if item.topics:
            tags = ", ".join(item.topics[:5])
            lines.append(f"Tags: {tags}")

        lines.append("")

    # Add instruction for Claude
    lines.extend([
        "---",
        "*Reference this knowledge naturally if relevant to the user's question.*",
        "*Don't mention 'Second Brain' explicitly unless asked.*",
    ])

    return "\n".join(lines)


def format_context_compact(results: list[SearchResult]) -> str:
    """Format results in a more compact form for token efficiency.

    Args:
        results: Search results to format

    Returns:
        Compact formatted string
    """
    if not results:
        return ""

    lines = ["[CONTEXT]"]

    for result in results:
        item = result.item
        title = item.title or "Untitled"
        if len(title) > 50:
            title = title[:47] + "..."

        # One line per item: title | summary
        summary = (item.summary or "")[:150]
        lines.append(f"• {title}: {summary}")

    lines.append("[/CONTEXT]")

    return "\n".join(lines)


async def should_surface(message: str) -> bool:
    """Quick check if surfacing might be useful for this message.

    Pre-filter before the more expensive semantic search.

    Args:
        message: User message

    Returns:
        True if surfacing should be attempted
    """
    if not message:
        return False

    # Skip very short messages
    if len(message.split()) < 3:
        return False

    # Skip greetings and simple phrases
    simple_phrases = [
        'hi', 'hello', 'hey', 'thanks', 'thank you', 'bye', 'goodbye',
        'ok', 'okay', 'sure', 'yes', 'no', 'maybe',
    ]
    message_lower = message.lower().strip()
    if message_lower in simple_phrases:
        return False

    # Skip command-like messages
    if message.startswith(('!', '/', '@')):
        return False

    return True


async def get_context_for_message(message: str) -> str:
    """High-level function to get formatted context for a message.

    Combines should_surface check, retrieval, and formatting.

    Args:
        message: User message

    Returns:
        Formatted context string (empty if none found)
    """
    if not await should_surface(message):
        return ""

    results = await get_relevant_context(message)

    if not results:
        return ""

    return format_context_for_claude(results)
