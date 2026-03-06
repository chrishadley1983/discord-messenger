"""MCP Server for Second Brain — exposes knowledge search and management.

Provides read and write access to the Second Brain knowledge base
via Claude Desktop and Claude Code.

Usage:
    python mcp_servers/second_brain_mcp.py
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from uuid import UUID

# Add project root to path so we can import domains.second_brain
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from mcp.server.fastmcp import FastMCP

# Import Second Brain modules
from domains.second_brain import db
from domains.second_brain.types import KnowledgeItem, CaptureType, ContentType

mcp = FastMCP(
    "second-brain",
    instructions=(
        "Chris's personal knowledge base containing saved articles, project notes, "
        "preferences, family info, business data (Hadley Bricks LEGO resale), recipes, "
        "travel plans, and more. Use search_knowledge whenever the user asks about "
        "something they may have previously saved or discussed. Use save_to_brain "
        "when they want to remember something for later."
    ),
)


def _item_to_dict(item: KnowledgeItem) -> dict:
    """Convert a KnowledgeItem to a serializable dict."""
    return {
        "id": str(item.id),
        "title": item.title,
        "content_type": item.content_type.value if isinstance(item.content_type, ContentType) else item.content_type,
        "capture_type": item.capture_type.value if isinstance(item.capture_type, CaptureType) else item.capture_type,
        "source": item.source,
        "summary": item.summary,
        "topics": item.topics or [],
        "decay_score": round(item.decay_score, 3),
        "access_count": item.access_count,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "status": item.status.value if hasattr(item.status, "value") else str(item.status),
        "facts": item.facts or [],
        "concepts": item.concepts or [],
    }


# =============================================================================
# READ TOOLS
# =============================================================================

@mcp.tool()
async def search_knowledge(query: str, limit: int = 5, min_similarity: float = 0.7) -> str:
    """Search Chris's personal knowledge base (Second Brain) using semantic + keyword search.

    USE THIS TOOL when the user asks about their projects, preferences, past decisions,
    saved articles, bookmarks, family info, business details, or anything they may have
    previously saved. This is Chris's long-term memory across all topics.

    Covers: LEGO business (Hadley Bricks), coding projects, family notes, recipes,
    travel plans, articles, personal preferences, and more.

    Uses vector (semantic) search first, with automatic keyword fallback for exact
    matches that embeddings might miss (e.g. proper nouns, addresses, specific terms).

    Args:
        query: Natural language search query
        limit: Max results to return (default 5)
        min_similarity: Minimum similarity threshold 0-1 (default 0.7)
    """
    try:
        results = await db.hybrid_search(
            query=query,
            min_similarity=min_similarity,
            limit=limit,
        )

        if not results:
            return "No matching items found."

        output = []
        for r in results:
            item = r.item
            excerpts = "\n".join(f"  > {e}" for e in r.relevant_excerpts[:2])
            entry = (
                f"**{item.title or 'Untitled'}** (similarity: {r.best_similarity:.2f})\n"
                f"  Type: {item.content_type.value if hasattr(item.content_type, 'value') else item.content_type} | "
                f"Topics: {', '.join(item.topics or [])}\n"
                f"  Source: {item.source}\n"
                f"  Summary: {item.summary or 'N/A'}"
            )
            if item.facts:
                entry += "\n  Facts:\n" + "\n".join(f"    - {f}" for f in item.facts[:5])
            if item.concepts:
                entry += "\n  Concepts:\n" + "\n".join(
                    f"    - [{c.get('type', 'pattern')}] {c.get('label', '')}: {c.get('detail', '')}"
                    for c in item.concepts[:3]
                )
            if excerpts:
                entry += f"\n  Excerpts:\n{excerpts}"
            output.append(entry)

        return f"Found {len(results)} results:\n\n" + "\n\n---\n\n".join(output)

    except Exception as e:
        return f"Search failed: {e}"


@mcp.tool()
async def get_recent_items(limit: int = 10, days_back: int = 7) -> str:
    """Get recently saved items from Chris's knowledge base.

    Use when the user asks "what have I saved recently?" or wants to review
    recent captures, bookmarks, or notes.

    Args:
        limit: Max items to return (default 10)
        days_back: How many days back to look (default 7)
    """
    try:
        since = datetime.now(timezone.utc) - timedelta(days=days_back)
        items = await db.get_items_since(since)
        items = items[:limit]

        if not items:
            return f"No items found in the last {days_back} days."

        output = []
        for item in items:
            output.append(
                f"- **{item.title or 'Untitled'}** ({item.content_type.value if hasattr(item.content_type, 'value') else item.content_type})\n"
                f"  Topics: {', '.join(item.topics or [])}\n"
                f"  Created: {item.created_at.strftime('%Y-%m-%d %H:%M') if item.created_at else 'unknown'}\n"
                f"  Source: {item.source}"
            )

        return f"Recent items ({len(items)}):\n\n" + "\n\n".join(output)

    except Exception as e:
        return f"Failed to get recent items: {e}"


@mcp.tool()
async def browse_topics() -> str:
    """List all topics in Chris's knowledge base with item counts.

    Use when the user asks what's in their knowledge base, wants to explore
    by category, or asks "what topics do you know about?"."""
    try:
        topics = await db.get_topics_with_counts()

        if not topics:
            return "No topics found."

        # Sort by count descending
        topics.sort(key=lambda x: x[1], reverse=True)

        lines = [f"- {topic}: {count} items" for topic, count in topics]
        return f"Topics ({len(topics)}):\n\n" + "\n".join(lines)

    except Exception as e:
        return f"Failed to browse topics: {e}"


@mcp.tool()
async def get_item_detail(item_id: str) -> str:
    """Get the full text, summary, and connections for a specific knowledge item.

    Use after search_knowledge returns a relevant item and you need the complete content.

    Args:
        item_id: UUID of the knowledge item (from search_knowledge or list_items results)
    """
    try:
        item = await db.get_knowledge_item(UUID(item_id))
        if not item:
            return f"Item {item_id} not found."

        # Boost access count
        await db.boost_access(UUID(item_id))

        # Get connections
        connections = await db.get_connections_for_item(UUID(item_id))

        result = _item_to_dict(item)
        result["full_text"] = item.full_text
        result["user_note"] = item.user_note
        result["word_count"] = item.word_count
        result["connections"] = [
            {
                "connected_to": str(c.item_b_id if str(c.item_a_id) == item_id else c.item_a_id),
                "type": c.connection_type.value if hasattr(c.connection_type, "value") else str(c.connection_type),
                "description": c.description,
                "similarity": round(c.similarity_score, 3) if c.similarity_score else None,
            }
            for c in connections
        ]

        return json.dumps(result, indent=2, default=str)

    except ValueError:
        return f"Invalid UUID: {item_id}"
    except Exception as e:
        return f"Failed to get item detail: {e}"


# =============================================================================
# BROWSE TOOLS
# =============================================================================

@mcp.tool()
async def list_items(
    limit: int = 20,
    offset: int = 0,
    content_type: str = "",
    topic: str = "",
    sort_by: str = "created_at",
    order: str = "desc",
) -> str:
    """Browse and filter items in Chris's knowledge base with pagination.

    Use when the user wants to see all items of a certain type or topic,
    or browse their saved knowledge systematically.

    Args:
        limit: Max items per page (default 20)
        offset: Pagination offset (default 0)
        content_type: Filter by type (article, note, recipe, video, etc.)
        topic: Filter by topic name
        sort_by: Sort field (created_at, title, access_count, decay_score)
        order: Sort order (asc or desc)
    """
    try:
        items, total = await db.list_items(
            limit=limit,
            offset=offset,
            content_type=content_type or None,
            topic=topic or None,
            sort_by=sort_by,
            order=order,
        )

        if not items:
            return "No items found matching filters."

        lines = []
        for item in items:
            lines.append(
                f"- [{item.id}] **{item.title or 'Untitled'}** "
                f"({item.content_type.value if hasattr(item.content_type, 'value') else item.content_type})\n"
                f"  Topics: {', '.join(item.topics or [])} | "
                f"Decay: {item.decay_score:.2f} | "
                f"Created: {item.created_at.strftime('%Y-%m-%d') if item.created_at else '?'}"
            )

        header = f"Items {offset+1}-{offset+len(items)} of {total}"
        if content_type:
            header += f" (type: {content_type})"
        if topic:
            header += f" (topic: {topic})"

        return header + "\n\n" + "\n\n".join(lines)

    except Exception as e:
        return f"Failed to list items: {e}"


# =============================================================================
# WRITE TOOLS
# =============================================================================

@mcp.tool()
async def save_to_brain(content: str, note: str = "", tags: str = "") -> str:
    """Save a URL or text to Chris's knowledge base for long-term recall.

    Use when the user says "remember this", "save this", shares a URL to keep,
    or wants to store information for later. Content is automatically summarised,
    chunked, and made searchable.

    Args:
        content: A URL to capture, or direct text content
        note: Optional personal note to attach
        tags: Optional comma-separated tags (e.g. "lego,business,pricing")
    """
    try:
        from domains.second_brain.pipeline import process_capture

        user_tags = [t.strip() for t in tags.split(",") if t.strip()] if tags else None

        item = await process_capture(
            source=content,
            capture_type=CaptureType.EXPLICIT,
            user_note=note or None,
            user_tags=user_tags,
            source_system="mcp:claude-code",
        )

        if not item:
            return "Failed to save — pipeline returned no item."

        return (
            f"Saved to Second Brain!\n"
            f"  ID: {item.id}\n"
            f"  Title: {item.title}\n"
            f"  Type: {item.content_type.value if hasattr(item.content_type, 'value') else item.content_type}\n"
            f"  Topics: {', '.join(item.topics or [])}\n"
            f"  Summary: {item.summary or 'N/A'}"
        )

    except Exception as e:
        return f"Save failed: {e}"


if __name__ == "__main__":
    mcp.run()
