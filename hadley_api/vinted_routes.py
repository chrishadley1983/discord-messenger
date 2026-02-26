"""Vinted collections tracker - parses Gmail for parcels ready to collect."""

from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
import json
import re
import base64
from html import unescape

router = APIRouter(prefix="/vinted")

UK_TZ = ZoneInfo("Europe/London")
DEDUP_FILE = Path(__file__).parent.parent / "data" / "vinted_collections_reported.json"


def _html_to_text(html_content: str) -> str:
    """Convert HTML to plain text (same logic as gmail_get)."""
    text = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?(p|div|tr|li|h[1-6])[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<td[^>]*>', ' | ', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n[ \t]+', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _extract_body(payload: dict) -> str:
    """Recursively extract text body from Gmail message payload."""
    plain_text = ""
    html_text = ""

    def extract_content(part):
        nonlocal plain_text, html_text
        mime_type = part.get('mimeType', '')
        if mime_type == 'text/plain':
            data = part.get('body', {}).get('data', '')
            if data:
                plain_text += base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        elif mime_type == 'text/html':
            data = part.get('body', {}).get('data', '')
            if data:
                html_text += base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        elif mime_type.startswith('multipart/') or 'parts' in part:
            for subpart in part.get('parts', []):
                extract_content(subpart)

    extract_content(payload)

    if not plain_text and not html_text:
        data = payload.get('body', {}).get('data', '')
        if data:
            content = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
            if payload.get('mimeType', '') == 'text/html':
                html_text = content
            else:
                plain_text = content

    return plain_text if plain_text else _html_to_text(html_text) if html_text else ""


def _load_reported() -> dict:
    """Load previously reported email IDs."""
    if DEDUP_FILE.exists():
        try:
            return json.loads(DEDUP_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_reported(reported: dict) -> None:
    """Save reported email IDs."""
    DEDUP_FILE.parent.mkdir(parents=True, exist_ok=True)
    DEDUP_FILE.write_text(json.dumps(reported, indent=2))


SERVICE_PATTERNS = {
    "InPost": re.compile(r'inpost', re.IGNORECASE),
    "Evri": re.compile(r'evri|hermes', re.IGNORECASE),
    "Royal Mail": re.compile(r'royal\s*mail', re.IGNORECASE),
    "Yodel": re.compile(r'yodel', re.IGNORECASE),
    "DPD": re.compile(r'\bdpd\b', re.IGNORECASE),
}

# Regex to extract service + location from email body
LOCATION_RE = re.compile(r'waiting for you at (.+?)\.\s*Go', re.DOTALL)


def _detect_service(text: str) -> str:
    """Detect delivery service from text."""
    for name, pattern in SERVICE_PATTERNS.items():
        if pattern.search(text):
            return name
    return "Unknown"


def _parse_collection(subject: str, body: str, date_str: str) -> dict:
    """Parse a single collection email into structured data."""
    # Item name from subject
    item = subject
    if item.lower().startswith("order update for "):
        item = item[len("Order update for "):]

    # Service + location from body
    service = "Unknown"
    location = ""
    match = LOCATION_RE.search(body)
    if match:
        full_location = match.group(1).strip()
        # Clean up any whitespace/newlines from HTML parsing
        full_location = re.sub(r'\s+', ' ', full_location)
        # Remove trailing "Please pick it up" if regex captured it
        full_location = re.sub(r'\.\s*Please pick it up$', '', full_location, flags=re.IGNORECASE).strip()
        # Split on first " - " to separate service from address
        parts = full_location.split(" - ", 1)
        if len(parts) == 2:
            service = _detect_service(parts[0])
            location = parts[1].strip()
            # If service not detected from the service part, use the raw text
            if service == "Unknown":
                service = parts[0].strip()
        else:
            service = _detect_service(full_location)
            location = full_location

    return {
        "item": item,
        "service": service,
        "location": location,
        "date": date_str,
    }


@router.get("/collections")
async def vinted_collections(
    days: int = Query(default=7, ge=1, le=90, description="Look back N days"),
    mark_reported: bool = Query(default=True, description="Mark new items as reported"),
):
    """Get Vinted orders ready to collect from Gmail notifications."""
    from .google_auth import get_gmail_service

    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=503, detail="Gmail not configured")

        # Build search query
        after_date = (datetime.now(UK_TZ) - timedelta(days=days)).strftime("%Y/%m/%d")
        query = f'from:no-reply@vinted.co.uk "waiting for you" after:{after_date}'

        # Search Gmail
        all_messages = []
        page_token = None
        while True:
            results = service.users().messages().list(
                userId='me',
                q=query,
                maxResults=100,
                pageToken=page_token,
            ).execute()
            messages = results.get('messages', [])
            if not messages:
                break
            all_messages.extend(messages)
            page_token = results.get('nextPageToken')
            if not page_token:
                break

        # Load dedup state
        reported = _load_reported()

        # Fetch and parse each email
        collections = []
        for msg in all_messages:
            email_id = msg['id']

            detail = service.users().messages().get(
                userId='me',
                id=email_id,
                format='full',
            ).execute()

            headers = {h['name']: h['value'] for h in detail.get('payload', {}).get('headers', [])}
            subject = headers.get('Subject', '')
            date_str = headers.get('Date', '')

            body = _extract_body(detail.get('payload', {}))
            parsed = _parse_collection(subject, body, date_str)

            is_new = email_id not in reported
            collections.append({
                "email_id": email_id,
                "item": parsed["item"],
                "date": parsed["date"],
                "service": parsed["service"],
                "location": parsed["location"],
                "is_new": is_new,
            })

        # Sort by date (newest first)
        collections.sort(key=lambda x: x["date"], reverse=True)

        new_count = sum(1 for c in collections if c["is_new"])

        # Mark new items as reported
        if mark_reported:
            now_iso = datetime.now(UK_TZ).isoformat()
            for c in collections:
                if c["is_new"]:
                    reported[c["email_id"]] = {
                        "reported_at": now_iso,
                        "item": c["item"],
                        "service": c["service"],
                    }
            _save_reported(reported)

        return {
            "collections": collections,
            "new_count": new_count,
            "total_count": len(collections),
            "query": query,
            "fetched_at": datetime.now(UK_TZ).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
