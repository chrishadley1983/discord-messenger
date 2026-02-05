#!/usr/bin/env python3
"""Test semantic search for Second Brain.

Usage:
    python scripts/test_semantic_search.py "your search query"
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def search(query: str, limit: int = 5):
    """Run semantic search."""
    from domains.second_brain.db import semantic_search

    print(f"\nSearching for: '{query}'")
    print("=" * 60)

    results = await semantic_search(
        query=query,
        min_similarity=0.5,  # Lower threshold for testing
        limit=limit,
    )

    if not results:
        print("No results found.")
        return

    print(f"Found {len(results)} results:\n")

    for i, result in enumerate(results, 1):
        item = result.item
        print(f"{i}. {item.title}")
        print(f"   Similarity: {result.best_similarity:.3f}")
        print(f"   Type: {item.content_type.value}")
        print(f"   Topics: {', '.join(item.topics[:5])}")
        if item.summary:
            summary = item.summary[:150] + "..." if len(item.summary) > 150 else item.summary
            print(f"   Summary: {summary}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Test semantic search")
    parser.add_argument("query", type=str, help="Search query")
    parser.add_argument("--limit", "-l", type=int, default=5, help="Max results")

    args = parser.parse_args()

    asyncio.run(search(args.query, args.limit))


if __name__ == "__main__":
    main()
