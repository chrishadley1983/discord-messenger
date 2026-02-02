"""Connection discovery for Second Brain.

Finds semantic connections between knowledge items:
- SEMANTIC: High embedding similarity between chunks
- TOPIC_OVERLAP: Shared tags/topics
- CROSS_DOMAIN: Different domains but related (most valuable)

Cross-domain connections are especially valuable as they surface
unexpected relationships between different areas of knowledge.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from logger import logger
from .types import (
    KnowledgeItem,
    KnowledgeConnection,
    ConnectionType,
)
from .config import (
    CONNECTION_THRESHOLD,
    KNOWN_DOMAIN_TAGS,
)
from .db import (
    semantic_search,
    get_recent_items,
    insert_connection,
    connection_exists,
    get_connections_for_item,
    get_unsurfaced_connections,
    mark_connection_surfaced,
)
from .embed import generate_embedding


# Domain groupings for cross-domain detection
DOMAIN_GROUPS = {
    'business': {'hadley-bricks', 'ebay', 'bricklink', 'brick-owl', 'amazon', 'finance', 'tax', 'self-employment'},
    'lego': {'lego', 'lego-investing', 'retired-sets', 'minifigures', 'hadley-bricks'},
    'fitness': {'running', 'marathon', 'training', 'nutrition', 'garmin'},
    'family': {'family', 'max', 'emmie', 'abby', 'japan-trip'},
    'tech': {'tech', 'development', 'peterbot', 'familyfuel'},
}


async def discover_connections_for_item(
    item: KnowledgeItem,
    min_similarity: float = CONNECTION_THRESHOLD,
) -> list[KnowledgeConnection]:
    """Discover connections for a newly saved item.

    Searches for similar items and creates connections where
    similarity exceeds threshold.

    Args:
        item: The item to find connections for
        min_similarity: Minimum similarity for connection

    Returns:
        List of created connections
    """
    if not item.id:
        logger.warning("Cannot discover connections for item without ID")
        return []

    logger.info(f"Discovering connections for: {item.title or item.id}")
    connections = []

    # Build search query from title + summary
    search_text = f"{item.title or ''} {item.summary or ''}"
    if not search_text.strip():
        logger.warning("Item has no title/summary for connection search")
        return []

    try:
        # Search for similar items (excluding self)
        results = await semantic_search(
            query=search_text,
            min_similarity=min_similarity,
            exclude_parent_id=UUID(item.id) if isinstance(item.id, str) else item.id,
            limit=10,
        )

        for result in results:
            other_item = result.item
            similarity = result.best_similarity

            # Determine connection type
            conn_type = _determine_connection_type(item, other_item)

            # Skip if connection already exists
            if await connection_exists(
                UUID(item.id) if isinstance(item.id, str) else item.id,
                UUID(other_item.id) if isinstance(other_item.id, str) else other_item.id
            ):
                continue

            # Create connection
            description = _generate_connection_description(item, other_item, conn_type)

            conn = await insert_connection(
                item_a_id=UUID(item.id) if isinstance(item.id, str) else item.id,
                item_b_id=UUID(other_item.id) if isinstance(other_item.id, str) else other_item.id,
                connection_type=conn_type,
                description=description,
                similarity_score=similarity,
            )

            if conn:
                connections.append(conn)
                logger.info(
                    f"Created {conn_type.value} connection: "
                    f"{item.title[:30] if item.title else 'Untitled'} <-> "
                    f"{other_item.title[:30] if other_item.title else 'Untitled'} "
                    f"({similarity:.2f})"
                )

    except Exception as e:
        logger.error(f"Connection discovery failed: {e}")

    return connections


async def batch_discover_connections(
    limit: int = 20,
    min_similarity: float = CONNECTION_THRESHOLD,
) -> int:
    """Run connection discovery on recent items.

    Useful for periodic batch processing.

    Args:
        limit: Max items to process
        min_similarity: Minimum similarity threshold

    Returns:
        Number of new connections created
    """
    logger.info(f"Running batch connection discovery (limit={limit})")

    try:
        recent = await get_recent_items(limit=limit)
    except Exception as e:
        logger.error(f"Failed to get recent items: {e}")
        return 0

    total_connections = 0

    for item in recent:
        connections = await discover_connections_for_item(item, min_similarity)
        total_connections += len(connections)

        # Small delay to avoid rate limiting
        await asyncio.sleep(0.5)

    logger.info(f"Batch discovery complete: {total_connections} new connections")
    return total_connections


def _determine_connection_type(
    item_a: KnowledgeItem,
    item_b: KnowledgeItem,
) -> ConnectionType:
    """Determine the type of connection between two items.

    Priority:
    1. CROSS_DOMAIN - Different domains but related (most valuable)
    2. TOPIC_OVERLAP - Shared tags/topics
    3. SEMANTIC - Default for high similarity
    """
    topics_a = set(item_a.topics or [])
    topics_b = set(item_b.topics or [])

    # Check for cross-domain connection
    domains_a = _get_item_domains(topics_a)
    domains_b = _get_item_domains(topics_b)

    if domains_a and domains_b:
        # Cross-domain if in different domain groups
        if not domains_a.intersection(domains_b):
            return ConnectionType.CROSS_DOMAIN

    # Check for topic overlap
    overlap = topics_a.intersection(topics_b)
    if overlap:
        return ConnectionType.TOPIC_OVERLAP

    # Default to semantic
    return ConnectionType.SEMANTIC


def _get_item_domains(topics: set[str]) -> set[str]:
    """Get domain groups for a set of topics."""
    domains = set()

    for group_name, group_tags in DOMAIN_GROUPS.items():
        if topics.intersection(group_tags):
            domains.add(group_name)

    return domains


def _generate_connection_description(
    item_a: KnowledgeItem,
    item_b: KnowledgeItem,
    conn_type: ConnectionType,
) -> str:
    """Generate human-readable connection description."""
    topics_a = set(item_a.topics or [])
    topics_b = set(item_b.topics or [])

    if conn_type == ConnectionType.CROSS_DOMAIN:
        domains_a = _get_item_domains(topics_a)
        domains_b = _get_item_domains(topics_b)
        domain_a = next(iter(domains_a)) if domains_a else "unknown"
        domain_b = next(iter(domains_b)) if domains_b else "unknown"
        return f"Cross-domain connection between {domain_a} and {domain_b}"

    elif conn_type == ConnectionType.TOPIC_OVERLAP:
        overlap = topics_a.intersection(topics_b)
        shared = list(overlap)[:3]
        return f"Shared topics: {', '.join(shared)}"

    else:
        return "Semantically similar content"


async def get_item_connections(item_id: str) -> list[tuple[KnowledgeConnection, KnowledgeItem]]:
    """Get all connections for an item with the connected items.

    Args:
        item_id: Item ID to find connections for

    Returns:
        List of (connection, connected_item) tuples
    """
    from .db import get_knowledge_item

    connections = await get_connections_for_item(UUID(item_id))
    results = []

    for conn in connections:
        # Determine which is the "other" item
        other_id = conn.item_b_id if str(conn.item_a_id) == item_id else conn.item_a_id

        try:
            other_item = await get_knowledge_item(other_id)
            if other_item:
                results.append((conn, other_item))
        except Exception:
            continue

    return results


async def surface_new_connections(
    max_connections: int = 3,
) -> list[tuple[KnowledgeConnection, KnowledgeItem, KnowledgeItem]]:
    """Get new connections that haven't been shown to user yet.

    For weekly digest or proactive surfacing.

    Args:
        max_connections: Maximum connections to return

    Returns:
        List of (connection, item_a, item_b) tuples
    """
    from .db import get_knowledge_item

    connections = await get_unsurfaced_connections()
    results = []

    for conn in connections[:max_connections]:
        try:
            item_a = await get_knowledge_item(conn.item_a_id)
            item_b = await get_knowledge_item(conn.item_b_id)

            if item_a and item_b:
                results.append((conn, item_a, item_b))

                # Mark as surfaced
                await mark_connection_surfaced(conn.id)

        except Exception as e:
            logger.warning(f"Failed to fetch connection items: {e}")
            continue

    return results


def format_connection_for_discord(
    conn: KnowledgeConnection,
    item_a: KnowledgeItem,
    item_b: KnowledgeItem,
) -> str:
    """Format a connection for Discord display.

    Args:
        conn: The connection
        item_a: First item
        item_b: Second item

    Returns:
        Formatted string for Discord
    """
    icon = {
        ConnectionType.CROSS_DOMAIN: "🔀",
        ConnectionType.TOPIC_OVERLAP: "🏷️",
        ConnectionType.SEMANTIC: "🔗",
    }.get(conn.connection_type, "🔗")

    title_a = item_a.title[:40] if item_a.title else "Untitled"
    title_b = item_b.title[:40] if item_b.title else "Untitled"

    similarity = int((conn.similarity_score or 0) * 100)

    lines = [
        f"{icon} **Connection Discovered** ({similarity}% match)",
        f"",
        f"📄 **{title_a}**",
        f"↔️",
        f"📄 **{title_b}**",
    ]

    if conn.description:
        lines.append(f"")
        lines.append(f"*{conn.description}*")

    return "\n".join(lines)
