"""Re-embed all knowledge chunks with the new embedding model.

Run after migration 010_upgrade_to_gte_base.sql to regenerate all
embeddings with gte-base (768-dim).

Usage:
    python scripts/reembed_all.py [--batch-size 50] [--dry-run]

Resumable: skips chunks that already have non-NULL embeddings.
Estimated time: 17,782 chunks / 50 per batch = ~356 calls ≈ 12 minutes.
"""

import argparse
import asyncio
import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

from config import SUPABASE_URL, SUPABASE_KEY
from domains.second_brain.embed import generate_embeddings_batch, EmbeddingError
from domains.second_brain.config import EMBEDDING_DIMENSIONS


def _get_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


async def get_chunks_needing_embedding(
    client: httpx.AsyncClient,
    offset: int = 0,
    limit: int = 100,
) -> list[dict]:
    """Fetch chunks with NULL embeddings."""
    response = await client.get(
        f"{SUPABASE_URL}/rest/v1/knowledge_chunks"
        f"?embedding=is.null"
        f"&select=id,content,parent_id,chunk_index"
        f"&order=parent_id,chunk_index"
        f"&offset={offset}&limit={limit}",
        headers=_get_headers(),
    )
    response.raise_for_status()
    return response.json()


async def update_chunk_embedding(
    client: httpx.AsyncClient,
    chunk_id: str,
    embedding: list[float],
) -> bool:
    """Update a single chunk's embedding."""
    response = await client.patch(
        f"{SUPABASE_URL}/rest/v1/knowledge_chunks?id=eq.{chunk_id}",
        headers=_get_headers(),
        json={"embedding": embedding},
    )
    return response.status_code == 200


async def get_total_null_count(client: httpx.AsyncClient) -> int:
    """Count chunks with NULL embeddings."""
    response = await client.get(
        f"{SUPABASE_URL}/rest/v1/knowledge_chunks"
        f"?embedding=is.null&select=id&limit=1",
        headers={**_get_headers(), "Prefer": "count=exact"},
    )
    response.raise_for_status()
    count_str = response.headers.get("content-range", "0-0/0").split("/")[-1]
    return int(count_str) if count_str != "*" else 0


async def main(batch_size: int = 50, dry_run: bool = False):
    start_time = time.time()

    async with httpx.AsyncClient(timeout=60) as client:
        total = await get_total_null_count(client)
        print(f"Chunks needing embedding: {total}")
        print(f"Expected batches: {(total + batch_size - 1) // batch_size}")
        print(f"Embedding model: gte-base ({EMBEDDING_DIMENSIONS}-dim)")
        print()

        if dry_run:
            print("DRY RUN — no changes will be made")
            return

        processed = 0
        failed = 0
        batch_num = 0

        while True:
            # Always fetch from offset 0 since we're updating as we go
            chunks = await get_chunks_needing_embedding(client, offset=0, limit=batch_size)
            if not chunks:
                break

            batch_num += 1
            texts = [c["content"] for c in chunks]

            try:
                embeddings = await generate_embeddings_batch(texts)

                for chunk, embedding in zip(chunks, embeddings):
                    if len(embedding) != EMBEDDING_DIMENSIONS:
                        print(f"  WARNING: wrong dimensions for {chunk['id']}: {len(embedding)}")
                        failed += 1
                        continue

                    success = await update_chunk_embedding(client, chunk["id"], embedding)
                    if success:
                        processed += 1
                    else:
                        failed += 1

                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                remaining = (total - processed) / rate if rate > 0 else 0
                print(
                    f"  Batch {batch_num}: {processed}/{total} done "
                    f"({rate:.1f}/s, ~{remaining:.0f}s remaining)"
                )

            except EmbeddingError as e:
                print(f"  ERROR in batch {batch_num}: {e}")
                failed += len(chunks)
                # Mark failed chunks with a zero-vector so we skip them next iteration
                # (prevents infinite loop re-fetching the same NULL chunks)
                zero_vec = [0.0] * EMBEDDING_DIMENSIONS
                for chunk in chunks:
                    await update_chunk_embedding(client, chunk["id"], zero_vec)
                print(f"  Marked {len(chunks)} chunks with placeholder to skip")

    elapsed = time.time() - start_time
    print(f"\nDone! {processed} embedded, {failed} failed in {elapsed:.1f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-embed all knowledge chunks")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    asyncio.run(main(batch_size=args.batch_size, dry_run=args.dry_run))
