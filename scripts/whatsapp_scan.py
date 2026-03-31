"""Quick WhatsApp promise scan from Second Brain."""
import asyncio, json, os, re, sys
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OUT = Path(__file__).resolve().parent.parent / "data" / "whatsapp_scan.log"

PROMISE_PATTERNS = [
    (r"\bi'?ll\s+(?:send|forward|share|get|find|check|look\s+into|sort|grab|do|make|write|book|set\s+up|arrange|organise|organize|update|fix|build|ping|chase|email|message|call|text|whatsapp|pop|drop|put|pick|order|transfer|pay|move|add|try|have\s+a\s+look)", "direct_commitment"),
    (r"\blet\s+me\s+(?:send|forward|share|get|find|check|look|sort|grab|do|know|see|think|have\s+a\s+look|pop|drop|have\s+a\s+think)", "let_me"),
    (r"\bi\s+(?:need|should|ought|must)\s+(?:to\s+)?(?:send|forward|share|get|find|check|look|sort|do|reply|respond|book|chase|email|message|call|text|pop|order|pay|transfer|pick\s+up)", "obligation"),
    (r"\b(?:will\s+do|on\s+it|i'm\s+on\s+it|leave\s+it\s+with\s+me|i'll\s+sort\s+it|i'll\s+handle|i'll\s+take\s+care)", "will_do"),
    (r"\bremind\s+me\s+(?:to|about|later|tomorrow|next)", "remind_me"),
    (r"\b(?:i\s+owe\s+you|i\s+still\s+need\s+to|i\s+haven'?t\s+(?:sent|done|finished|replied|responded))", "debt_acknowledgement"),
    (r"\bi'?ll\s+(?:get\s+back|come\s+back|circle\s+back|follow\s+up|loop\s+back)", "follow_up"),
    (r"\b(?:haven'?t\s+(?:replied|responded|got\s+back|sent|done|sorted|booked|paid)|still\s+haven'?t|forgot\s+to|keep\s+meaning\s+to|keep\s+forgetting)", "overdue"),
]
COMPILED = [(re.compile(p, re.IGNORECASE), c) for p, c in PROMISE_PATTERNS]


def detect(text):
    matches = []
    for pat, cat in COMPILED:
        for m in pat.finditer(text):
            matches.append({"category": cat, "matched": m.group(0)})
    return matches


async def main():
    f = open(OUT, "w", encoding="utf-8")

    def log(msg=""):
        f.write(msg + "\n")
        f.flush()

    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/knowledge_items",
            headers=headers,
            params={
                "select": "id,title,full_text,source_url,created_at",
                "source_url": "like.whatsapp://*",
                "order": "created_at.desc",
                "limit": "100",
            },
        )
        items = resp.json()
        log(f"Found {len(items)} WhatsApp items in Second Brain")

        found = 0
        for item in items:
            text = item.get("full_text", "")
            title = item.get("title", "")

            # Pattern matches on raw text
            promises = detect(text)

            # Action items from structured summaries
            action_items = []
            in_action = False
            for line in text.split("\n"):
                lower = line.lower().strip()
                if "action item" in lower or "to-do" in lower or "to do" in lower:
                    in_action = True
                    continue
                if in_action:
                    if line.startswith("#") or (line.strip() == "" and action_items):
                        in_action = False
                        continue
                    stripped = line.strip().lstrip("- *")
                    if stripped and not any(s in stripped.lower() for s in
                                           ["none", "no action", "no clear", "not identified",
                                            "no specific", "n/a", "*no "]):
                        action_items.append(stripped)

            if promises or action_items:
                found += 1
                log(f"\n--- {title} ---")
                if promises:
                    for p in promises:
                        log(f"  [PATTERN] {p['category']}: {p['matched']}")
                if action_items:
                    for ai in action_items:
                        log(f"  [ACTION ITEM] {ai}")

        log(f"\n{'='*60}")
        log(f"TOTAL: {found}/{len(items)} WhatsApp conversations had promises/action items")

    f.close()
    # Print to console safely
    with open(OUT, "r", encoding="utf-8") as rf:
        for line in rf:
            try:
                print(line, end="")
            except UnicodeEncodeError:
                print(line.encode("ascii", errors="replace").decode(), end="")


asyncio.run(main())
