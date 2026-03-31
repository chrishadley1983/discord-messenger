"""Backfill orphaned knowledge items — generate chunks + embeddings.

Orphaned items are active knowledge_items with no rows in knowledge_chunks,
making them invisible to semantic search.

Usage:
    python scripts/backfill_orphaned_chunks.py [--dry-run] [--batch-size 20] [--limit 100]
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
_root = str(Path(__file__).parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from dotenv import load_dotenv
load_dotenv()

import httpx
from config import SUPABASE_URL, SUPABASE_KEY
from domains.second_brain.chunk import chunk_text, chunk_for_embedding
from domains.second_brain.embed import generate_embeddings_batch
from domains.second_brain.db import create_knowledge_chunks


REST_URL = f"{SUPABASE_URL}/rest/v1"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


async def fetch_orphaned_items(limit: int = 0) -> list[dict]:
    """Fetch active items that have no chunks using server-side RPC."""
    # Step 1: Get orphan IDs via RPC (server-side NOT EXISTS — reliable)
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{REST_URL}/rpc/get_orphaned_item_ids",
            headers=HEADERS,
            json={},
        )
        resp.raise_for_status()
        orphan_ids = [row["id"] for row in resp.json()]

    if limit:
        orphan_ids = orphan_ids[:limit]

    if not orphan_ids:
        return []

    # Step 2: Fetch full item data in batches of 100 (PostgREST URL length limit)
    all_items = []
    for i in range(0, len(orphan_ids), 100):
        batch_ids = orphan_ids[i:i + 100]
        ids_filter = ",".join(f'"{uid}"' for uid in batch_ids)
        url = f"{REST_URL}/knowledge_items?id=in.({ids_filter})&select=id,title,full_text,summary,content_type,word_count&order=created_at.asc"

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=HEADERS)
            resp.raise_for_status()
            all_items.extend(resp.json())

    return all_items


async def process_batch(items: list[dict], dry_run: bool = False) -> tuple[int, int]:
    """Process a batch of orphaned items: chunk, embed, insert.

    Returns (success_count, skip_count).
    """
    # Prepare all chunks
    item_chunks = []  # (item, chunks, embed_texts)
    all_embed_texts = []

    for item in items:
        text = item.get("full_text") or item.get("summary") or ""
        if not text.strip():
            continue

        chunks = chunk_text(text)
        if not chunks:
            continue

        embed_texts = chunk_for_embedding(text, item.get("title"))
        item_chunks.append((item, chunks, len(embed_texts)))
        all_embed_texts.extend(embed_texts)

    if not all_embed_texts:
        return 0, len(items)

    if dry_run:
        print(f"  [DRY RUN] Would embed {len(all_embed_texts)} chunks for {len(item_chunks)} items")
        return len(item_chunks), len(items) - len(item_chunks)

    # Batch embed all chunks at once
    try:
        all_embeddings = await generate_embeddings_batch(all_embed_texts)
    except Exception as e:
        print(f"  Embedding failed: {e}")
        return 0, len(items)

    # Insert chunks per item
    success = 0
    embed_idx = 0

    for item, chunks, n_embeds in item_chunks:
        embeddings = all_embeddings[embed_idx:embed_idx + n_embeds]
        embed_idx += n_embeds

        chunk_data = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_data.append({
                "index": i,
                "text": chunk.text,
                "embedding": embedding,
                "start_word": chunk.start_word,
                "end_word": chunk.end_word,
            })

        ok = await create_knowledge_chunks(item["id"], chunk_data)
        if ok:
            success += 1
        else:
            print(f"  Failed to insert chunks for {item['id']}: {item.get('title', '')[:60]}")

    skipped = len(items) - success
    return success, skipped


async def main():
    parser = argparse.ArgumentParser(description="Backfill orphaned knowledge items with chunks + embeddings")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without doing it")
    parser.add_argument("--batch-size", type=int, default=20, help="Items per embedding batch (default: 20)")
    parser.add_argument("--limit", type=int, default=0, help="Max items to process (0 = all)")
    args = parser.parse_args()

    print("Fetching orphaned items...")
    orphans = await fetch_orphaned_items(limit=args.limit)
    print(f"Found {len(orphans)} orphaned items")

    if not orphans:
        print("Nothing to do!")
        return

    # Show breakdown
    from collections import Counter
    type_counts = Counter(item.get("content_type", "unknown") for item in orphans)
    for ct, count in type_counts.most_common():
        print(f"  {ct}: {count}")

    total_success = 0
    total_skip = 0

    for i in range(0, len(orphans), args.batch_size):
        batch = orphans[i:i + args.batch_size]
        batch_num = i // args.batch_size + 1
        total_batches = (len(orphans) + args.batch_size - 1) // args.batch_size
        print(f"\nBatch {batch_num}/{total_batches} ({len(batch)} items)...")

        success, skipped = await process_batch(batch, dry_run=args.dry_run)
        total_success += success
        total_skip += skipped
        print(f"  Done: {success} embedded, {skipped} skipped")

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Complete: {total_success} items embedded, {total_skip} skipped")


if __name__ == "__main__":
    asyncio.run(main())
