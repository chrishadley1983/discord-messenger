"""Commitment detection and tracking.

Scans outbound messages for promises/commitments Chris makes,
stores them in Supabase, and provides query methods for the nudge job.
"""

import logging
import os
import re
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# ── Promise detection patterns ──────────────────────────────────────────
# Tuned after MVP scan: removed "on it", "will do", "let me know" which
# are conversational filler, not real commitments.

PROMISE_PATTERNS = [
    # "I'll [verb]" — the core commitment pattern
    (r"\bi'?ll\s+(?:send|forward|share|get|find|check|look\s+into|sort|grab|"
     r"make|write|book|set\s+up|arrange|organise|organize|update|fix|build|"
     r"ping|chase|email|message|call|text|whatsapp|pop|drop|put|pick\s+up|"
     r"order|transfer|pay|move|add|try|have\s+a\s+look|do\s+(?:it|that|this))",
     "direct_commitment"),

    # "I need to" / "I should" + action verb
    (r"\bi\s+(?:need|should|must)\s+to\s+(?:send|forward|share|get|find|check|"
     r"look|sort|do|reply|respond|book|chase|email|message|call|text|pop|order|"
     r"pay|transfer|pick\s+up)",
     "obligation"),

    # "Leave it with me" / "I'll sort it" / "I'll handle it"
    (r"\b(?:leave\s+it\s+with\s+me|i'?ll\s+sort\s+it|i'?ll\s+handle\s+it|"
     r"i'?ll\s+take\s+care\s+of)",
     "will_do"),

    # "I'll get back to you" / "I'll follow up"
    (r"\bi'?ll\s+(?:get\s+back\s+to|come\s+back\s+to|follow\s+up|loop\s+back)",
     "follow_up"),

    # Deferred: "tomorrow I'll", "later I'll", "this weekend I'll"
    (r"\b(?:tomorrow\s+i'?ll|later\s+(?:today\s+)?i'?ll|this\s+(?:evening|"
     r"afternoon|weekend)\s+i'?ll|after\s+work\s+i'?ll|when\s+i\s+get\s+"
     r"(?:home|back|a\s+chance)\s+i'?ll)",
     "deferred"),

    # Explicit: "I promised", "I said I'd", "I told [person] I'd"
    (r"\b(?:i\s+promised|i\s+said\s+i'?d|i\s+told\s+\w+\s+i'?d)",
     "explicit_promise"),

    # Overdue acknowledgement: "I forgot to", "I still haven't", "I keep meaning to"
    (r"\b(?:forgot\s+to|i\s+still\s+haven'?t|keep\s+meaning\s+to|keep\s+forgetting\s+to)",
     "overdue"),
]

COMPILED_PATTERNS = [(re.compile(p, re.IGNORECASE), cat) for p, cat in PROMISE_PATTERNS]


def detect_commitments(text: str) -> list[dict]:
    """Scan text for commitment patterns. Returns list of matches."""
    matches = []
    seen = set()
    for pattern, category in COMPILED_PATTERNS:
        for m in pattern.finditer(text):
            matched = m.group(0)
            if matched.lower() not in seen:
                seen.add(matched.lower())
                matches.append({
                    "category": category,
                    "matched_text": matched,
                })
    return matches


# Recipient lookup: map WhatsApp JID numbers to friendly names
# This is populated from the webhook's ALLOWED_SENDERS config
_JID_TO_NAME = {
    "447855620978": "Chris",
    "447856182831": "Abby",
}


def resolve_recipient_from_jid(remote_jid: str) -> str | None:
    """Try to resolve a WhatsApp JID to a friendly name."""
    if remote_jid.endswith("@g.us"):
        return None  # Group — recipient unclear
    number = remote_jid.split("@")[0] if "@" in remote_jid else remote_jid
    return _JID_TO_NAME.get(number, number)


async def store_commitment(
    text: str,
    matched_pattern: str,
    category: str,
    recipient: str | None,
    source: str,
    source_context: str | None = None,
    source_message_id: str | None = None,
) -> bool:
    """Store a detected commitment in Supabase. Returns True on success."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.warning("No Supabase credentials — cannot store commitment")
        return False

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    payload = {
        "text": text[:500],  # Truncate long messages
        "matched_pattern": matched_pattern[:200],
        "category": category,
        "recipient": recipient,
        "source": source,
        "source_context": source_context,
        "source_message_id": source_message_id,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/commitments",
                headers=headers,
                json=payload,
            )
            if resp.status_code in (200, 201):
                logger.info(f"Commitment stored: [{category}] {matched_pattern} → {recipient}")
                return True
            else:
                logger.error(f"Commitment store failed ({resp.status_code}): {resp.text[:200]}")
                return False
    except Exception as e:
        logger.error(f"Commitment store error: {e}")
        return False


async def get_open_commitments(min_age_hours: int = 24, limit: int = 20) -> list[dict]:
    """Fetch open commitments older than min_age_hours."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }

    cutoff = datetime.now(timezone.utc).isoformat()

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/commitments",
                headers=headers,
                params={
                    "select": "*",
                    "status": "eq.open",
                    "order": "detected_at.asc",
                    "limit": str(limit),
                },
            )
            if resp.status_code == 200:
                items = resp.json()
                # Filter by age in Python (simpler than Supabase timestamp math)
                from datetime import timedelta
                age_cutoff = datetime.now(timezone.utc) - timedelta(hours=min_age_hours)
                return [
                    i for i in items
                    if datetime.fromisoformat(i["detected_at"].replace("Z", "+00:00")) < age_cutoff
                ]
            else:
                logger.error(f"Commitments fetch failed: {resp.status_code}")
                return []
    except Exception as e:
        logger.error(f"Commitments fetch error: {e}")
        return []


async def update_commitment(commitment_id: str, status: str, reason: str | None = None) -> bool:
    """Update commitment status (resolve/dismiss)."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    payload: dict = {"status": status}
    if status == "resolved":
        payload["resolved_at"] = datetime.now(timezone.utc).isoformat()
    elif status == "dismissed":
        payload["dismissed_at"] = datetime.now(timezone.utc).isoformat()
        if reason:
            payload["dismiss_reason"] = reason

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.patch(
                f"{SUPABASE_URL}/rest/v1/commitments",
                headers={**headers, "Prefer": "return=minimal"},
                params={"id": f"eq.{commitment_id}"},
                json=payload,
            )
            return resp.status_code in (200, 204)
    except Exception as e:
        logger.error(f"Commitment update error: {e}")
        return False


async def record_nudge(commitment_id: str) -> bool:
    """Increment nudge count and update last_nudged_at."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Fetch current nudge_count
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/commitments",
                headers=headers,
                params={"id": f"eq.{commitment_id}", "select": "nudge_count"},
            )
            if resp.status_code != 200 or not resp.json():
                return False
            current = resp.json()[0].get("nudge_count", 0)

            resp = await client.patch(
                f"{SUPABASE_URL}/rest/v1/commitments",
                headers={**headers, "Prefer": "return=minimal"},
                params={"id": f"eq.{commitment_id}"},
                json={
                    "nudge_count": current + 1,
                    "last_nudged_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            return resp.status_code in (200, 204)
    except Exception as e:
        logger.error(f"Nudge record error: {e}")
        return False
