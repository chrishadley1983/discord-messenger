"""Embed Japan guide chunks locally and insert into Second Brain.

Uses sentence-transformers (gte-small, 384-dim) locally — zero API cost.
Follows the Second Brain schema: knowledge_items (parent) + knowledge_chunks (children with embeddings).

Usage: python embed_japan_guides.py
"""

import json
import asyncio
import uuid
from pathlib import Path

import httpx
from sentence_transformers import SentenceTransformer

CHUNKS_FILE = Path("data/japan_guide_chunks.jsonl")
SUPABASE_URL = "https://modjoikyuhqzouxvieua.supabase.co/rest/v1"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1vZGpvaWt5dWhxem91eHZpZXVhIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2NjE0MTcyOSwiZXhwIjoyMDgxNzE3NzI5fQ.5qFwF4eEnJxn_mg-KHe9hBRr6TIrLZyJtSWfXj0PSmk"
CHUNK_BATCH = 50

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


def load_chunks():
    chunks = []
    with open(CHUNKS_FILE, encoding="utf-8") as f:
        for line in f:
            chunks.append(json.loads(line.strip()))
    return chunks


def group_by_guide(chunks):
    """Group chunks by guide name — each guide becomes one knowledge_item parent."""
    guides = {}
    for c in chunks:
        g = c.get("guide", "unknown")
        if g not in guides:
            guides[g] = []
        guides[g].append(c)
    return guides


async def create_parent_item(client, guide_name: str, chunk_count: int) -> str | None:
    """Create a knowledge_items parent row. Returns the UUID."""
    payload = {
        "content_type": "reference",
        "capture_type": "imported",
        "title": guide_name.replace("-", " ").replace("guide", "Guide").strip().title(),
        "source_system": "japan-guide",
        "full_text": f"Japan travel guide: {guide_name}. Contains {chunk_count} sections.",
        "summary": f"Japan guide page: {guide_name}",
        "topics": ["japan", "travel", guide_name.replace("-guide", "")],
        "base_priority": 1.5,
        "decay_score": 1.5,
        "status": "active",
    }
    try:
        resp = await client.post(f"{SUPABASE_URL}/knowledge_items", headers=HEADERS, json=payload)
        if resp.status_code in (200, 201):
            data = resp.json()
            return data[0]["id"] if data else None
        else:
            print(f"  Parent insert failed: {resp.status_code} {resp.text[:80]}")
    except Exception as e:
        print(f"  Parent insert error: {e}")
    return None


async def insert_chunks(client, parent_id: str, chunks_data: list[dict], embeddings: list) -> int:
    """Insert chunks with embeddings as children of the parent item."""
    inserted = 0
    for i in range(0, len(chunks_data), CHUNK_BATCH):
        batch_c = chunks_data[i:i + CHUNK_BATCH]
        batch_e = embeddings[i:i + CHUNK_BATCH]

        payloads = [
            {
                "parent_id": parent_id,
                "chunk_index": i + j,
                "content": c["content"],
                "embedding": e.tolist(),
            }
            for j, (c, e) in enumerate(zip(batch_c, batch_e))
        ]

        try:
            resp = await client.post(
                f"{SUPABASE_URL}/knowledge_chunks",
                headers={**HEADERS, "Prefer": "return=minimal"},
                json=payloads,
            )
            if resp.status_code in (200, 201):
                inserted += len(payloads)
            else:
                print(f"  Chunk batch failed: {resp.status_code} {resp.text[:80]}")
        except Exception as e:
            print(f"  Chunk batch error: {e}")

    return inserted


async def main():
    # Load chunks
    chunks = load_chunks()
    print(f"Loaded {len(chunks)} chunks")

    # Group by guide
    guides = group_by_guide(chunks)
    print(f"Grouped into {len(guides)} guides")

    # Load model
    print("Loading gte-small model...")
    model = SentenceTransformer("thenlper/gte-small")

    # Embed all chunks
    all_texts = [c["content"] for c in chunks]
    print(f"Embedding {len(all_texts)} chunks locally...")
    all_embeddings = model.encode(all_texts, show_progress_bar=True, batch_size=64)
    print(f"Done: {len(all_embeddings)} embeddings (dim={len(all_embeddings[0])})")

    # Build index: chunk → embedding
    embed_idx = 0
    guide_embeddings = {}
    for guide_name, guide_chunks in guides.items():
        guide_embeddings[guide_name] = all_embeddings[embed_idx:embed_idx + len(guide_chunks)]
        embed_idx += len(guide_chunks)

    # Insert to Supabase
    total_parents = 0
    total_chunks = 0

    async with httpx.AsyncClient(timeout=30) as client:
        for guide_name, guide_chunks in guides.items():
            # Create parent
            parent_id = await create_parent_item(client, guide_name, len(guide_chunks))
            if not parent_id:
                continue
            total_parents += 1

            # Insert chunks
            n = await insert_chunks(client, parent_id, guide_chunks, guide_embeddings[guide_name])
            total_chunks += n

            if total_parents % 20 == 0:
                print(f"  Progress: {total_parents}/{len(guides)} guides, {total_chunks} chunks")

    print(f"\n=== DONE ===")
    print(f"Parents: {total_parents}/{len(guides)}")
    print(f"Chunks: {total_chunks}/{len(chunks)}")


if __name__ == "__main__":
    asyncio.run(main())
