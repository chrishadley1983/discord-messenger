"""Diagnose memory system health.

Checks:
- Peterbot-mem worker (port 37777)
- Second Brain item counts by capture_type
- Items created in last 7 days
- Decay score distribution
- Pending items count
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta

# Project root setup
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

import httpx


async def check_peterbot_mem():
    """Check if peterbot-mem worker is running on port 37777."""
    print("\n=== Peterbot-Mem Worker ===")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:37777/api/health", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                print(f"  Status: HEALTHY")
                print(f"  Response: {data}")
            else:
                print(f"  Status: UNHEALTHY (HTTP {resp.status_code})")
    except httpx.ConnectError:
        print("  Status: NOT RUNNING (connection refused)")
    except Exception as e:
        print(f"  Status: ERROR ({e})")


async def check_second_brain():
    """Check Second Brain health via Supabase."""
    from domains.second_brain import db
    from domains.second_brain.types import ItemStatus

    print("\n=== Second Brain ===")

    # Total active items
    total = await db.get_total_active_count()
    print(f"  Total active items: {total}")

    # Total connections
    connections = await db.get_total_connection_count()
    print(f"  Total connections: {connections}")

    # Items by capture_type
    print("\n  Items by capture type:")
    from config import SUPABASE_URL, SUPABASE_KEY
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient() as client:
        for ct in ["explicit", "passive", "seed"]:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/knowledge_items?capture_type=eq.{ct}&status=eq.active&select=id",
                headers={**headers, "Prefer": "count=exact"},
                timeout=30,
            )
            count = resp.headers.get("content-range", "0-0/0").split("/")[-1]
            print(f"    {ct}: {count}")

    # Recent items (last 7 days)
    since = datetime.utcnow() - timedelta(days=7)
    recent = await db.get_items_since(since)
    print(f"\n  Items created in last 7 days: {len(recent)}")
    for item in recent[:5]:
        print(f"    - {item.title or 'Untitled'} ({item.content_type.value if hasattr(item.content_type, 'value') else item.content_type})")
    if len(recent) > 5:
        print(f"    ... and {len(recent) - 5} more")

    # Pending items
    pending = await db.get_pending_items(limit=100)
    print(f"\n  Pending items (need reprocessing): {len(pending)}")

    # Decay score distribution
    print("\n  Decay score distribution:")
    async with httpx.AsyncClient() as client:
        for low, high, label in [
            (0.8, 1.0, "Fresh (0.8-1.0)"),
            (0.5, 0.8, "Active (0.5-0.8)"),
            (0.2, 0.5, "Fading (0.2-0.5)"),
            (0.0, 0.2, "Nearly forgotten (0-0.2)"),
        ]:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/knowledge_items"
                f"?status=eq.active&decay_score=gte.{low}&decay_score=lt.{high}&select=id",
                headers={**headers, "Prefer": "count=exact"},
                timeout=30,
            )
            count = resp.headers.get("content-range", "0-0/0").split("/")[-1]
            print(f"    {label}: {count}")

    # Topics
    topics = await db.get_topics_with_counts()
    print(f"\n  Total topics: {len(topics)}")
    if topics:
        topics.sort(key=lambda x: x[1], reverse=True)
        print("  Top 10:")
        for topic, count in topics[:10]:
            print(f"    - {topic}: {count}")


async def main():
    print("Memory Systems Health Check")
    print("=" * 50)
    print(f"Run at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    await check_peterbot_mem()
    await check_second_brain()

    print("\n" + "=" * 50)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
