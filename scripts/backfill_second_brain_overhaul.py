"""Second Brain overhaul backfill script.

Runs after the pipeline overhaul to fix existing data:
1. SQL backfill: reclassify content_type by source_system
2. SQL cleanup: remove noise tags (email, general)
3. Re-tag items with improved topic extraction
4. Run structured extraction on items missing facts/concepts

Usage:
    python scripts/backfill_second_brain_overhaul.py [--phase 1|2|3|all] [--batch-size 50] [--dry-run]

Phase 1: SQL fixes (instant, no API calls)
Phase 2: Re-tag items (Claude API via Hadley API)
Phase 3: Structured extraction backfill (Claude API via Hadley API)

Run phase 1 first, then 2 and 3 can run in parallel.
"""

import argparse
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

from config import SUPABASE_URL, SUPABASE_KEY
from logger import logger


def _get_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


# =============================================================================
# PHASE 1: SQL backfill (content_type reclassification + noise tag cleanup)
# =============================================================================

CONTENT_TYPE_MAPPINGS = [
    ("seed:email", "email"),
    ("seed:gcal", "calendar_event"),
    ("seed:garmin", "health_activity"),
    ("seed:garmin-health", "health_activity"),
    ("seed:finance", "financial_report"),
    ("seed:spotify", "listening_history"),
    ("seed:netflix", "viewing_history"),
    ("seed:github", "commit"),
    ("seed:bookmarks", "bookmark"),
    ("seed:familyfuel", "recipe"),
    ("seed:travel", "travel_booking"),
    ("seed:claude", "conversation_extract"),
    ("seed:claude-code", "conversation_extract"),
    ("seed:withings", "health_activity"),
    ("seed:peter", "conversation_extract"),
    ("seed:school", "calendar_event"),
    ("seed:reddit", "social_save"),
]


async def phase1_sql_backfill(client: httpx.AsyncClient, dry_run: bool = False):
    """Reclassify content_type and clean up noise tags."""
    print("=== Phase 1: SQL Backfill ===\n")

    # 1a: Reclassify content_type by source_system
    print("1a. Reclassifying content_type by source_system...")
    for source_system, content_type in CONTENT_TYPE_MAPPINGS:
        if dry_run:
            print(f"  [DRY RUN] {source_system} → {content_type}")
            continue

        response = await client.patch(
            f"{SUPABASE_URL}/rest/v1/knowledge_items"
            f"?source_system=eq.{source_system}&content_type=eq.note",
            headers={**_get_headers(), "Prefer": "count=exact, return=representation"},
            json={"content_type": content_type},
        )
        count_range = response.headers.get("content-range", "*/0")
        print(f"  {source_system} → {content_type}: {count_range}")

    # 1b: Clean up noise tags from multi-tag items
    print("\n1b. Cleaning up noise tags...")
    noise_tags = ["email", "general"]
    for tag in noise_tags:
        if dry_run:
            print(f"  [DRY RUN] Would remove '{tag}' from multi-tag items")
            continue

        updated = 0
        offset = 0
        while True:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/knowledge_items"
                f"?topics=cs.{{{tag}}}"
                f"&select=id,topics"
                f"&limit=100&offset={offset}",
                headers=_get_headers(),
            )
            response.raise_for_status()
            items = response.json()
            if not items:
                break

            for item in items:
                topics = item.get("topics", [])
                if len(topics) > 1 and tag in topics:
                    new_topics = [t for t in topics if t != tag]
                    await client.patch(
                        f"{SUPABASE_URL}/rest/v1/knowledge_items?id=eq.{item['id']}",
                        headers=_get_headers(),
                        json={"topics": new_topics},
                    )
                    updated += 1

            offset += 100
            if len(items) < 100:
                break

        print(f"  Removed '{tag}' from {updated} multi-tag items")

    # 1c: Replace solo noise tags with "unclassified"
    if not dry_run:
        for tag in noise_tags:
            updated = 0
            offset = 0
            while True:
                response = await client.get(
                    f"{SUPABASE_URL}/rest/v1/knowledge_items"
                    f"?topics=eq.{{{tag}}}"
                    f"&select=id"
                    f"&limit=100&offset={offset}",
                    headers=_get_headers(),
                )
                response.raise_for_status()
                items = response.json()
                if not items:
                    break

                for item in items:
                    await client.patch(
                        f"{SUPABASE_URL}/rest/v1/knowledge_items?id=eq.{item['id']}",
                        headers=_get_headers(),
                        json={"topics": ["unclassified"]},
                    )
                    updated += 1

                offset += 100
                if len(items) < 100:
                    break

            print(f"  Replaced solo '{tag}' → 'unclassified' on {updated} items")

    print("\nPhase 1 complete.\n")


