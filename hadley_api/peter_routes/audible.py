"""Audible listening-history endpoints (read-only).

Wraps domains/audible/client.py, which reuses the audible-mcp project's
auth.json. Built for the book-recommender skill and Second Brain adapter.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/audible", tags=["Audible"])


@router.get("/finished")
async def finished_books(since: str | None = None, limit: int = 100):
    """Finished books, newest purchases first. `since` = ISO date filter."""
    from domains.audible import client as ac

    try:
        books = await asyncio.to_thread(ac.get_finished_books, since)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Audible API error: {e}")
    return {"count": len(books), "books": books[: max(1, min(limit, 1000))]}


@router.get("/library-context")
async def library_context():
    """Bundle for the book recommender: recent finished, top-rated,
    in-progress, favourite authors, and listening stats."""
    from domains.audible import client as ac

    try:
        library, stats = await asyncio.gather(
            asyncio.to_thread(ac.get_library),
            asyncio.to_thread(ac.get_listening_stats),
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Audible API error: {e}")

    finished = [b for b in library if b["is_finished"]]
    in_progress = [
        b for b in library
        if not b["is_finished"] and 1 < (b.get("percent_complete") or 0) < 100
    ]

    author_counts: dict[str, int] = {}
    for b in finished:
        for a in b.get("authors") or []:
            author_counts[a] = author_counts.get(a, 0) + 1
    favourite_authors = sorted(author_counts.items(), key=lambda x: -x[1])[:15]

    def _slim(b):
        return {k: b[k] for k in (
            "asin", "title", "authors", "series", "my_rating",
            "average_rating", "purchase_date", "runtime_hours",
        )}

    top_rated = sorted(
        (b for b in finished if b.get("my_rating")),
        key=lambda b: (-float(b["my_rating"]), str(b.get("purchase_date") or "")),
    )[:25]

    return {
        "finished_count": len(finished),
        "recent_finished": [_slim(b) for b in finished[:40]],
        "top_rated": [_slim(b) for b in top_rated],
        "in_progress": [_slim(b) for b in in_progress],
        "favourite_authors": [{"author": a, "books": n} for a, n in favourite_authors],
        "listening_stats": stats.get("aggregated_monthly_listening_stats", []),
    }


@router.get("/similar/{asin}")
async def similar(asin: str, limit: int = 10):
    """Catalogue titles similar to a given book."""
    from domains.audible import client as ac

    try:
        sims = await asyncio.to_thread(ac.get_similar, asin, limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Audible API error: {e}")
    return {"asin": asin, "similar": sims}


@router.get("/search")
async def search(q: str, limit: int = 10):
    """Search the Audible catalogue."""
    from domains.audible import client as ac

    try:
        results = await asyncio.to_thread(ac.search_catalogue, q, limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Audible API error: {e}")
    return {"query": q, "results": results}
