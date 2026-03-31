"""Promise Scanner MVP — scan Discord + WhatsApp messages for unfulfilled commitments.

Uses Discord REST API (no gateway conflict with running bot) and Second Brain
for WhatsApp chat summaries.

Usage:
    python scripts/promise_scanner.py
"""

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Load env from project root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
LOOKBACK_DAYS = 90

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_DIR.mkdir(exist_ok=True)
LOG_PATH = OUTPUT_DIR / "promise_scan.log"
RESULTS_PATH = OUTPUT_DIR / "promise_scan_results.json"

# ── Logging ─────────────────────────────────────────────────────────────

_log_file = None

def log(msg: str = ""):
    global _log_file
    if _log_file is None:
        _log_file = open(LOG_PATH, "w", encoding="utf-8")
    # Safe print for Windows cp1252
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode(), flush=True)
    _log_file.write(msg + "\n")
    _log_file.flush()

# ── Promise detection patterns ──────────────────────────────────────────

PROMISE_PATTERNS = [
    # Direct commitments
    (r"\bi'?ll\s+(?:send|forward|share|get|find|check|look\s+into|sort|grab|do|make|write|book|set\s+up|arrange|organise|organize|update|fix|build|ping|chase|email|message|call|text|whatsapp|pop|drop|put|pick|order|transfer|pay|move|add|try|have\s+a\s+look)",
     "direct_commitment"),
    # "Let me" intentions
    (r"\blet\s+me\s+(?:send|forward|share|get|find|check|look|sort|grab|do|know|see|think|have\s+a\s+look|pop|drop|have\s+a\s+think)",
     "let_me"),
    # "I need to" / "I should"
    (r"\bi\s+(?:need|should|ought|must)\s+(?:to\s+)?(?:send|forward|share|get|find|check|look|sort|do|reply|respond|book|chase|email|message|call|text|pop|order|pay|transfer|pick\s+up)",
     "obligation"),
    # "Will do" / "on it"
    (r"\b(?:will\s+do|on\s+it|i'?m\s+on\s+it|leave\s+it\s+with\s+me|i'?ll\s+sort\s+it|i'?ll\s+handle|i'?ll\s+take\s+care)",
     "will_do"),
    # "Remind me"
    (r"\bremind\s+me\s+(?:to|about|later|tomorrow|next)",
     "remind_me"),
    # "I owe you" / "I still need to"
    (r"\b(?:i\s+owe\s+you|i\s+still\s+need\s+to|i\s+haven'?t\s+(?:sent|done|finished|replied|responded))",
     "debt_acknowledgement"),
    # "I'll get back to" / "I'll come back to"
    (r"\bi'?ll\s+(?:get\s+back|come\s+back|circle\s+back|follow\s+up|loop\s+back)",
     "follow_up"),
    # Deferred actions
    (r"\b(?:after\s+\w+\s+i'?ll|when\s+i\s+get\s+(?:a\s+)?chance|tomorrow\s+i'?ll|later\s+(?:today\s+)?i'?ll|this\s+(?:evening|afternoon|weekend)\s+i'?ll|at\s+some\s+point\s+i'?ll)",
     "deferred"),
    # Delegation to Peter
    (r"\b(?:can\s+you\s+remind|peter.*remind|remind.*peter)",
     "delegation_to_peter"),
    # Explicit promises
    (r"\b(?:i\s+promised|i\s+said\s+i'?d|i\s+told\s+(?:her|him|them|you|abby|dad|mum)\s+i'?d)",
     "explicit_promise"),
    # Transfer / send to someone
    (r"\b(?:need\s+to\s+(?:get|send)\s+\w+\s+to\s+\w+|should\s+(?:get|send)\s+\w+\s+to\s+\w+)",
     "transfer"),
    # Overdue / haven't done
    (r"\b(?:haven'?t\s+(?:replied|responded|got\s+back|sent|done|sorted|booked|paid)|still\s+haven'?t|forgot\s+to|keep\s+meaning\s+to|keep\s+forgetting)",
     "overdue"),
]

COMPILED_PATTERNS = [(re.compile(p, re.IGNORECASE), cat) for p, cat in PROMISE_PATTERNS]


def detect_promises(text: str) -> list[dict]:
    matches = []
    for pattern, category in COMPILED_PATTERNS:
        for m in pattern.finditer(text):
            matches.append({
                "category": category,
                "matched_text": m.group(0),
            })
    return matches


# ── Discord REST API ────────────────────────────────────────────────────

DISCORD_API = "https://discord.com/api/v10"


async def discord_get(client: httpx.AsyncClient, path: str, params: dict = None) -> dict | list:
    resp = await client.get(
        f"{DISCORD_API}{path}",
        headers={"Authorization": f"Bot {DISCORD_TOKEN}"},
        params=params or {},
    )
    if resp.status_code == 429:
        retry_after = resp.json().get("retry_after", 1)
        log(f"  ⏳ Rate limited, waiting {retry_after}s...")
        await asyncio.sleep(retry_after)
        return await discord_get(client, path, params)
    resp.raise_for_status()
    return resp.json()


