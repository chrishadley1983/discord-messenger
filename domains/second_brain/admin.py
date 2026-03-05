"""Second Brain admin CLI.

Usage:
    python -m domains.second_brain.admin stats
    python -m domains.second_brain.admin search "query"
    python -m domains.second_brain.admin seed --adapter github-stars
    python -m domains.second_brain.admin seed --all
    python -m domains.second_brain.admin connections --refresh
    python -m domains.second_brain.admin health
"""

import argparse
import asyncio
import sys
from uuid import UUID

from logger import logger
from .db import (
    get_recent_items,
    get_knowledge_item,
    get_total_active_count,
    get_total_connection_count,
    get_topics_with_counts,
    semantic_search,
)
from .seed import run_seed_import, run_all_adapters, get_available_adapters


async def cmd_stats() -> None:
    """Show knowledge base statistics."""
    print("\n=== Second Brain Statistics ===\n")

    try:
        total = await get_total_active_count()
        print(f"Total active items: {total}")

        conn_count = await get_total_connection_count()
        print(f"Total connections: {conn_count}")

        # Recent items
        print("\n--- Recent Items (last 10) ---")
        recent = await get_recent_items(limit=10)
        for item in recent:
            title = item.title[:50] if item.title else "No title"
            print(f"  [{item.capture_type.value}] {title}")

        # Top tags
        print("\n--- Top Tags ---")
        topics = await get_topics_with_counts()
        for topic, count in topics[:10]:
            print(f"  {topic}: {count}")

    except Exception as e:
        logger.error(f"Stats error: {e}")
        print(f"Error: {e}")


async def cmd_search(query: str, limit: int = 10) -> None:
    """Search the knowledge base."""
    print(f"\n=== Searching for: '{query}' ===\n")

    try:
        results = await semantic_search(query, limit=limit)

        if not results:
            print("No results found.")
            return

        for i, result in enumerate(results, 1):
            title = result.item.title[:60] if result.item.title else "No title"
            print(f"{i}. [{result.best_similarity:.3f}] {title}")
            print(f"   Topics: {', '.join(result.item.topics or [])}")
            print(f"   ID: {result.item.id}")
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
    from .connections import discover_connections_for_item

    if item_id:
        print(f"\n=== Connections for item {item_id} ===\n")
        item = await get_knowledge_item(UUID(item_id))
        if not item:
            print("Item not found.")
            return

        connections = await discover_connections_for_item(item)
        print(f"Found {len(connections)} connections")
        for conn in connections:
            print(f"  - {conn.connection_type.value}: {conn.item_b_id} (score: {conn.similarity_score:.2f})")

    elif refresh:
        print("\n=== Refreshing all connections ===\n")
        recent = await get_recent_items(limit=50)
        for item in recent:
            title = item.title[:40] if item.title else "Untitled"
            print(f"Processing: {title}...")
            await discover_connections_for_item(item)
        print("Done.")

    else:
        print("Use --refresh to rebuild connections or --item-id to view specific item")


async def cmd_view(item_id: str) -> None:
    """View a knowledge item in detail."""
    print(f"\n=== Knowledge Item {item_id} ===\n")

    item = await get_knowledge_item(UUID(item_id))
    if not item:
        print("Item not found.")
        return

    print(f"Title: {item.title}")
    print(f"Type: {item.content_type.value}")
    print(f"Capture: {item.capture_type.value}")
    print(f"Status: {item.status.value}")
    print(f"Priority: {item.priority}")
    print(f"Decay: {item.decay_score:.3f}")
    print(f"Topics: {', '.join(item.topics or [])}")
    print(f"Created: {item.created_at}")
    print(f"Accessed: {item.access_count} times")
    print()
    print("--- Summary ---")
    print(item.summary or "(no summary)")
    print()
    print("--- Content (first 500 chars) ---")
    content = item.full_text or ""
    print(content[:500])


def _safe_print(text: str) -> None:
    """Print text, replacing unencodable characters for Windows console."""
    import sys
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8", errors="replace"))


async def cmd_health() -> None:
    """Show Second Brain health diagnostics."""
    from .health import get_health_report, _get_warnings

    _safe_print("\n=== Second Brain Health Report ===\n")

    try:
        report = await get_health_report()

        # Totals
        _safe_print(f"Total active items: {report.total_active}")
        _safe_print(f"Total connections:  {report.total_connections}")

        # Pending items
        _safe_print(f"\n--- Pending Items ({report.pending_count}) ---")
        if report.pending_items:
            for item in report.pending_items:
                title = item.title[:50] if item.title else "Untitled"
                _safe_print(f"  - {title} (created {item.created_at})")
        else:
            _safe_print("  None")

        # Orphaned items
        _safe_print(f"\n--- Orphaned Items ({report.orphaned_count}) ---")
        if report.orphaned_items:
            for item in report.orphaned_items:
                title = item.title[:50] if item.title else "Untitled"
                _safe_print(f"  - {title}")
        else:
            _safe_print("  None")

        # Decay distribution
        total = report.decay_below_02 + report.decay_02_to_05 + report.decay_above_05
        _safe_print("\n--- Decay Distribution ---")
        if total > 0:
            pct = lambda n: f"{n / total * 100:.0f}%"
            _safe_print(f"  Healthy (>0.5):          {report.decay_above_05:>4} ({pct(report.decay_above_05)})")
            _safe_print(f"  Fading (0.2-0.5):        {report.decay_02_to_05:>4} ({pct(report.decay_02_to_05)})")
            _safe_print(f"  Below threshold (<0.2):  {report.decay_below_02:>4} ({pct(report.decay_below_02)})")
        else:
            _safe_print("  No active items")

        # Embedding stats
        stats = report.embedding_stats
        _safe_print("\n--- Embedding Pipeline (current session) ---")
        _safe_print(f"  Edge function: {stats.get('edge_ok', 0)} ok / {stats.get('edge_fail', 0)} fail")
        _safe_print(f"  HuggingFace:   {stats.get('hf_single_ok', 0)} ok / {stats.get('hf_single_fail', 0)} fail")
        _safe_print(f"  Retries: {stats.get('retries', 0)} | Cache hits: {stats.get('cache_hits', 0)}")

        # Connection coverage
        connected = report.total_active - report.items_with_zero_connections
        _safe_print("\n--- Connection Coverage ---")
        _safe_print(f"  Connected: {connected}/{report.total_active}")
        if report.connection_type_breakdown:
            for ctype, count in sorted(report.connection_type_breakdown.items()):
                _safe_print(f"    {ctype}: {count}")

        # Recent capture rate
        _safe_print("\n--- Recent Capture (7 days) ---")
        _safe_print(f"  Created: {report.items_created_7d}")
        _safe_print(f"  Still pending: {report.items_pending_7d}")

        # Warnings summary
        warnings = _get_warnings(report)
        if warnings:
            _safe_print("\n--- WARNINGS ---")
            for w in warnings:
                # Strip Discord emoji syntax for CLI
                clean = w.replace(":warning:", "!").replace(":chart_with_downwards_trend:", "!")
                _safe_print(f"  {clean}")
        else:
            _safe_print("\nAll healthy.")

    except Exception as e:
        logger.error(f"Health report error: {e}")
        _safe_print(f"Error: {e}")


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

    # health command
    subparsers.add_parser("health", help="Show health diagnostics")

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
    elif args.command == "health":
        asyncio.run(cmd_health())


if __name__ == "__main__":
    main()
