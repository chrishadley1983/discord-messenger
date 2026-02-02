"""Second Brain admin CLI.

Usage:
    python -m domains.second_brain.admin stats
    python -m domains.second_brain.admin search "query"
    python -m domains.second_brain.admin seed --adapter github-stars
    python -m domains.second_brain.admin seed --all
    python -m domains.second_brain.admin connections --refresh
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta

from logger import logger
from .db import get_recent_items, search_knowledge, get_item_by_id
from .seed import run_seed_import, run_all_adapters, get_available_adapters


async def cmd_stats() -> None:
    """Show knowledge base statistics."""
    from .db import supabase

    print("\n=== Second Brain Statistics ===\n")

    # Get counts by status
    try:
        result = supabase.table("knowledge_items").select("status", count="exact").execute()
        total = len(result.data) if result.data else 0
        print(f"Total items: {total}")

        # Count by capture type
        for capture_type in ["explicit", "passive", "seed"]:
            result = supabase.table("knowledge_items").select(
                "*", count="exact"
            ).eq("capture_type", capture_type).execute()
            count = len(result.data) if result.data else 0
            print(f"  - {capture_type}: {count}")

        # Recent items
        print("\n--- Recent Items (last 7 days) ---")
        recent = await get_recent_items(limit=10)
        for item in recent:
            title = item.title[:50] if item.title else "No title"
            print(f"  [{item.capture_type}] {title}")

        # Top tags
        print("\n--- Top Tags ---")
        result = supabase.table("knowledge_items").select("tags").execute()
        tag_counts: dict[str, int] = {}
        for row in result.data or []:
            for tag in row.get("tags") or []:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"  {tag}: {count}")

    except Exception as e:
        logger.error(f"Stats error: {e}")
        print(f"Error: {e}")


async def cmd_search(query: str, limit: int = 10) -> None:
    """Search the knowledge base."""
    print(f"\n=== Searching for: '{query}' ===\n")

    try:
        results = await search_knowledge(query, limit=limit)

        if not results:
            print("No results found.")
            return

        for i, item in enumerate(results, 1):
            title = item.title[:60] if item.title else "No title"
            score = getattr(item, "similarity_score", 0)
            print(f"{i}. [{score:.3f}] {title}")
            print(f"   Tags: {', '.join(item.tags or [])}")
            print(f"   ID: {item.id}")
            print()

    except Exception as e:
        logger.error(f"Search error: {e}")
        print(f"Error: {e}")


async def cmd_seed(adapter_name: str | None = None, dry_run: bool = False) -> None:
    """Run seed imports."""
    adapters = get_available_adapters()

    if adapter_name:
        if adapter_name not in adapters:
            print(f"Unknown adapter: {adapter_name}")
            print(f"Available: {', '.join(adapters.keys())}")
            return

        print(f"\n=== Running {adapter_name} adapter ===\n")
        adapter_class = adapters[adapter_name]
        adapter = adapter_class()
        result = await run_seed_import(adapter, dry_run=dry_run)
        _print_seed_result(result)

    else:
        # Run all adapters
        print("\n=== Running all seed adapters ===\n")
        results = await run_all_adapters(dry_run=dry_run)
        for result in results:
            _print_seed_result(result)
            print()


def _print_seed_result(result) -> None:
    """Print seed import result."""
    print(f"Adapter: {result.adapter_name}")
    print(f"  Found: {result.items_found}")
    print(f"  Imported: {result.items_imported}")
    print(f"  Skipped: {result.items_skipped}")
    print(f"  Failed: {result.items_failed}")
    if result.errors:
        print(f"  Errors:")
        for err in result.errors[:5]:
            print(f"    - {err}")


async def cmd_connections(refresh: bool = False, item_id: str | None = None) -> None:
    """Manage knowledge connections."""
    from .connections import discover_connections

    if item_id:
        print(f"\n=== Connections for item {item_id} ===\n")
        item = await get_item_by_id(item_id)
        if not item:
            print("Item not found.")
            return

        connections = await discover_connections(item_id)
        print(f"Found {len(connections)} connections")
        for conn in connections:
            print(f"  - {conn.connection_type}: {conn.target_id} (strength: {conn.strength:.2f})")

    elif refresh:
        print("\n=== Refreshing all connections ===\n")
        # Get recent items without connections
        recent = await get_recent_items(limit=50)
        for item in recent:
            print(f"Processing: {item.title[:40]}...")
            await discover_connections(item.id)
        print("Done.")

    else:
        print("Use --refresh to rebuild connections or --item-id to view specific item")


async def cmd_view(item_id: str) -> None:
    """View a knowledge item in detail."""
    print(f"\n=== Knowledge Item {item_id} ===\n")

    item = await get_item_by_id(item_id)
    if not item:
        print("Item not found.")
        return

    print(f"Title: {item.title}")
    print(f"Type: {item.content_type}")
    print(f"Capture: {item.capture_type}")
    print(f"Status: {item.status}")
    print(f"Priority: {item.priority_multiplier}")
    print(f"Tags: {', '.join(item.tags or [])}")
    print(f"Created: {item.created_at}")
    print(f"Accessed: {item.access_count} times")
    print()
    print("--- Summary ---")
    print(item.summary or "(no summary)")
    print()
    print("--- Content (first 500 chars) ---")
    content = item.content or ""
    print(content[:500])


def main():
    parser = argparse.ArgumentParser(
        description="Second Brain admin CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # stats command
    subparsers.add_parser("stats", help="Show knowledge base statistics")

    # search command
    search_parser = subparsers.add_parser("search", help="Search knowledge base")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--limit", type=int, default=10)

    # seed command
    seed_parser = subparsers.add_parser("seed", help="Run seed imports")
    seed_parser.add_argument("--adapter", help="Specific adapter to run")
    seed_parser.add_argument("--all", action="store_true", help="Run all adapters")
    seed_parser.add_argument("--dry-run", action="store_true", help="Don't save, just preview")

    # connections command
    conn_parser = subparsers.add_parser("connections", help="Manage connections")
    conn_parser.add_argument("--refresh", action="store_true", help="Refresh all connections")
    conn_parser.add_argument("--item-id", help="View connections for specific item")

    # view command
    view_parser = subparsers.add_parser("view", help="View a knowledge item")
    view_parser.add_argument("item_id", help="Item ID to view")

    args = parser.parse_args()

    # Run async command
    if args.command == "stats":
        asyncio.run(cmd_stats())
    elif args.command == "search":
        asyncio.run(cmd_search(args.query, args.limit))
    elif args.command == "seed":
        adapter = args.adapter if hasattr(args, "adapter") else None
        asyncio.run(cmd_seed(adapter, args.dry_run))
    elif args.command == "connections":
        asyncio.run(cmd_connections(args.refresh, getattr(args, "item_id", None)))
    elif args.command == "view":
        asyncio.run(cmd_view(args.item_id))


if __name__ == "__main__":
    main()
