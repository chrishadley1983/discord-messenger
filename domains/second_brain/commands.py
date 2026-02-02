"""Discord command handlers for Second Brain.

Provides:
- /save <url|text> - Explicit knowledge capture
- /recall <query> - Semantic search
- /knowledge - Stats and recent items
"""

import re
from datetime import datetime, timezone
from typing import Optional

from logger import logger
from .types import CaptureType, KnowledgeItem, SearchResult
from .pipeline import process_capture
from .db import (
    semantic_search,
    get_recent_items,
    get_total_active_count,
    get_total_connection_count,
    get_topics_with_counts,
    boost_access,
)


async def handle_save(
    content: str,
    user_note: Optional[str] = None,
    user_tags: Optional[list[str]] = None,
) -> str:
    """Handle !save / /save command.

    Args:
        content: URL or text to save
        user_note: Optional user annotation
        user_tags: Optional user-provided tags

    Returns:
        Discord response message
    """
    if not content or not content.strip():
        return "**Usage:** `/save <url or text>`\n\nExamples:\n- `/save https://example.com/article`\n- `/save Great idea: use semantic search for knowledge retrieval`"

    content = content.strip()
    logger.info(f"Processing save command: {content[:100]}...")

    try:
        item = await process_capture(
            source=content,
            capture_type=CaptureType.EXPLICIT,
            user_note=user_note,
            user_tags=user_tags,
        )

        if not item:
            return "❌ Failed to save content. Please try again."

        # Format response
        response_lines = [
            "✅ **Saved to Second Brain**",
            "",
            f"**{item.title}**" if item.title else "",
        ]

        if item.summary:
            response_lines.append(f"> {item.summary[:200]}...")

        if item.topics:
            tags_str = " ".join(f"`{t}`" for t in item.topics[:5])
            response_lines.append(f"\n🏷️ {tags_str}")

        if item.word_count:
            response_lines.append(f"📄 {item.word_count} words")

        return "\n".join(line for line in response_lines if line is not None)

    except Exception as e:
        logger.error(f"Save command failed: {e}")
        return f"❌ Error saving content: {str(e)[:100]}"


async def handle_recall(
    query: str,
    limit: int = 5,
) -> str:
    """Handle !recall / /recall command.

    Args:
        query: Semantic search query
        limit: Max results to return

    Returns:
        Discord response message
    """
    if not query or not query.strip():
        return "**Usage:** `/recall <query>`\n\nExamples:\n- `/recall LEGO investing strategies`\n- `/recall marathon training nutrition`"

    query = query.strip()
    logger.info(f"Processing recall command: {query}")

    try:
        results = await semantic_search(
            query=query,
            limit=limit,
        )

        if not results:
            return f"🔍 No matches found for: *{query}*\n\nTry a different query or save more content with `/save`."

        # Format results
        response_lines = [
            f"🧠 **Found {len(results)} result{'s' if len(results) > 1 else ''}** for: *{query}*",
            "",
        ]

        for i, result in enumerate(results, 1):
            item = result.item
            similarity_pct = int(result.best_similarity * 100)

            # Title with similarity
            title = item.title or "Untitled"
            if len(title) > 50:
                title = title[:47] + "..."
            response_lines.append(f"**{i}. {title}** ({similarity_pct}% match)")

            # Excerpt
            if result.relevant_excerpts:
                excerpt = result.relevant_excerpts[0][:150]
                if len(result.relevant_excerpts[0]) > 150:
                    excerpt += "..."
                response_lines.append(f"> {excerpt}")

            # Tags
            if item.topics:
                tags = " ".join(f"`{t}`" for t in item.topics[:3])
                response_lines.append(f"🏷️ {tags}")

            # Source
            if item.source and item.source.startswith('http'):
                response_lines.append(f"🔗 <{item.source}>")

            response_lines.append("")

            # Boost access count for returned items
            if item.id:
                try:
                    await boost_access(item.id)
                except Exception:
                    pass  # Non-critical

        return "\n".join(response_lines)

    except Exception as e:
        logger.error(f"Recall command failed: {e}")
        return f"❌ Search failed: {str(e)[:100]}"


async def handle_knowledge() -> str:
    """Handle !knowledge / /knowledge command - show stats.

    Returns:
        Discord response message with stats
    """
    try:
        # Fetch stats
        total_items = await get_total_active_count()
        total_connections = await get_total_connection_count()
        recent = await get_recent_items(limit=5)
        topics = await get_topics_with_counts()

        # Format response
        response_lines = [
            "🧠 **Second Brain Stats**",
            "",
            f"📚 **{total_items}** knowledge items",
            f"🔗 **{total_connections}** connections discovered",
            "",
        ]

        # Top topics
        if topics:
            top_topics = sorted(topics, key=lambda x: x[1], reverse=True)[:8]
            topics_str = " ".join(f"`{t}` ({c})" for t, c in top_topics)
            response_lines.append(f"🏷️ **Top topics:** {topics_str}")
            response_lines.append("")

        # Recent items
        if recent:
            response_lines.append("📝 **Recent saves:**")
            for item in recent[:5]:
                title = item.title or "Untitled"
                if len(title) > 40:
                    title = title[:37] + "..."

                # Format date
                if item.created_at:
                    if isinstance(item.created_at, str):
                        from dateutil.parser import parse
                        dt = parse(item.created_at)
                    else:
                        dt = item.created_at
                    date_str = dt.strftime("%d %b")
                else:
                    date_str = "Unknown"

                capture_icon = "💾" if item.capture_type == CaptureType.EXPLICIT else "👁️"
                response_lines.append(f"{capture_icon} {title} ({date_str})")

        # Commands hint
        response_lines.extend([
            "",
            "**Commands:**",
            "- `/save <url|text>` - Save content",
            "- `/recall <query>` - Semantic search",
        ])

        return "\n".join(response_lines)

    except Exception as e:
        logger.error(f"Knowledge command failed: {e}")
        return f"❌ Failed to load stats: {str(e)[:100]}"


def extract_tags_from_message(message: str) -> tuple[str, list[str]]:
    """Extract hashtags from message content.

    Args:
        message: User message

    Returns:
        Tuple of (content_without_tags, list_of_tags)
    """
    # Find hashtags at the end of message
    tag_pattern = re.compile(r'#([a-zA-Z0-9_-]+)\s*$')

    tags = []
    content = message

    while True:
        match = tag_pattern.search(content)
        if match:
            tags.append(match.group(1).lower())
            content = content[:match.start()].strip()
        else:
            break

    return content, list(reversed(tags))  # Preserve original order


def extract_note_from_message(message: str) -> tuple[str, Optional[str]]:
    """Extract user note (after ||) from message.

    Args:
        message: User message

    Returns:
        Tuple of (content, note_or_none)
    """
    if "||" in message:
        parts = message.split("||", 1)
        return parts[0].strip(), parts[1].strip()
    return message, None
