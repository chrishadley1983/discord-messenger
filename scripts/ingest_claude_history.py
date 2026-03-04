"""Ingest Claude chat history into peterbot-mem and Second Brain.

Usage:
    python scripts/ingest_claude_history.py <export.json> [--dry-run] [--verbose]

Processes Anthropic JSON exports:
1. Parse conversations
2. Chunk by topic
3. Classify (skip / peterbot-mem / second-brain)
4. Deduplicate via SHA-256
5. Route to appropriate system
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Project root setup
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from scripts.chat_history.parser import parse_export_file
from scripts.chat_history.chunker import chunk_conversation
from scripts.chat_history.classifier import classify_chunk, Route
from scripts.chat_history.dedup import DedupTracker

import httpx


async def send_to_peterbot_mem(chunk_text: str, conversation_name: str) -> bool:
    """Send a preference/decision chunk to peterbot-mem."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "http://localhost:37777/api/sessions/messages",
                json={
                    "role": "user",
                    "content": chunk_text,
                    "metadata": {
                        "source": "claude-history",
                        "conversation": conversation_name,
                    },
                },
                timeout=30,
            )
            return resp.status_code in (200, 201)
    except Exception as e:
        print(f"  [ERROR] peterbot-mem: {e}")
        return False


async def send_to_second_brain(chunk_text: str, conversation_name: str, topics: list[str]) -> bool:
    """Send a knowledge chunk to Second Brain via pipeline."""
    try:
        from domains.second_brain.pipeline import process_capture
        from domains.second_brain.types import CaptureType

        item = await process_capture(
            source=chunk_text,
            capture_type=CaptureType.SEED,
            user_note=f"From Claude chat: {conversation_name}",
            user_tags=topics + ["claude-history"],
        )
        return item is not None
    except Exception as e:
        print(f"  [ERROR] second-brain: {e}")
        return False


async def main():
    parser = argparse.ArgumentParser(description="Ingest Claude chat history")
    parser.add_argument("export_file", type=Path, help="Path to Anthropic JSON export")
    parser.add_argument("--dry-run", action="store_true", help="Parse and classify but don't import")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show each chunk's classification")
    parser.add_argument("--min-confidence", type=float, default=0.5, help="Minimum classification confidence")
    args = parser.parse_args()

    if not args.export_file.exists():
        print(f"File not found: {args.export_file}")
        sys.exit(1)

    # Parse
    print(f"Parsing {args.export_file}...")
    conversations = parse_export_file(args.export_file)
    print(f"Found {len(conversations)} conversations")

    # Chunk
    all_chunks = []
    for conv in conversations:
        chunks = chunk_conversation(conv)
        all_chunks.extend(chunks)
    print(f"Created {len(all_chunks)} chunks")

    # Classify
    classifications = [classify_chunk(c) for c in all_chunks]

    # Stats
    route_counts = {r: 0 for r in Route}
    for c in classifications:
        route_counts[c.route] += 1

    print(f"\nClassification summary:")
    print(f"  Skip: {route_counts[Route.SKIP]}")
    print(f"  Peterbot-mem: {route_counts[Route.PETERBOT_MEM]}")
    print(f"  Second Brain: {route_counts[Route.SECOND_BRAIN]}")

    if args.dry_run:
        if args.verbose:
            for cl in classifications:
                if cl.route != Route.SKIP:
                    print(f"\n  [{cl.route.value}] (conf: {cl.confidence:.2f}) {cl.reason}")
                    print(f"    Conv: {cl.chunk.conversation_name}")
                    preview = cl.chunk.human_text[:100].replace("\n", " ")
                    print(f"    Preview: {preview}...")
        print("\nDry run complete — no data imported.")
        return

    # Dedup and import
    tracker = DedupTracker()
    run_id = tracker.start_run(str(args.export_file))

    imported = 0
    skipped = 0
    deduped = 0
    failed = 0

    for cl in classifications:
        if cl.route == Route.SKIP:
            skipped += 1
            continue

        if cl.confidence < args.min_confidence:
            skipped += 1
            continue

        # Dedup check
        content_hash = tracker.hash_content(cl.chunk.text)
        if tracker.is_imported(content_hash):
            deduped += 1
            continue

        success = False
        if cl.route == Route.PETERBOT_MEM:
            success = await send_to_peterbot_mem(cl.chunk.text, cl.chunk.conversation_name)
        elif cl.route == Route.SECOND_BRAIN:
            success = await send_to_second_brain(
                cl.chunk.text, cl.chunk.conversation_name, []
            )

        if success:
            tracker.mark_imported(content_hash, cl.chunk.conversation_id,
                                  cl.chunk.chunk_index, cl.route.value)
            imported += 1
            if args.verbose:
                print(f"  [OK] {cl.route.value}: {cl.chunk.conversation_name} chunk {cl.chunk.chunk_index}")
        else:
            failed += 1

    tracker.finish_run(run_id, len(all_chunks), imported, skipped, deduped)

    print(f"\nImport complete:")
    print(f"  Imported: {imported}")
    print(f"  Skipped: {skipped}")
    print(f"  Deduped: {deduped}")
    print(f"  Failed: {failed}")

    tracker.close()


if __name__ == "__main__":
    asyncio.run(main())
