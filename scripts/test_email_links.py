#!/usr/bin/env python3
"""Test the email link scraper adapter.

Usage:
    python scripts/test_email_links.py --dry-run     # Find emails + extract links only
    python scripts/test_email_links.py               # Full scrape + save to DB
    python scripts/test_email_links.py --limit 2     # Limit items
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from logger import logger


async def test_email_links(dry_run: bool = False, limit: int = 20):
    """Test the email link scraper."""
    from domains.second_brain.seed.runner import run_seed_import, get_available_adapters
    from domains.second_brain.seed.adapters import email_links

    adapters = get_available_adapters()
    print(f"Available adapters: {list(adapters.keys())}")

    if "email-link-scraper" not in adapters:
        print("[ERROR] email-link-scraper not registered!")
        return

    adapter_class = adapters["email-link-scraper"]

    # Use 1 year back to find the latest Gousto + all Japan Airbnb bookings
    config = {
        "years_back": 1,
        "per_scraper_limit": limit,
    }
    adapter = adapter_class(config)

    # Validate
    is_valid, err = await adapter.validate()
    print(f"Validation: {'PASS' if is_valid else 'FAIL'} {err}")
    if not is_valid:
        return

    print(f"\n{'='*60}")
    print(f"Running email-link-scraper (dry_run={dry_run}, limit={limit})")
    print(f"{'='*60}\n")

    result = await run_seed_import(adapter, limit=limit, dry_run=dry_run)

    print(f"\n{'='*60}")
    print(f"RESULTS:")
    print(f"  Found:    {result.items_found}")
    print(f"  Imported: {result.items_imported}")
    print(f"  Skipped:  {result.items_skipped}")
    print(f"  Failed:   {result.items_failed}")
    if result.errors:
        print(f"  Errors:")
        for err in result.errors[:10]:
            print(f"    - {err}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Test email link scraper")
    parser.add_argument("--dry-run", action="store_true", help="Don't save, just test")
    parser.add_argument("--limit", "-l", type=int, default=20, help="Max items total")
    args = parser.parse_args()

    asyncio.run(test_email_links(dry_run=args.dry_run, limit=args.limit))


if __name__ == "__main__":
    main()
