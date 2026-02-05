"""Daily Embedding Report job.

Runs at 3am to generate a report of embeddings across all memory systems:
- Claude-mem (Chris's Claude Code sessions)
- Peter-mem (Peterbot conversations)
- Second Brain (split by Chris/Peter/Incremental Seed)

Posts report to #alerts channel with 5 examples from each category.
"""

import asyncio
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from logger import logger

# Alerts channel for posting report
ALERTS_CHANNEL_ID = 1466019126194606286

# Windows subprocess config
IS_WINDOWS = sys.platform == "win32"
if IS_WINDOWS:
    STARTUPINFO = subprocess.STARTUPINFO()
    STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    STARTUPINFO.wShowWindow = subprocess.SW_HIDE
    CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW
else:
    STARTUPINFO = None
    CREATE_NO_WINDOW = 0


async def _get_claudemem_stats(hours: int = 24) -> dict:
    """Get Claude-mem observations from last N hours via WSL.

    Returns:
        Dict with count and examples
    """
    cutoff_epoch = int((datetime.now() - timedelta(hours=hours)).timestamp() * 1000)

    query_script = f'''
import sqlite3
import json
conn = sqlite3.connect('/home/chris_hadley/.claude-mem/claude-mem.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Count observations in time window
cur.execute("""
    SELECT COUNT(*) as count FROM observations
    WHERE created_at_epoch > {cutoff_epoch}
""")
count = cur.fetchone()['count']

# Get 5 recent examples
cur.execute("""
    SELECT id, title, type, project, created_at_epoch
    FROM observations
    WHERE created_at_epoch > {cutoff_epoch}
    ORDER BY created_at_epoch DESC
    LIMIT 5
""")
examples = [dict(r) for r in cur.fetchall()]

print(json.dumps({{"count": count, "examples": examples}}))
'''

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["wsl", "--", "python3", "-c", query_script],
            capture_output=True,
            text=True,
            timeout=30,
            startupinfo=STARTUPINFO,
            creationflags=CREATE_NO_WINDOW if IS_WINDOWS else 0,
        )

        if result.returncode == 0:
            return json.loads(result.stdout.strip())
        else:
            logger.error(f"Claude-mem query failed: {result.stderr}")
            return {"count": 0, "examples": [], "error": result.stderr}

    except Exception as e:
        logger.error(f"Claude-mem query error: {e}")
        return {"count": 0, "examples": [], "error": str(e)}


async def _get_petermem_stats(hours: int = 24) -> dict:
    """Get Peter-mem captures from last N hours.

    Returns:
        Dict with count and examples
    """
    from domains.peterbot import config as peterbot_config

    cutoff = int((datetime.now() - timedelta(hours=hours)).timestamp())
    db_path = Path(peterbot_config.CAPTURE_STORE_DB)

    if not db_path.exists():
        return {"count": 0, "examples": [], "error": "Database not found"}

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Count captures in time window (sent status = successfully embedded)
        cur.execute("""
            SELECT COUNT(*) as count FROM pending_captures
            WHERE created_at > ? AND status = 'sent'
        """, (cutoff,))
        count = cur.fetchone()['count']

        # Get 5 recent examples
        cur.execute("""
            SELECT id, user_message, channel, created_at
            FROM pending_captures
            WHERE created_at > ? AND status = 'sent'
            ORDER BY created_at DESC
            LIMIT 5
        """, (cutoff,))
        examples = []
        for row in cur.fetchall():
            examples.append({
                "id": row["id"],
                "preview": row["user_message"][:80],
                "channel": row["channel"],
                "created_at": row["created_at"],
            })

        conn.close()
        return {"count": count, "examples": examples}

    except Exception as e:
        logger.error(f"Peter-mem query error: {e}")
        return {"count": 0, "examples": [], "error": str(e)}


