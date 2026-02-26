"""Brain Graph API Routes.

Provides mind map visualization data from the Second Brain:
- Graph data (topics, edges, stats)
- Topic drill-down
- Semantic search with topic highlighting
- Activity patterns
"""

import os
import time
import httpx
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from zoneinfo import ZoneInfo

UK_TZ = ZoneInfo("Europe/London")

router = APIRouter(prefix="/brain/graph", tags=["Brain Graph"])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_FUNC_URL = None  # Lazy init from SUPABASE_URL

CACHE_TTL = 600  # 10 minutes
_cache: dict[str, tuple[float, dict]] = {}


def _get_func_url() -> str:
    global SUPABASE_FUNC_URL
    if SUPABASE_FUNC_URL is None:
        # https://xxx.supabase.co -> https://xxx.supabase.co/functions/v1
        SUPABASE_FUNC_URL = f"{SUPABASE_URL}/functions/v1"
    return SUPABASE_FUNC_URL


def _supabase_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def _get_cached(key: str) -> Optional[dict]:
    if key in _cache:
        ts, data = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return data
        del _cache[key]
    return None


def _set_cached(key: str, data: dict):
    _cache[key] = (time.time(), data)


# ============================================================
# GET /brain/graph — Main graph data
# ============================================================

@router.get("")
async def get_graph_data():
    """Get full mind map graph data (topics, edges, stats). Cached 10 min."""
    cached = _get_cached("graph")
    if cached:
        return cached

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/rpc/get_mind_map_data",
            headers=_supabase_headers(),
            json={},
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)

        data = resp.json()
        _set_cached("graph", data)
        return data


# ============================================================
# GET /brain/graph/topic/{topic} — Drill-down
# ============================================================

@router.get("/topic/{topic}")
async def get_topic_items(topic: str, limit: int = Query(default=50, le=100)):
    """Get knowledge items for a specific topic."""
    # Use PostgREST contains operator for array field
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/knowledge_items",
            headers={**_supabase_headers(), "Prefer": "count=exact"},
            params={
                "topics": f"cs.{{{topic}}}",
                "status": "eq.active",
                "select": "id,title,content_type,topics,decay_score,access_count,last_accessed_at,created_at,summary",
                "order": "last_accessed_at.desc.nullslast",
                "limit": limit,
            },
        )
        if resp.status_code not in (200, 206):
            raise HTTPException(status_code=resp.status_code, detail=resp.text)

        total = resp.headers.get("content-range", "")
        total_count = int(total.split("/")[1]) if "/" in total else None

        return {
            "topic": topic,
            "total_count": total_count,
            "items": resp.json(),
        }


# ============================================================
# GET /brain/graph/search — Semantic search + topic highlight
# ============================================================

@router.get("/search")
async def search_graph(query: str = Query(..., min_length=2)):
    """Semantic search returning items + which topics to highlight."""
    # Generate embedding via Edge Function
    async with httpx.AsyncClient(timeout=15) as client:
        embed_resp = await client.post(
            f"{_get_func_url()}/embed",
            headers=_supabase_headers(),
            json={"input": query},
        )
        if embed_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Embedding generation failed")

        embedding = embed_resp.json().get("embedding")
        if not embedding:
            raise HTTPException(status_code=502, detail="No embedding returned")

        # Search via existing RPC
        search_resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/rpc/search_knowledge",
            headers=_supabase_headers(),
            json={
                "query_embedding": embedding,
                "match_count": 20,
                "match_threshold": 0.3,
            },
        )
        if search_resp.status_code != 200:
            raise HTTPException(status_code=search_resp.status_code, detail=search_resp.text)

        items = search_resp.json()

        # Extract unique topics from results for highlighting
        highlighted_topics = set()
        for item in items:
            if item.get("topics"):
                for t in item["topics"]:
                    highlighted_topics.add(t)

        return {
            "query": query,
            "items": items,
            "highlighted_topics": sorted(highlighted_topics),
        }


# ============================================================
# GET /brain/graph/activity — Activity patterns
# ============================================================

@router.get("/activity")
async def get_activity():
    """Get activity patterns from CLI cost logs and knowledge access."""
    result = {"cli_activity": [], "knowledge_activity": []}

    # CLI cost logs
    log_path = Path(__file__).parent.parent / "data" / "cli_costs.jsonl"
    if log_path.exists():
        import json
        entries = []
        try:
            lines = log_path.read_text(encoding="utf-8").strip().split("\n")
            for line in lines[-500:]:  # Last 500 entries
                if line.strip():
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass

        # Aggregate by date
        daily: dict[str, dict] = {}
        for entry in entries:
            ts = entry.get("timestamp", "")
            day = ts[:10] if len(ts) >= 10 else None
            if not day:
                continue
            if day not in daily:
                daily[day] = {"date": day, "calls": 0, "total_cost_usd": 0.0}
            daily[day]["calls"] += 1
            daily[day]["total_cost_usd"] += entry.get("cost_usd", 0) or 0

        result["cli_activity"] = sorted(daily.values(), key=lambda x: x["date"])

    # Knowledge access patterns (last 90 days, by day)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/rpc/get_mind_map_data",
            headers=_supabase_headers(),
            json={},
        )
        if resp.status_code == 200:
            data = resp.json()
            result["overall"] = data.get("overall", {})

    # Knowledge items accessed recently — aggregate by date
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/knowledge_items",
            headers=_supabase_headers(),
            params={
                "status": "eq.active",
                "last_accessed_at": f"gte.{(datetime.now(UK_TZ) - timedelta(days=90)).isoformat()}",
                "select": "last_accessed_at,topics",
                "order": "last_accessed_at.desc",
                "limit": 1000,
            },
        )
        if resp.status_code == 200:
            items = resp.json()
            daily_access: dict[str, dict] = {}
            for item in items:
                la = item.get("last_accessed_at", "")
                day = la[:10] if la and len(la) >= 10 else None
                if not day:
                    continue
                if day not in daily_access:
                    daily_access[day] = {"date": day, "accesses": 0, "topics": set()}
                daily_access[day]["accesses"] += 1
                for t in (item.get("topics") or []):
                    daily_access[day]["topics"].add(t)

            # Convert sets to lists for JSON
            result["knowledge_activity"] = sorted(
                [{"date": v["date"], "accesses": v["accesses"], "topic_count": len(v["topics"])}
                 for v in daily_access.values()],
                key=lambda x: x["date"]
            )

    return result


# ============================================================
# POST /brain/graph/refresh — Clear cache
# ============================================================

@router.post("/refresh")
async def refresh_cache():
    """Clear the graph data cache."""
    _cache.clear()
    return {"status": "ok", "message": "Cache cleared"}