# =============================================================================
# PHASE 2: Re-tag items needing better topics
# =============================================================================

async def phase2_retag(
    client: httpx.AsyncClient,
    batch_size: int = 50,
    dry_run: bool = False,
):
    """Re-tag items with poor topics using the improved prompt."""
    from domains.second_brain.tag import extract_topics

    print("=== Phase 2: Re-tag Items ===\n")

    offset = 0
    retagged = 0
    failed = 0

    while True:
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/knowledge_items"
            f"?status=eq.active"
            f"&select=id,title,full_text,topics,content_type"
            f"&or=(topics.cs.{{unclassified}},topics.cs.{{untagged}},topics.cs.{{claude-history}})"
            f"&limit={batch_size}&offset={offset}",
            headers=_get_headers(),
        )
        response.raise_for_status()
        items = response.json()
        if not items:
            break

        print(f"  Processing batch at offset {offset} ({len(items)} items)...")

        for item in items:
            text = item.get("full_text") or ""
            title = item.get("title")
            content_type = item.get("content_type")

            if len(text) < 20:
                continue

            if dry_run:
                retagged += 1
                continue

            try:
                new_topics = await extract_topics(text, title, content_type=content_type)
                if new_topics and new_topics != item.get("topics"):
                    await client.patch(
                        f"{SUPABASE_URL}/rest/v1/knowledge_items?id=eq.{item['id']}",
                        headers=_get_headers(),
                        json={"topics": new_topics},
                    )
                    retagged += 1
            except Exception as e:
                failed += 1
                if failed <= 5:
                    print(f"    Failed to re-tag {item['id']}: {e}")

        offset += batch_size
        if len(items) < batch_size:
            break

    print(f"\nPhase 2 complete: {retagged} re-tagged, {failed} failed.\n")


# =============================================================================
# PHASE 3: Structured extraction backfill
# =============================================================================

async def phase3_extract(
    client: httpx.AsyncClient,
    batch_size: int = 50,
    dry_run: bool = False,
):
    """Run structured extraction on items missing facts/concepts."""
    from domains.second_brain.extract_structured import extract_structured

    print("=== Phase 3: Structured Extraction Backfill ===\n")

    skip_types = ["listening_history", "viewing_history"]
    skip_filter = "&".join(f"content_type=neq.{t}" for t in skip_types)

    offset = 0
    extracted = 0
    failed = 0

    while True:
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/knowledge_items"
            f"?status=eq.active"
            f"&facts=eq.[]"
            f"&concepts=eq.[]"
            f"&{skip_filter}"
            f"&select=id,title,full_text,content_type"
            f"&limit={batch_size}&offset={offset}",
            headers=_get_headers(),
        )
        response.raise_for_status()
        items = response.json()
        if not items:
            break

        print(f"  Processing batch at offset {offset} ({len(items)} items)...")

        for item in items:
            text = item.get("full_text") or ""
            title = item.get("title")
            content_type = item.get("content_type")

            if len(text) < 50:
                continue

            if dry_run:
                extracted += 1
                continue

            try:
                result = await extract_structured(text, title, content_type=content_type)
                facts = result.get("facts", [])
                concepts = result.get("concepts", [])

                if facts or concepts:
                    await client.patch(
                        f"{SUPABASE_URL}/rest/v1/knowledge_items?id=eq.{item['id']}",
                        headers=_get_headers(),
                        json={"facts": facts, "concepts": concepts},
                    )
                    extracted += 1
            except Exception as e:
                failed += 1
                if failed <= 5:
                    print(f"    Failed to extract {item['id']}: {e}")

        offset += batch_size
        if len(items) < batch_size:
            break

    print(f"\nPhase 3 complete: {extracted} extracted, {failed} failed.\n")


# =============================================================================
# MAIN
# =============================================================================

async def main(phase: str = "all", batch_size: int = 50, dry_run: bool = False):
    async with httpx.AsyncClient(timeout=60) as client:
        if phase in ("1", "all"):
            await phase1_sql_backfill(client, dry_run=dry_run)

        if phase in ("2", "all"):
            await phase2_retag(client, batch_size=batch_size, dry_run=dry_run)

        if phase in ("3", "all"):
            await phase3_extract(client, batch_size=batch_size, dry_run=dry_run)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Second Brain overhaul backfill")
    parser.add_argument("--phase", default="all", choices=["1", "2", "3", "all"])
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    asyncio.run(main(phase=args.phase, batch_size=args.batch_size, dry_run=args.dry_run))