async def _get_secondbrain_stats(hours: int = 24) -> dict:
    """Get Second Brain items from last N hours, split by capture type.

    Returns:
        Dict with counts and examples per capture type
    """
    from config import SUPABASE_URL, SUPABASE_KEY
    import httpx

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }

    result = {
        "explicit": {"count": 0, "examples": []},  # Chris (explicit saves)
        "passive": {"count": 0, "examples": []},   # Peter (passive captures)
        "seed": {"count": 0, "examples": []},      # Incremental seed
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Query for each capture type
            for capture_type in ["explicit", "passive", "seed"]:
                # Get count
                response = await client.get(
                    f"{SUPABASE_URL}/rest/v1/knowledge_items",
                    headers={**headers, "Prefer": "count=exact"},
                    params={
                        "capture_type": f"eq.{capture_type}",
                        "created_at": f"gte.{cutoff}",
                        "status": "eq.active",
                        "select": "id",
                    },
                )

                if response.status_code in (200, 206):
                    count = response.headers.get("content-range", "0-0/0").split("/")[-1]
                    result[capture_type]["count"] = int(count)

                # Get examples
                response = await client.get(
                    f"{SUPABASE_URL}/rest/v1/knowledge_items",
                    headers=headers,
                    params={
                        "capture_type": f"eq.{capture_type}",
                        "created_at": f"gte.{cutoff}",
                        "status": "eq.active",
                        "select": "id,title,content_type,created_at",
                        "order": "created_at.desc",
                        "limit": "5",
                    },
                )

                if response.status_code in (200, 206):
                    items = response.json()
                    result[capture_type]["examples"] = [
                        {
                            "id": item["id"][:8],
                            "title": (item.get("title") or "Untitled")[:60],
                            "type": item.get("content_type", "unknown"),
                        }
                        for item in items
                    ]

        return result

    except Exception as e:
        logger.error(f"Second Brain query error: {e}")
        return {
            "explicit": {"count": 0, "examples": [], "error": str(e)},
            "passive": {"count": 0, "examples": []},
            "seed": {"count": 0, "examples": []},
        }


def _format_timestamp(epoch_ms: int) -> str:
    """Format epoch milliseconds to readable time."""
    return datetime.fromtimestamp(epoch_ms / 1000).strftime("%H:%M")


def _format_timestamp_s(epoch_s: int) -> str:
    """Format epoch seconds to readable time."""
    return datetime.fromtimestamp(epoch_s).strftime("%H:%M")


async def generate_embedding_report(bot):
    """Generate and post the daily embedding report."""
    logger.info("Generating daily embedding report")

    channel = bot.get_channel(ALERTS_CHANNEL_ID)
    if not channel:
        try:
            channel = await bot.fetch_channel(ALERTS_CHANNEL_ID)
        except Exception as e:
            logger.error(f"Could not find #alerts channel: {e}")
            return

    # Gather stats from all sources
    claudemem = await _get_claudemem_stats(24)
    petermem = await _get_petermem_stats(24)
    secondbrain = await _get_secondbrain_stats(24)

    # Build report
    lines = [
        "📊 **Daily Embedding Report** (last 24 hours)",
        "",
    ]

    # Claude-mem section
    lines.append("## Claude-mem (Chris's Claude Code)")
    lines.append(f"**Items embedded:** {claudemem['count']}")
    if claudemem.get("error"):
        lines.append(f"⚠️ Error: {claudemem['error'][:50]}")
    elif claudemem["examples"]:
        for ex in claudemem["examples"]:
            ts = _format_timestamp(ex["created_at_epoch"])
            title = (ex.get("title") or "Untitled")[:50]
            lines.append(f"  • [{ts}] {title}")
    lines.append("")

    # Peter-mem section
    lines.append("## Peter-mem (Peterbot conversations)")
    lines.append(f"**Items embedded:** {petermem['count']}")
    if petermem.get("error"):
        lines.append(f"⚠️ Error: {petermem['error'][:50]}")
    elif petermem["examples"]:
        for ex in petermem["examples"]:
            ts = _format_timestamp_s(ex["created_at"])
            preview = ex["preview"][:40]
            lines.append(f"  • [{ts}] {preview}...")
    lines.append("")

    # Second Brain section
    lines.append("## Second Brain")

    # Explicit (Chris)
    explicit = secondbrain["explicit"]
    lines.append(f"### From Chris (explicit saves): {explicit['count']} items")
    if explicit.get("error"):
        lines.append(f"⚠️ Error: {explicit['error'][:50]}")
    elif explicit["examples"]:
        for ex in explicit["examples"]:
            lines.append(f"  • {ex['title']}")
    else:
        lines.append("  (none)")

    # Passive (Peter)
    passive = secondbrain["passive"]
    lines.append(f"### From Peter (passive captures): {passive['count']} items")
    if passive["examples"]:
        for ex in passive["examples"]:
            lines.append(f"  • {ex['title']}")
    else:
        lines.append("  (none)")

    # Seed (Incremental)
    seed = secondbrain["seed"]
    lines.append(f"### Incremental Seed: {seed['count']} items")
    if seed["examples"]:
        for ex in seed["examples"]:
            lines.append(f"  • {ex['title']}")
    else:
        lines.append("  (none)")

    # Calculate totals
    total_claudemem = claudemem["count"]
    total_petermem = petermem["count"]
    total_secondbrain = explicit["count"] + passive["count"] + seed["count"]
    grand_total = total_claudemem + total_petermem + total_secondbrain

    lines.append("")
    lines.append(f"**Total embeddings (24h):** {grand_total}")
    lines.append(f"  Claude-mem: {total_claudemem} | Peter-mem: {total_petermem} | Second Brain: {total_secondbrain}")

    message = "\n".join(lines)

    # Discord has 2000 char limit - truncate if needed
    if len(message) > 1900:
        message = message[:1900] + "\n...(truncated)"

    try:
        await channel.send(message)
        logger.info(f"Posted embedding report - total: {grand_total}")
    except Exception as e:
        logger.error(f"Failed to post embedding report: {e}")


def register_embedding_report(scheduler, bot):
    """Register the embedding report job with the scheduler.

    Args:
        scheduler: APScheduler instance
        bot: Discord bot instance
    """
    scheduler.add_job(
        generate_embedding_report,
        'cron',
        args=[bot],
        hour=3,
        minute=0,
        timezone="Europe/London",
        id="embedding_report",
        max_instances=1,
        coalesce=True,
    )
    logger.info("Registered embedding report job (daily at 3:00 AM UK)")
