#!/usr/bin/env python3
"""Run Second Brain seed import.

Usage:
    python scripts/run_seed_import.py [--dry-run] [--adapter NAME] [--limit N]

Examples:
    python scripts/run_seed_import.py                     # Run all adapters
    python scripts/run_seed_import.py --dry-run           # Dry run (no saving)
    python scripts/run_seed_import.py --adapter calendar  # Run specific adapter
    python scripts/run_seed_import.py --limit 50          # Limit items per adapter
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from logger import logger


async def run_import(dry_run: bool = False, adapter_name: str = None, limit: int = 100):
    """Run the seed import."""
    from domains.second_brain.seed import (
        run_seed_import,
        run_all_adapters,
        get_available_adapters,
    )
    from domains.second_brain.seed.adapters import (
        GitHubProjectsAdapter,
        BookmarksAdapter,
        GarminActivitiesAdapter,
        CalendarEventsAdapter,
        EmailImportAdapter,
    )

    print("\n" + "=" * 60)
    print("Second Brain Seed Import")
    print("=" * 60)

    if dry_run:
        print("[DRY RUN] No data will be saved\n")
    else:
        print("[LIVE] Data will be saved to Supabase\n")

    adapters = get_available_adapters()
    print(f"Available adapters: {list(adapters.keys())}\n")

    if adapter_name:
        # Run specific adapter
        if adapter_name not in adapters:
            print(f"[ERROR] Unknown adapter: {adapter_name}")
            print(f"   Available: {list(adapters.keys())}")
            return

        adapter_class = adapters[adapter_name]
        adapter = adapter_class()
        print(f"Running adapter: {adapter_name}")
        print("-" * 40)

        result = await run_seed_import(adapter, limit=limit, dry_run=dry_run)

        print(f"\n[RESULTS] {adapter_name}:")
        print(f"   Found:    {result.items_found}")
        print(f"   Imported: {result.items_imported}")
        print(f"   Skipped:  {result.items_skipped}")
        print(f"   Failed:   {result.items_failed}")
        if result.errors:
            print(f"   Errors:")
            for err in result.errors[:5]:
                print(f"     - {err}")
    else:
        # Run all adapters
        print(f"Running all {len(adapters)} adapters...")
        print("-" * 40)

        results = await run_all_adapters(
            limit_per_adapter=limit,
            dry_run=dry_run,
        )

        # Summary
        print("\n" + "=" * 60)
        print("IMPORT SUMMARY")
        print("=" * 60)

        total_found = 0
        total_imported = 0
        total_skipped = 0
        total_failed = 0

        for result in results:
            total_found += result.items_found
            total_imported += result.items_imported
            total_skipped += result.items_skipped
            total_failed += result.items_failed

            status = "[OK]" if result.items_failed == 0 else "[!!]"
            print(f"{status} {result.adapter_name:20} | "
                  f"Found: {result.items_found:4} | "
                  f"Imported: {result.items_imported:4} | "
                  f"Skipped: {result.items_skipped:4} | "
                  f"Failed: {result.items_failed:4}")

            if result.errors:
                for err in result.errors[:2]:
                    print(f"   -> {err[:60]}...")

        print("-" * 60)
        print(f"TOTAL                   | "
              f"Found: {total_found:4} | "
              f"Imported: {total_imported:4} | "
              f"Skipped: {total_skipped:4} | "
              f"Failed: {total_failed:4}")
        print("=" * 60)

    print("\nImport complete!")


def main():
    parser = argparse.ArgumentParser(description="Run Second Brain seed import")
    parser.add_argument("--dry-run", action="store_true", help="Don't save, just test")
    parser.add_argument("--adapter", "-a", type=str, help="Run specific adapter only")
    parser.add_argument("--limit", "-l", type=int, default=100, help="Max items per adapter")

    args = parser.parse_args()

    asyncio.run(run_import(
        dry_run=args.dry_run,
        adapter_name=args.adapter,
        limit=args.limit,
    ))


if __name__ == "__main__":
    main()
