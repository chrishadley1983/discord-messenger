"""One-off backfill: generate monthly financial summaries and save to Second Brain.

Generates summaries from Jan 2019 to Feb 2026 (current month excluded).
Skips months that already exist in Second Brain (dedup by source_url).

Usage:
    python scripts/backfill_finance_summaries.py [--dry-run] [--start 2024-01] [--end 2026-02]
"""

import argparse
import asyncio
import os
import sys
from datetime import date, datetime

# Setup paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "mcp_servers"))

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from domains.second_brain.seed.adapters.finance_summary import FinanceSummaryAdapter
from domains.second_brain.seed.runner import run_seed_import


async def backfill(start_month: str, end_month: str, dry_run: bool = False):
    """Generate and save financial summaries for a range of months."""
    # Parse range
    s_year, s_month = map(int, start_month.split("-"))
    e_year, e_month = map(int, end_month.split("-"))

    months = []
    y, m = s_year, s_month
    while (y, m) <= (e_year, e_month):
        months.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1

    print(f"Backfilling {len(months)} months: {start_month} to {end_month}")
    if dry_run:
        print("DRY RUN — no data will be saved\n")

    total_imported = 0
    total_skipped = 0
    total_failed = 0

    for year, month in months:
        label = f"{year}-{month:02d}"
        print(f"  {label}...", end=" ", flush=True)

        try:
            adapter = FinanceSummaryAdapter({"year": year, "month": month})

            if dry_run:
                items = await adapter.fetch(limit=1)
                if items:
                    # Show first 100 chars of content
                    preview = items[0].content[:100].replace("\n", " ")
                    print(f"OK ({len(items[0].content)} chars) — {preview}...")
                else:
                    print("no data")
                continue

            result = await run_seed_import(adapter, limit=1)
            total_imported += result.items_imported
            total_skipped += result.items_skipped
            total_failed += result.items_failed

            if result.items_imported:
                print(f"IMPORTED")
            elif result.items_skipped:
                print(f"skipped (already exists)")
            else:
                errs = "; ".join(result.errors[:2]) if result.errors else "unknown"
                print(f"FAILED: {errs}")

        except Exception as e:
            total_failed += 1
            print(f"ERROR: {e}")

    print(f"\nDone: {total_imported} imported, {total_skipped} skipped, {total_failed} failed")


def main():
    parser = argparse.ArgumentParser(description="Backfill financial summaries to Second Brain")
    parser.add_argument("--start", default="2019-01", help="Start month (YYYY-MM)")
    parser.add_argument("--end", default=None, help="End month (YYYY-MM), default: last month")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    args = parser.parse_args()

    # Default end: previous month
    if args.end is None:
        today = date.today()
        if today.month == 1:
            args.end = f"{today.year - 1}-12"
        else:
            args.end = f"{today.year}-{today.month - 1:02d}"

    asyncio.run(backfill(args.start, args.end, args.dry_run))


if __name__ == "__main__":
    main()
