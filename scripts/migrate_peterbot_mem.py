"""Migrate peterbot-mem observations to Second Brain.

One-off script to read all observations from the claude-mem SQLite database
and import them into Second Brain (Supabase + pgvector).

Usage:
    python scripts/migrate_peterbot_mem.py [--dry-run] [--limit N] [--skip-existing]

The script:
1. Reads all observations from ~/.claude-mem/claude-mem.db (or AppData path)
2. Maps each to a KnowledgeItem with content_type=CONVERSATION_EXTRACT
3. Runs through the Second Brain pipeline (summarise, tag, extract, embed, store)
4. Preserves original timestamps
5. Logs migration stats
"""

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from domains.second_brain.pipeline import process_capture
from domains.second_brain.types import CaptureType, ContentType
from domains.second_brain import db as sb_db
from logger import logger


# Possible locations for peterbot-mem database
def _candidate_paths() -> list[Path]:
    paths = []
    env_db = os.environ.get("CLAUDE_MEM_DB", "").strip()
    if env_db:
        paths.append(Path(env_db))
    paths.append(Path.home() / ".claude-mem" / "claude-mem.db")
    temp = os.environ.get("TEMP", "").strip()
    if temp:
        paths.append(Path(temp) / "claude" / "claude-mem.db")
    paths.append(Path(r"C:\Users\Chris Hadley\AppData\Local\Temp\claude\claude-mem.db"))
    return paths


def find_db() -> Path:
    """Find the peterbot-mem SQLite database."""
    for p in _candidate_paths():
        if p.exists():
            return p
    raise FileNotFoundError(
        f"Could not find claude-mem.db. Searched: {[str(p) for p in _candidate_paths()]}"
    )


def read_observations(db_path: Path, limit: int = 0) -> list[dict]:
    """Read all observations from the peterbot-mem database."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    query = "SELECT * FROM observations WHERE is_active = 1 ORDER BY created_at ASC"
    if limit:
        query += f" LIMIT {limit}"

    cur.execute(query)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def parse_json_field(value: str | None) -> list:
    """Safely parse a JSON string field from peterbot-mem."""
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return parsed
        return []
    except (json.JSONDecodeError, TypeError):
        return []


def observation_to_text(obs: dict) -> str:
    """Convert a peterbot-mem observation to plain text for Second Brain ingestion."""
    parts = []

    if obs.get("title"):
        parts.append(f"# {obs['title']}")

    if obs.get("subtitle"):
        parts.append(obs["subtitle"])

    if obs.get("narrative"):
        parts.append(obs["narrative"])

    facts = parse_json_field(obs.get("facts"))
    if facts:
        parts.append("\nFacts:")
        for fact in facts:
            if isinstance(fact, str):
                parts.append(f"- {fact}")

    concepts = parse_json_field(obs.get("concepts"))
    if concepts:
        parts.append("\nConcepts:")
        for concept in concepts:
            if isinstance(concept, str):
                parts.append(f"- {concept}")
            elif isinstance(concept, dict):
                label = concept.get("label", "")
                detail = concept.get("detail", "")
                parts.append(f"- {label}: {detail}" if detail else f"- {label}")

    return "\n\n".join(parts)


def parse_timestamp(obs: dict) -> datetime | None:
    """Parse the created_at timestamp from an observation."""
    ts = obs.get("created_at")
    if not ts:
        return None
    try:
        # Format: "2026-02-03T08:43:56.241Z"
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


async def migrate_observation(obs: dict, dry_run: bool = False, skip_existing: bool = True) -> str:
    """Migrate a single observation to Second Brain.

    Returns: "migrated", "skipped", "skipped_duplicate", or "failed"
    """
    text = observation_to_text(obs)
    if not text or len(text) < 20:
        return "skipped"

    title = obs.get("title", "")
    source_id = f"peterbot-mem-{obs['id']}"
    obs_id_str = str(obs['id'])

    # Check for existing item with same source_message_id + source_system
    if skip_existing:
        try:
            import httpx
            rest_url = sb_db._get_rest_url()
            headers = sb_db._get_headers()
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{rest_url}/knowledge_items?source_system=eq.peterbot-mem-migration&source_message_id=eq.{obs_id_str}&select=id&limit=1",
                    headers=headers,
                    timeout=10,
                )
                if resp.status_code == 200 and resp.json():
                    return "skipped_duplicate"
        except Exception:
            pass  # If dedup check fails, proceed with migration

    if dry_run:
        logger.info(f"[DRY RUN] Would migrate obs #{obs['id']}: {title[:60]}")
        return "migrated"

    try:
        # Pre-parsed facts and concepts from peterbot-mem
        facts = parse_json_field(obs.get("facts"))
        facts = [f for f in facts if isinstance(f, str) and len(f) >= 5][:8]

        concepts_raw = parse_json_field(obs.get("concepts"))
        concepts = []
        for c in concepts_raw:
            if isinstance(c, str):
                # peterbot-mem stores concept types as plain strings
                concepts.append({"label": c, "type": c, "detail": ""})
            elif isinstance(c, dict):
                concepts.append(c)

        # Map peterbot-mem category to topics
        category = obs.get("category", "")
        user_tags = ["peterbot-mem-migration"]
        if category:
            user_tags.append(category)

        original_timestamp = parse_timestamp(obs)

        item = await process_capture(
            source=source_id,
            text=text,
            capture_type=CaptureType.PASSIVE,
            content_type_override=ContentType.CONVERSATION_EXTRACT,
            source_system="peterbot-mem-migration",
            source_message_id=str(obs["id"]),
            user_tags=user_tags,
            title_override=title or None,
            facts_override=facts if facts else None,
            concepts_override=concepts if concepts else None,
            created_at_override=original_timestamp,
        )

        if item:
            logger.info(f"Migrated obs #{obs['id']}: {title[:60]}")
            return "migrated"
        else:
            logger.warning(f"Pipeline returned None for obs #{obs['id']}: {title[:60]}")
            return "failed"

    except Exception as e:
        logger.error(f"Failed to migrate obs #{obs['id']}: {e}")
        return "failed"


async def main():
    parser = argparse.ArgumentParser(description="Migrate peterbot-mem to Second Brain")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of observations")
    parser.add_argument("--skip-existing", action="store_true", default=True, help="Skip already-migrated items")
    parser.add_argument("--no-skip-existing", dest="skip_existing", action="store_false")
    args = parser.parse_args()

    db_path = find_db()
    print(f"Found peterbot-mem database: {db_path}")

    observations = read_observations(db_path, limit=args.limit)
    total = len(observations)
    print(f"Found {total} active observations to migrate")

    if args.dry_run:
        print("[DRY RUN MODE — no data will be written]")

    stats = {"migrated": 0, "skipped": 0, "skipped_duplicate": 0, "failed": 0}

    for i, obs in enumerate(observations, 1):
        result = await migrate_observation(obs, dry_run=args.dry_run, skip_existing=args.skip_existing)
        stats[result] += 1

        if i % 50 == 0 or i == total:
            print(f"  Progress: {i}/{total} — migrated={stats['migrated']}, skipped={stats['skipped']}, dupes={stats['skipped_duplicate']}, failed={stats['failed']}")

    print(f"\n{'='*50}")
    print(f"Migration complete!")
    print(f"  Total observations: {total}")
    print(f"  Migrated:           {stats['migrated']}")
    print(f"  Skipped (empty):    {stats['skipped']}")
    print(f"  Skipped (existing): {stats['skipped_duplicate']}")
    print(f"  Failed:             {stats['failed']}")
    print(f"{'='*50}")


if __name__ == "__main__":
    asyncio.run(main())