async def get_guilds(client: httpx.AsyncClient) -> list:
    return await discord_get(client, "/users/@me/guilds")


async def get_channels(client: httpx.AsyncClient, guild_id: str) -> list:
    return await discord_get(client, f"/guilds/{guild_id}/channels")


async def get_messages(client: httpx.AsyncClient, channel_id: str, after: str = None, limit: int = 100) -> list:
    params = {"limit": limit}
    if after:
        params["after"] = after
    return await discord_get(client, f"/channels/{channel_id}/messages", params)


async def fetch_all_messages(client: httpx.AsyncClient, channel_id: str, channel_name: str, cutoff: datetime) -> list[dict]:
    """Fetch all messages from a channel after cutoff date."""
    # Convert cutoff to Discord snowflake
    # Discord epoch: 2015-01-01T00:00:00Z = 1420070400000 ms
    discord_epoch = 1420070400000
    cutoff_ms = int(cutoff.timestamp() * 1000)
    cutoff_snowflake = str((cutoff_ms - discord_epoch) << 22)

    all_messages = []
    after = cutoff_snowflake
    batch = 0

    while True:
        batch += 1
        try:
            messages = await get_messages(client, channel_id, after=after, limit=100)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                log(f"  ⛔ No access to #{channel_name}")
                return []
            raise

        if not messages:
            break

        all_messages.extend(messages)
        after = messages[0]["id"]  # Messages come newest-first, so first is the newest

        if batch % 5 == 0:
            log(f"    ... #{channel_name}: fetched {len(all_messages)} messages so far")

        # Check if we've gone past our cutoff (messages are newest-first)
        oldest_in_batch = messages[-1]
        oldest_ts = datetime.fromisoformat(oldest_in_batch["timestamp"].replace("+00:00", "+00:00"))
        if oldest_ts < cutoff:
            break

        await asyncio.sleep(0.5)  # Be nice to the API

    return all_messages


async def scan_discord() -> list[dict]:
    """Scan all Discord channels for promises."""
    results = []

    async with httpx.AsyncClient(timeout=30) as client:
        guilds = await get_guilds(client)
        log(f"📡 Discord: found {len(guilds)} servers")

        for guild in guilds:
            guild_name = guild["name"]
            guild_id = guild["id"]
            log(f"\n🏠 Server: {guild_name}")

            channels = await get_channels(client, guild_id)
            text_channels = [c for c in channels if c["type"] == 0]  # 0 = text channel
            log(f"   {len(text_channels)} text channels")

            cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

            for ch in text_channels:
                ch_name = ch["name"]
                ch_id = ch["id"]

                messages = await fetch_all_messages(client, ch_id, ch_name, cutoff)
                if not messages:
                    continue

                # Filter to non-bot messages only (Chris's messages)
                human_msgs = [m for m in messages if not m.get("author", {}).get("bot", False)]

                found = 0
                for msg in human_msgs:
                    content = msg.get("content", "")
                    if not content:
                        continue

                    promises = detect_promises(content)
                    if promises:
                        found += 1
                        ts = msg["timestamp"]
                        dt = datetime.fromisoformat(ts)
                        results.append({
                            "channel": f"#{ch_name}",
                            "channel_id": ch_id,
                            "message_id": msg["id"],
                            "timestamp": ts,
                            "date": dt.strftime("%Y-%m-%d %H:%M"),
                            "content": content[:500],
                            "matches": promises,
                            "categories": list({p["category"] for p in promises}),
                            "jump_url": f"https://discord.com/channels/{guild_id}/{ch_id}/{msg['id']}",
                            "source": "discord",
                        })

                if human_msgs:
                    log(f"  📨 #{ch_name}: {len(human_msgs)} human messages, {found} promises")

    return results


# ── WhatsApp from Second Brain ──────────────────────────────────────────

