"""Weekly digest for Second Brain.

Generates a weekly summary of:
- New items added
- New connections discovered
- Items that are fading (need review)
- Top topics
- Overall stats
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from logger import logger
from .types import DigestData, KnowledgeItem, KnowledgeConnection
from .db import (
    get_items_since,
    get_total_active_count,
    get_total_connection_count,
    get_topics_with_counts,
    get_fading_but_relevant_items,
    get_most_accessed_item_since,
)
from .connections import surface_new_connections


async def generate_weekly_digest() -> DigestData:
    """Generate weekly digest data.

    Returns:
        DigestData with all digest components
    """
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    logger.info("Generating weekly Second Brain digest")

    try:
        # Get new items from the past week
        new_items = await get_items_since(week_ago)

        # Get new connections (unsurfaced)
        new_connections_data = await surface_new_connections(max_connections=5)
        new_connections = [conn for conn, _, _ in new_connections_data]

        # Get fading items that need attention
        fading_items = await get_fading_but_relevant_items(limit=5)

        # Get overall stats
        total_items = await get_total_active_count()
        total_connections = await get_total_connection_count()

        # Get most accessed item this week
        most_accessed = await get_most_accessed_item_since(week_ago)

        return DigestData(
            new_items=new_items,
            new_connections=new_connections,
            fading_items=fading_items,
            total_items=total_items,
            total_connections=total_connections,
            most_accessed_item=most_accessed,
        )

    except Exception as e:
        logger.error(f"Failed to generate digest: {e}")
        # Return empty digest on error
        return DigestData(
            new_items=[],
            new_connections=[],
            fading_items=[],
            total_items=0,
            total_connections=0,
        )


def format_digest_for_discord(data: DigestData) -> str:
    """Format digest data for Discord.

    Args:
        data: DigestData from generate_weekly_digest

    Returns:
        Formatted string for Discord
    """
    lines = [
        "# 🧠 Weekly Second Brain Digest",
        "",
    ]

    # Stats summary
    lines.extend([
        f"**Total Knowledge:** {data.total_items} items | {data.total_connections} connections",
        "",
    ])

    # New items this week
    if data.new_items:
        lines.extend([
            f"## 📥 New This Week ({len(data.new_items)} items)",
            "",
        ])
        for item in data.new_items[:5]:
            title = item.title[:50] if item.title else "Untitled"
            if len(item.title or "") > 50:
                title += "..."
            icon = "💾" if item.capture_type.value == "explicit" else "👁️"
            lines.append(f"{icon} {title}")
        if len(data.new_items) > 5:
            lines.append(f"*...and {len(data.new_items) - 5} more*")
        lines.append("")

    # New connections
    if data.new_connections:
        lines.extend([
            f"## 🔗 Connections Discovered ({len(data.new_connections)})",
            "",
        ])
        for conn in data.new_connections[:3]:
            conn_type_icon = {
                "cross_domain": "🔀",
                "topic_overlap": "🏷️",
                "semantic": "🔗",
            }.get(conn.connection_type.value, "🔗")

            desc = conn.description or "Semantically similar"
            similarity = int((conn.similarity_score or 0) * 100)
            lines.append(f"{conn_type_icon} {desc} ({similarity}% match)")
        lines.append("")

    # Fading items
    if data.fading_items:
        lines.extend([
            "## ⏳ Fading Knowledge (consider revisiting)",
            "",
        ])
        for item in data.fading_items[:3]:
            title = item.title[:40] if item.title else "Untitled"
            if len(item.title or "") > 40:
                title += "..."
            decay_pct = int(item.decay_score * 100)
            lines.append(f"- {title} ({decay_pct}% relevance)")
        lines.append("")
        lines.append("*Use `/recall` to revisit these and boost their relevance*")
        lines.append("")

    # Most accessed
    if data.most_accessed_item:
        item = data.most_accessed_item
        title = item.title[:40] if item.title else "Untitled"
        lines.extend([
            "## ⭐ Most Accessed This Week",
            f"**{title}** ({item.access_count} accesses)",
            "",
        ])

    # No activity message
    if not data.new_items and not data.new_connections:
        lines.extend([
            "*No new knowledge captured this week.*",
            "",
            "Try using `/save` to capture interesting URLs and ideas!",
            "",
        ])

    # Commands reminder
    lines.extend([
        "---",
        "**Commands:** `/save` `/recall` `/knowledge`",
    ])

    return "\n".join(lines)


async def get_digest_for_skill() -> dict:
    """Get digest data formatted for skill data fetcher.

    Used by the weekly-knowledge-digest skill.

    Returns:
        Dict with digest data for skill template
    """
    data = await generate_weekly_digest()

    return {
        "total_items": data.total_items,
        "total_connections": data.total_connections,
        "new_items_count": len(data.new_items),
        "new_items": [
            {
                "title": item.title or "Untitled",
                "capture_type": item.capture_type.value,
                "topics": item.topics[:3] if item.topics else [],
            }
            for item in data.new_items[:5]
        ],
        "new_connections_count": len(data.new_connections),
        "new_connections": [
            {
                "type": conn.connection_type.value,
                "description": conn.description,
                "similarity": int((conn.similarity_score or 0) * 100),
            }
            for conn in data.new_connections[:3]
        ],
        "fading_items": [
            {
                "title": item.title or "Untitled",
                "decay_score": int(item.decay_score * 100),
            }
            for item in data.fading_items[:3]
        ],
        "most_accessed": {
            "title": data.most_accessed_item.title if data.most_accessed_item else None,
            "access_count": data.most_accessed_item.access_count if data.most_accessed_item else 0,
        },
        "formatted_message": format_digest_for_discord(data),
    }