async def scan_whatsapp_from_second_brain() -> list[dict]:
    """Fetch WhatsApp chat summaries from Second Brain and scan for promises."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        log("  ⚠️  No Supabase credentials — skipping WhatsApp scan")
        return []

    results = []
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/knowledge_items",
            headers=headers,
            params={
                "select": "id,title,full_text,source,created_at",
                "source": "like.whatsapp://*",
                "order": "created_at.desc",
                "limit": "100",
            },
        )
        if resp.status_code != 200:
            log(f"  ❌ Supabase error: {resp.status_code} {resp.text[:200]}")
            return []

        items = resp.json()
        log(f"  📱 Found {len(items)} WhatsApp chat summaries in Second Brain")

        for item in items:
            text = item.get("full_text", "")
            title = item.get("title", "Unknown")
            if not text:
                continue

            # Scan the full text for promise patterns
            promises = detect_promises(text)

            # Also extract structured action items from chat summaries
            action_items = []
            in_action_section = False
            for line in text.split("\n"):
                lower = line.lower().strip()
                if "action item" in lower or "to-do" in lower or "to do" in lower:
                    in_action_section = True
                    continue
                if in_action_section:
                    if line.startswith("#") or (line.strip() == "" and action_items):
                        in_action_section = False
                        continue
                    stripped = line.strip().lstrip("- •*")
                    if stripped and not any(skip in stripped.lower() for skip in
                                           ["none", "no action", "no clear", "not identified",
                                            "no specific", "n/a"]):
                        action_items.append(stripped)

            if promises or action_items:
                all_matches = promises.copy()
                for ai in action_items:
                    all_matches.append({
                        "category": "whatsapp_action_item",
                        "matched_text": ai[:100],
                    })

                categories = list({m["category"] for m in all_matches})
                created = item.get("created_at", "")

                results.append({
                    "channel": f"📱 {title}",
                    "channel_id": None,
                    "message_id": item["id"],
                    "timestamp": created,
                    "date": datetime.fromisoformat(created.replace("Z", "+00:00")).strftime("%Y-%m-%d") if created else "unknown",
                    "content": text[:500],
                    "matches": all_matches,
                    "categories": categories,
                    "jump_url": None,
                    "source": "whatsapp_second_brain",
                })

    log(f"  📱 WhatsApp: {len(results)} items with promises/action items")
    return results


# ── Report ──────────────────────────────────────────────────────────────

def print_report(all_results: list[dict]):
    log()
    log("=" * 70)
    log(f"PROMISE SCANNER RESULTS — {len(all_results)} commitments detected")
    log("=" * 70)

    if not all_results:
        log("No promises detected.")
        return

    # Sort by date (newest first)
    all_results.sort(key=lambda x: x["timestamp"], reverse=True)

    # Category breakdown
    cat_counts: dict[str, int] = {}
    for r in all_results:
        for cat in r["categories"]:
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

    log()
    log("📊 Category Breakdown:")
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        label = cat.replace("_", " ").title()
        log(f"   {label:30s} {count:4d}")

    # Source breakdown
    source_counts: dict[str, int] = {}
    for r in all_results:
        src = r.get("source", "discord")
        source_counts[src] = source_counts.get(src, 0) + 1

    log()
    log("🔌 Source Breakdown:")
    for src, count in sorted(source_counts.items(), key=lambda x: -x[1]):
        log(f"   {src:30s} {count:4d}")

    # Channel breakdown
    ch_counts: dict[str, int] = {}
    for r in all_results:
        ch_counts[r["channel"]] = ch_counts.get(r["channel"], 0) + 1

    log()
    log("📍 Channel Breakdown:")
    for ch, count in sorted(ch_counts.items(), key=lambda x: -x[1]):
        log(f"   {ch:30s} {count:4d}")

    # Timeline (by week)
    week_counts: dict[str, int] = {}
    for r in all_results:
        try:
            dt = datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00"))
            week_key = f"{dt:%Y-W%W}"
            week_counts[week_key] = week_counts.get(week_key, 0) + 1
        except (ValueError, AttributeError):
            pass

    log()
    log("📈 Weekly Distribution:")
    for week, count in sorted(week_counts.items()):
        bar = "█" * min(count, 50)
        log(f"   {week}  {bar} ({count})")

    # Full list
    log()
    log("─" * 70)
    log("DETAILED FINDINGS (newest first)")
    log("─" * 70)

    for i, r in enumerate(all_results, 1):
        cats = ", ".join(r["categories"])
        matched = " | ".join(m["matched_text"] for m in r["matches"][:5])  # Cap at 5
        log()
        log(f"[{i:3d}] {r['date']}  {r['channel']}")
        log(f"      Categories: {cats}")
        log(f"      Matched: {matched}")
        for line in r["content"].split("\n")[:8]:  # Cap content lines
            log(f"      > {line}")

    # Save raw JSON
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "scan_date": datetime.now(timezone.utc).isoformat(),
            "lookback_days": LOOKBACK_DAYS,
            "total_promises": len(all_results),
            "category_counts": cat_counts,
            "source_counts": source_counts,
            "channel_counts": ch_counts,
            "results": all_results,
        }, f, indent=2, ensure_ascii=False)
    log()
    log(f"💾 Raw data saved to: {RESULTS_PATH}")


# ── Main ────────────────────────────────────────────────────────────────

async def main():
    if not DISCORD_TOKEN:
        log("ERROR: DISCORD_TOKEN not set in .env")
        sys.exit(1)

    log(f"📅 Scanning last {LOOKBACK_DAYS} days ({datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS):%Y-%m-%d} → now)")
    log()

    # Run both scans
    discord_results = await scan_discord()
    log()
    log("📱 Scanning WhatsApp chat summaries from Second Brain...")
    whatsapp_results = await scan_whatsapp_from_second_brain()

    all_results = discord_results + whatsapp_results
    print_report(all_results)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        if _log_file:
            _log_file.close()
