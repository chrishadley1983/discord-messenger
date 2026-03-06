"""Hadley API - Local API proxy for Peter's real-time queries.

Handles OAuth complexity and exposes simple REST endpoints.
Run with: uvicorn hadley_api.main:app --port 8100
"""

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel
from fastapi.responses import JSONResponse, Response
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional
from pathlib import Path
import asyncio
import json
import os

app = FastAPI(
    title="Hadley API",
    description="Local API proxy for Peter's real-time queries",
    version="1.0.0"
)

# Register sub-routers (load_dotenv before import so env vars are available)
from dotenv import load_dotenv
load_dotenv()
from hadley_api.task_routes import router as task_router
app.include_router(task_router)
from hadley_api.brain_routes import router as brain_graph_router
app.include_router(brain_graph_router)
from hadley_api.vinted_routes import router as vinted_router
app.include_router(vinted_router)
from hadley_api.spotify_routes import router as spotify_router
app.include_router(spotify_router)
from hadley_api.claude_routes import router as claude_router
app.include_router(claude_router)
from hadley_api.vault_routes import router as vault_router
app.include_router(vault_router)
from hadley_api.whatsapp_webhook import router as whatsapp_router
app.include_router(whatsapp_router)

UK_TZ = ZoneInfo("Europe/London")

# Calendars to query for read endpoints (primary + shared)
CALENDAR_IDS = [
    'primary',
    'aehadley86@gmail.com',
    'family04516641497623508871@group.calendar.google.com',
]

CALENDAR_LABELS = {
    'primary': 'Chris',
    'aehadley86@gmail.com': 'Abby',
    'family04516641497623508871@group.calendar.google.com': 'Family',
}


def _fetch_all_calendars(service, **kwargs):
    """Fetch events from all configured calendars and merge results.

    Accepts the same kwargs as service.events().list() except calendarId.
    Returns a flat list of event dicts with an added 'calendar' field.
    """
    all_events = []
    for cal_id in CALENDAR_IDS:
        try:
            result = service.events().list(calendarId=cal_id, **kwargs).execute()
            label = CALENDAR_LABELS.get(cal_id, cal_id)
            for event in result.get('items', []):
                event['_calendar'] = label
                all_events.append(event)
        except Exception:
            # Skip calendars that error (permissions, etc.)
            pass
    return all_events


# ============================================================
# Health Check
# ============================================================

@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "Hadley API",
        "timestamp": datetime.now(UK_TZ).isoformat()
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


# ============================================================
# Gmail Endpoints
# ============================================================


def _build_mime_message(body_text: str, attachment_paths: list[str] | None = None):
    """Build a MIME message, with attachments if provided."""
    import mimetypes
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email import encoders

    if not attachment_paths:
        return MIMEText(body_text)

    msg = MIMEMultipart()
    msg.attach(MIMEText(body_text))

    for file_path in attachment_paths:
        p = Path(file_path)
        if not p.is_file():
            raise FileNotFoundError(f"Attachment not found: {file_path}")

        content_type, _ = mimetypes.guess_type(str(p))
        if content_type is None:
            content_type = "application/octet-stream"
        maintype, subtype = content_type.split("/", 1)

        with open(p, "rb") as f:
            part = MIMEBase(maintype, subtype)
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=p.name)
        msg.attach(part)

    return msg


@app.get("/gmail/unread")
async def gmail_unread(limit: int = Query(default=10, le=20)):
    """Get unread emails."""
    from .google_auth import get_gmail_service

    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=503, detail="Gmail not configured")

        # Get unread messages
        results = service.users().messages().list(
            userId='me',
            q='is:unread',
            maxResults=limit
        ).execute()

        messages = results.get('messages', [])
        unread_count = results.get('resultSizeEstimate', 0)

        emails = []
        for msg in messages[:limit]:
            detail = service.users().messages().get(
                userId='me',
                id=msg['id'],
                format='metadata',
                metadataHeaders=['From', 'Subject', 'Date']
            ).execute()

            headers = {h['name']: h['value'] for h in detail.get('payload', {}).get('headers', [])}
            emails.append({
                "id": msg['id'],
                "from": headers.get('From', 'Unknown'),
                "subject": headers.get('Subject', '(no subject)'),
                "date": headers.get('Date', ''),
                "snippet": detail.get('snippet', '')[:150]
            })

        return {
            "unread_count": unread_count,
            "emails": emails,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gmail/search")
async def gmail_search(
    q: str = Query(..., description="Search query"),
    limit: int = Query(default=10, le=500, description="Max results (up to 500 for seed imports)"),
    account: str = Query(default="personal", description="Account: personal or hadley-bricks"),
):
    """Search emails with pagination support for large result sets."""
    from .google_auth import get_gmail_service

    try:
        service = get_gmail_service(account)
        if not service:
            raise HTTPException(status_code=503, detail="Gmail not configured")

        # Paginate through results for larger limits
        all_messages = []
        page_token = None

        while len(all_messages) < limit:
            results = service.users().messages().list(
                userId='me',
                q=q,
                maxResults=min(100, limit - len(all_messages)),
                pageToken=page_token
            ).execute()

            messages = results.get('messages', [])
            if not messages:
                break

            all_messages.extend(messages)
            page_token = results.get('nextPageToken')
            if not page_token:
                break

        emails = []
        for msg in all_messages[:limit]:
            detail = service.users().messages().get(
                userId='me',
                id=msg['id'],
                format='metadata',
                metadataHeaders=['From', 'Subject', 'Date']
            ).execute()

            headers = {h['name']: h['value'] for h in detail.get('payload', {}).get('headers', [])}
            emails.append({
                "id": msg['id'],
                "from": headers.get('From', 'Unknown'),
                "subject": headers.get('Subject', '(no subject)'),
                "date": headers.get('Date', ''),
                "snippet": detail.get('snippet', '')[:150]
            })

        return {
            "query": q,
            "count": len(emails),
            "emails": emails,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gmail/get")
async def gmail_get(
    id: str = Query(..., description="Email message ID"),
    account: str = Query(default="personal", description="Account: personal or hadley-bricks"),
    html: bool = Query(default=False, description="Include raw HTML body in response"),
):
    """Get full email content by ID."""
    from .google_auth import get_gmail_service
    import base64
    import re
    from html import unescape

    def html_to_text(html_content: str) -> str:
        """Convert HTML to plain text."""
        # Remove script and style elements
        text = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        # Convert <br> and block elements to newlines
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</?(p|div|tr|li|h[1-6])[^>]*>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<td[^>]*>', ' | ', text, flags=re.IGNORECASE)
        # Remove all other HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # Decode HTML entities
        text = unescape(text)
        # Clean up whitespace
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n[ \t]+', '\n', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    try:
        service = get_gmail_service(account)
        if not service:
            raise HTTPException(status_code=503, detail="Gmail not configured")

        # Get full message content
        detail = service.users().messages().get(
            userId='me',
            id=id,
            format='full'
        ).execute()

        headers = {h['name']: h['value'] for h in detail.get('payload', {}).get('headers', [])}

        # Extract body text - try plain text first, then HTML
        plain_text = ""
        html_text = ""
        payload = detail.get('payload', {})

        def extract_content(part):
            """Recursively extract text from message parts."""
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
            elif mime_type.startswith('multipart/'):
                for subpart in part.get('parts', []):
                    extract_content(subpart)
            elif 'parts' in part:
                for subpart in part['parts']:
                    extract_content(subpart)

        extract_content(payload)

        # If no content found in parts, try the body directly
        if not plain_text and not html_text:
            data = payload.get('body', {}).get('data', '')
            if data:
                content = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                mime_type = payload.get('mimeType', '')
                if mime_type == 'text/html':
                    html_text = content
                else:
                    plain_text = content

        # Use plain text if available, otherwise convert HTML
        if plain_text:
            body = plain_text
        elif html_text:
            body = html_to_text(html_text)
        else:
            body = ""

        # Get attachment info with attachment IDs for retrieval
        attachments = []
        def find_attachments(part):
            if part.get('filename'):
                att_info = {
                    "filename": part['filename'],
                    "mimeType": part.get('mimeType', 'unknown'),
                    "size": part.get('body', {}).get('size', 0)
                }
                # Include attachment ID if available
                if part.get('body', {}).get('attachmentId'):
                    att_info["attachmentId"] = part['body']['attachmentId']
                attachments.append(att_info)
            for subpart in part.get('parts', []):
                find_attachments(subpart)

        find_attachments(payload)

        result = {
            "id": id,
            "from": headers.get('From', 'Unknown'),
            "to": headers.get('To', ''),
            "subject": headers.get('Subject', '(no subject)'),
            "date": headers.get('Date', ''),
            "body": body[:10000],  # Limit body to 10k chars
            "attachments": attachments,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

        # Include raw HTML when requested (for structured data extraction)
        if html and html_text:
            result["html"] = html_text[:50000]

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gmail/labels")
async def gmail_labels(
    account: str = Query(default="personal", description="Account: personal or hadley-bricks"),
):
    """Get all Gmail labels."""
    from .google_auth import get_gmail_service

    try:
        service = get_gmail_service(account)
        if not service:
            raise HTTPException(status_code=503, detail="Gmail not configured")

        results = service.users().labels().list(userId='me').execute()
        labels = results.get('labels', [])

        return {
            "labels": [{"id": l['id'], "name": l['name'], "type": l.get('type', 'user')} for l in labels],
            "count": len(labels),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gmail/starred")
async def gmail_starred(limit: int = Query(default=10, le=20)):
    """Get starred emails."""
    from .google_auth import get_gmail_service

    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=503, detail="Gmail not configured")

        results = service.users().messages().list(
            userId='me',
            q='is:starred',
            maxResults=limit
        ).execute()

        messages = results.get('messages', [])
        emails = []

        for msg in messages:
            detail = service.users().messages().get(
                userId='me',
                id=msg['id'],
                format='metadata',
                metadataHeaders=['From', 'Subject', 'Date']
            ).execute()

            headers = {h['name']: h['value'] for h in detail.get('payload', {}).get('headers', [])}
            emails.append({
                "id": msg['id'],
                "from": headers.get('From', 'Unknown'),
                "subject": headers.get('Subject', '(no subject)'),
                "date": headers.get('Date', ''),
                "snippet": detail.get('snippet', '')[:150]
            })

        return {
            "count": len(emails),
            "emails": emails,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gmail/thread")
async def gmail_thread(id: str = Query(..., description="Thread ID")):
    """Get full email thread/conversation."""
    from .google_auth import get_gmail_service
    import base64

    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=503, detail="Gmail not configured")

        thread = service.users().threads().get(
            userId='me',
            id=id,
            format='full'
        ).execute()

        messages = []
        for msg in thread.get('messages', []):
            headers = {h['name']: h['value'] for h in msg.get('payload', {}).get('headers', [])}

            # Extract body
            body = ""
            payload = msg.get('payload', {})

            def extract_text(part):
                text = ""
                if part.get('mimeType') == 'text/plain':
                    data = part.get('body', {}).get('data', '')
                    if data:
                        text = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                for subpart in part.get('parts', []):
                    text += extract_text(subpart)
                return text

            body = extract_text(payload)
            if not body and payload.get('body', {}).get('data'):
                body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')

            messages.append({
                "id": msg['id'],
                "from": headers.get('From', 'Unknown'),
                "to": headers.get('To', ''),
                "date": headers.get('Date', ''),
                "body": body[:5000]
            })

        return {
            "thread_id": id,
            "subject": messages[0].get('subject', thread.get('snippet', '')[:50]) if messages else '',
            "message_count": len(messages),
            "messages": messages,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/gmail/draft")
async def gmail_draft(
    to: str = Query(..., description="Recipient email"),
    subject: str = Query(..., description="Email subject"),
    body: str = Query(..., description="Email body text"),
    attachments: list[str] = Query(default=[], description="Local file paths to attach"),
):
    """Create a draft email, optionally with file attachments."""
    from .google_auth import get_gmail_service
    import base64

    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=503, detail="Gmail not configured")

        message = _build_mime_message(body, attachments)
        message['to'] = to
        message['subject'] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        draft = service.users().drafts().create(
            userId='me',
            body={'message': {'raw': raw}}
        ).execute()

        return {
            "status": "draft_created",
            "draft_id": draft['id'],
            "to": to,
            "subject": subject,
            "attachments": [Path(a).name for a in attachments],
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/gmail/send")
async def gmail_send(
    to: str = Query(..., description="Recipient email"),
    subject: str = Query(..., description="Email subject"),
    body: str = Query(..., description="Email body text"),
    attachments: list[str] = Query(default=[], description="Local file paths to attach"),
):
    """Send an email, optionally with file attachments."""
    from .google_auth import get_gmail_service
    import base64
    from email.mime.text import MIMEText

    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=503, detail="Gmail not configured")

        message = _build_mime_message(body, attachments)
        message['to'] = to
        message['subject'] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        sent = service.users().messages().send(
            userId='me',
            body={'raw': raw}
        ).execute()

        return {
            "status": "sent",
            "message_id": sent['id'],
            "to": to,
            "subject": subject,
            "attachments": [Path(a).name for a in attachments],
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Calendar Endpoints
# ============================================================

@app.get("/calendar/today")
async def calendar_today():
    """Get today's calendar events."""
    from .google_auth import get_calendar_service

    try:
        service = get_calendar_service()
        if not service:
            raise HTTPException(status_code=503, detail="Calendar not configured")

        now = datetime.now(UK_TZ)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        all_items = _fetch_all_calendars(
            service,
            timeMin=start_of_day.isoformat(),
            timeMax=end_of_day.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        )

        events = []
        for event in all_items:
            start = event.get('start', {})
            end = event.get('end', {})

            events.append({
                "id": event.get('id'),
                "title": event.get('summary', '(no title)'),
                "start": start.get('dateTime') or start.get('date'),
                "end": end.get('dateTime') or end.get('date'),
                "location": event.get('location'),
                "all_day": 'date' in start,
                "calendar": event.get('_calendar', 'Chris')
            })

        # Sort merged events by start time
        events.sort(key=lambda e: e['start'] or '')

        return {
            "date": now.strftime("%A %d %B %Y"),
            "event_count": len(events),
            "events": events,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/calendar/week")
async def calendar_week():
    """Get this week's calendar events."""
    from .google_auth import get_calendar_service

    try:
        service = get_calendar_service()
        if not service:
            raise HTTPException(status_code=503, detail="Calendar not configured")

        now = datetime.now(UK_TZ)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)

        all_items = _fetch_all_calendars(
            service,
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        )

        # Group by day
        events_by_day = {}
        for event in all_items:
            event_start = event.get('start', {})
            start_str = event_start.get('dateTime') or event_start.get('date')

            if start_str:
                day_key = start_str.split('T')[0] if 'T' in start_str else start_str

                if day_key not in events_by_day:
                    events_by_day[day_key] = []

                events_by_day[day_key].append({
                    "title": event.get('summary', '(no title)'),
                    "start": start_str,
                    "location": event.get('location'),
                    "calendar": event.get('_calendar', 'Chris')
                })

        # Sort events within each day by start time
        for day_events in events_by_day.values():
            day_events.sort(key=lambda e: e['start'] or '')

        return {
            "start_date": start.strftime("%A %d %B"),
            "end_date": end.strftime("%A %d %B"),
            "total_events": sum(len(v) for v in events_by_day.values()),
            "events_by_day": events_by_day,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/calendar/free")
async def calendar_free(
    date: Optional[str] = Query(default=None, description="Date to check (YYYY-MM-DD)"),
    duration: int = Query(default=60, description="Duration in minutes")
):
    """Find free time slots."""
    from .google_auth import get_calendar_service

    try:
        service = get_calendar_service()
        if not service:
            raise HTTPException(status_code=503, detail="Calendar not configured")

        now = datetime.now(UK_TZ)

        if date:
            check_date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UK_TZ)
        else:
            check_date = now

        start_of_day = check_date.replace(hour=9, minute=0, second=0, microsecond=0)
        end_of_day = check_date.replace(hour=17, minute=30, second=0, microsecond=0)

        all_items = _fetch_all_calendars(
            service,
            timeMin=start_of_day.isoformat(),
            timeMax=end_of_day.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        )

        # Find gaps between events
        busy_times = []
        for event in all_items:
            start = event.get('start', {}).get('dateTime')
            end = event.get('end', {}).get('dateTime')
            if start and end:
                busy_times.append((
                    datetime.fromisoformat(start),
                    datetime.fromisoformat(end)
                ))

        # Sort by start time
        busy_times.sort(key=lambda x: x[0])

        # Find free slots
        free_slots = []
        current = start_of_day

        for busy_start, busy_end in busy_times:
            if current < busy_start:
                gap_minutes = (busy_start - current).total_seconds() / 60
                if gap_minutes >= duration:
                    free_slots.append({
                        "start": current.strftime("%H:%M"),
                        "end": busy_start.strftime("%H:%M"),
                        "duration_minutes": int(gap_minutes)
                    })
            current = max(current, busy_end)

        # Check remaining time
        if current < end_of_day:
            gap_minutes = (end_of_day - current).total_seconds() / 60
            if gap_minutes >= duration:
                free_slots.append({
                    "start": current.strftime("%H:%M"),
                    "end": end_of_day.strftime("%H:%M"),
                    "duration_minutes": int(gap_minutes)
                })

        return {
            "date": check_date.strftime("%A %d %B"),
            "minimum_duration": duration,
            "free_slots": free_slots,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/calendar/range")
async def calendar_range(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    limit: int = Query(default=2500, le=5000, description="Max events to return")
):
    """Get events in a date range (paginated to fetch all)."""
    from .google_auth import get_calendar_service

    try:
        service = get_calendar_service()
        if not service:
            raise HTTPException(status_code=503, detail="Calendar not configured")

        start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=UK_TZ)
        end = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, tzinfo=UK_TZ)

        # Fetch from all calendars
        all_items = _fetch_all_calendars(
            service,
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy='startTime',
            maxResults=min(250, limit)
        )

        events = []
        for event in all_items[:limit]:
            start_time = event.get('start', {}).get('dateTime', event.get('start', {}).get('date', ''))
            end_time = event.get('end', {}).get('dateTime', event.get('end', {}).get('date', ''))
            events.append({
                "id": event['id'],
                "summary": event.get('summary', '(No title)'),
                "start": start_time,
                "end": end_time,
                "location": event.get('location', ''),
                "description": event.get('description', '')[:200] if event.get('description') else '',
                "calendar": event.get('_calendar', 'Chris')
            })

        events.sort(key=lambda e: e['start'] or '')

        return {
            "start_date": start_date,
            "end_date": end_date,
            "count": len(events),
            "events": events,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/calendar/create")
async def calendar_create(
    summary: str = Query(..., description="Event title"),
    start: str = Query(..., description="Start datetime (YYYY-MM-DDTHH:MM or YYYY-MM-DD for all-day)"),
    end: Optional[str] = Query(default=None, description="End datetime (optional, defaults to 1 hour after start)"),
    location: Optional[str] = Query(default=None, description="Event location"),
    description: Optional[str] = Query(default=None, description="Event description"),
    attachments: list[str] = Query(default=[], description="Google Drive file URLs to attach"),
):
    """Create a calendar event, optionally with Drive file attachments."""
    from .google_auth import get_calendar_service

    try:
        service = get_calendar_service()
        if not service:
            raise HTTPException(status_code=503, detail="Calendar not configured")

        # Determine if all-day event
        is_all_day = len(start) == 10  # YYYY-MM-DD format

        if is_all_day:
            event_body = {
                'summary': summary,
                'start': {'date': start},
                'end': {'date': end or start}
            }
        else:
            start_dt = datetime.fromisoformat(start)
            if not start_dt.tzinfo:
                start_dt = start_dt.replace(tzinfo=UK_TZ)

            if end:
                end_dt = datetime.fromisoformat(end)
                if not end_dt.tzinfo:
                    end_dt = end_dt.replace(tzinfo=UK_TZ)
            else:
                end_dt = start_dt + timedelta(hours=1)

            event_body = {
                'summary': summary,
                'start': {'dateTime': start_dt.isoformat()},
                'end': {'dateTime': end_dt.isoformat()}
            }

        if location:
            event_body['location'] = location
        if description:
            event_body['description'] = description
        if attachments:
            event_body['attachments'] = [{'fileUrl': url} for url in attachments]

        event = service.events().insert(
            calendarId='primary',
            body=event_body,
            supportsAttachments=bool(attachments),
        ).execute()

        return {
            "status": "created",
            "event_id": event['id'],
            "summary": summary,
            "start": start,
            "end": end or (start if is_all_day else (start_dt + timedelta(hours=1)).isoformat()),
            "link": event.get('htmlLink', ''),
            "attachments": len(attachments),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/calendar/event")
async def calendar_event(id: str = Query(..., description="Event ID")):
    """Get a specific calendar event."""
    from .google_auth import get_calendar_service

    try:
        service = get_calendar_service()
        if not service:
            raise HTTPException(status_code=503, detail="Calendar not configured")

        event = service.events().get(calendarId='primary', eventId=id).execute()

        return {
            "id": event['id'],
            "summary": event.get('summary', '(No title)'),
            "start": event.get('start', {}).get('dateTime', event.get('start', {}).get('date', '')),
            "end": event.get('end', {}).get('dateTime', event.get('end', {}).get('date', '')),
            "location": event.get('location', ''),
            "description": event.get('description', ''),
            "status": event.get('status', ''),
            "link": event.get('htmlLink', ''),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/calendar/event")
async def calendar_delete(id: str = Query(..., description="Event ID")):
    """Delete a calendar event."""
    from .google_auth import get_calendar_service

    try:
        service = get_calendar_service()
        if not service:
            raise HTTPException(status_code=503, detail="Calendar not configured")

        service.events().delete(calendarId='primary', eventId=id).execute()

        return {
            "status": "deleted",
            "event_id": id,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/calendar/event")
async def calendar_update(
    id: str = Query(..., description="Event ID"),
    summary: Optional[str] = Query(default=None, description="New event title"),
    start: Optional[str] = Query(default=None, description="New start datetime"),
    end: Optional[str] = Query(default=None, description="New end datetime"),
    location: Optional[str] = Query(default=None, description="New location"),
    description: Optional[str] = Query(default=None, description="New description"),
    attachments: list[str] = Query(default=[], description="Google Drive file URLs to attach (appended to existing)"),
):
    """Update a calendar event, optionally adding Drive file attachments."""
    from .google_auth import get_calendar_service

    try:
        service = get_calendar_service()
        if not service:
            raise HTTPException(status_code=503, detail="Calendar not configured")

        # Get existing event
        event = service.events().get(calendarId='primary', eventId=id).execute()

        # Update fields if provided
        if summary:
            event['summary'] = summary
        if location:
            event['location'] = location
        if description:
            event['description'] = description

        if start:
            is_all_day = len(start) == 10
            if is_all_day:
                event['start'] = {'date': start}
            else:
                start_dt = datetime.fromisoformat(start)
                if not start_dt.tzinfo:
                    start_dt = start_dt.replace(tzinfo=UK_TZ)
                event['start'] = {'dateTime': start_dt.isoformat()}

        if end:
            is_all_day = len(end) == 10
            if is_all_day:
                event['end'] = {'date': end}
            else:
                end_dt = datetime.fromisoformat(end)
                if not end_dt.tzinfo:
                    end_dt = end_dt.replace(tzinfo=UK_TZ)
                event['end'] = {'dateTime': end_dt.isoformat()}

        if attachments:
            existing = event.get('attachments', [])
            existing.extend({'fileUrl': url} for url in attachments)
            event['attachments'] = existing

        updated = service.events().update(
            calendarId='primary',
            eventId=id,
            body=event,
            supportsAttachments=bool(attachments),
        ).execute()

        return {
            "status": "updated",
            "event_id": id,
            "summary": updated.get('summary', ''),
            "start": updated.get('start', {}).get('dateTime', updated.get('start', {}).get('date', '')),
            "end": updated.get('end', {}).get('dateTime', updated.get('end', {}).get('date', '')),
            "attachments": len(updated.get('attachments', [])),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Drive Endpoints
# ============================================================

@app.get("/drive/search")
async def drive_search(
    q: str = Query(..., description="Search query"),
    limit: int = Query(default=10, le=20)
):
    """Search Google Drive."""
    from .google_auth import get_drive_service

    try:
        service = get_drive_service()
        if not service:
            raise HTTPException(status_code=503, detail="Drive not configured")

        # Search files
        results = service.files().list(
            q=f"name contains '{q}' or fullText contains '{q}'",
            pageSize=limit,
            fields="files(id, name, mimeType, modifiedTime, webViewLink, parents)"
        ).execute()

        files = []
        for f in results.get('files', []):
            mime = f.get('mimeType', '')
            file_type = 'other'
            if 'document' in mime:
                file_type = 'doc'
            elif 'spreadsheet' in mime:
                file_type = 'sheet'
            elif 'presentation' in mime:
                file_type = 'slides'
            elif 'pdf' in mime:
                file_type = 'pdf'
            elif 'folder' in mime:
                file_type = 'folder'

            files.append({
                "id": f.get('id'),
                "name": f.get('name'),
                "type": file_type,
                "modified": f.get('modifiedTime'),
                "url": f.get('webViewLink')
            })

        return {
            "query": q,
            "count": len(files),
            "files": files,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Notion Endpoints
# ============================================================

@app.get("/notion/todos")
async def notion_todos():
    """Get Notion todos."""
    from .notion_client import get_todos

    try:
        result = await get_todos()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/notion/ideas")
async def notion_ideas():
    """Get Notion ideas."""
    from .notion_client import get_ideas

    try:
        result = await get_ideas()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




# ============================================================
# Weather Endpoints (Open-Meteo - Free)
# ============================================================

WEATHER_CODES = {
    0: ("Clear sky", "☀️"), 1: ("Mainly clear", "🌤️"), 2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁️"), 45: ("Foggy", "🌫️"), 48: ("Rime fog", "🌫️"),
    51: ("Light drizzle", "🌦️"), 53: ("Drizzle", "🌦️"), 55: ("Dense drizzle", "🌧️"),
    61: ("Slight rain", "🌧️"), 63: ("Rain", "🌧️"), 65: ("Heavy rain", "🌧️"),
    71: ("Slight snow", "❄️"), 73: ("Snow", "❄️"), 75: ("Heavy snow", "❄️"),
    80: ("Showers", "🌦️"), 81: ("Moderate showers", "🌧️"), 82: ("Heavy showers", "🌧️"),
    95: ("Thunderstorm", "⛈️"), 96: ("Thunderstorm + hail", "⛈️"), 99: ("Heavy thunderstorm", "⛈️"),
}


@app.get("/weather/current")
async def weather_current():
    """Get current weather for Tonbridge."""
    import httpx
    from dotenv import load_dotenv
    load_dotenv()

    lat = float(os.getenv("WEATHER_LAT", "51.1952"))
    lon = float(os.getenv("WEATHER_LON", "0.2739"))
    location = os.getenv("WEATHER_LOCATION_NAME", "Tonbridge")

    try:
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
            "timezone": "Europe/London"
        }

        async with httpx.AsyncClient() as client:
            response = await client.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=10)
            data = response.json()

        current = data.get("current", {})
        weather_code = current.get("weather_code", 0)
        condition, icon = WEATHER_CODES.get(weather_code, ("Unknown", "❓"))

        return {
            "location": location,
            "temperature": current.get("temperature_2m"),
            "feels_like": current.get("apparent_temperature"),
            "humidity": current.get("relative_humidity_2m"),
            "precipitation": current.get("precipitation"),
            "wind_speed": current.get("wind_speed_10m"),
            "condition": condition,
            "icon": icon,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/weather/forecast")
async def weather_forecast(days: int = Query(default=7, le=14)):
    """Get weather forecast."""
    import httpx
    from dotenv import load_dotenv
    load_dotenv()

    lat = float(os.getenv("WEATHER_LAT", "51.1952"))
    lon = float(os.getenv("WEATHER_LON", "0.2739"))
    location = os.getenv("WEATHER_LOCATION_NAME", "Tonbridge")

    try:
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset",
            "timezone": "Europe/London",
            "forecast_days": days
        }

        async with httpx.AsyncClient() as client:
            response = await client.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=10)
            data = response.json()

        daily = data.get("daily", {})
        forecast = []

        for i in range(len(daily.get("time", []))):
            weather_code = daily["weather_code"][i]
            condition, icon = WEATHER_CODES.get(weather_code, ("Unknown", "❓"))

            forecast.append({
                "date": daily["time"][i],
                "temp_max": daily["temperature_2m_max"][i],
                "temp_min": daily["temperature_2m_min"][i],
                "precipitation_prob": daily["precipitation_probability_max"][i],
                "condition": condition,
                "icon": icon
            })

        return {
            "location": location,
            "forecast": forecast,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Traffic/Directions Endpoints (Google Maps Routes API)
# ============================================================

@app.get("/traffic/school")
async def traffic_school():
    """Get traffic to school using Google Maps Directions API."""
    import httpx
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    origin = os.getenv("HOME_ADDRESS", "47 Correnden Road, TN10 3AU")
    destination = os.getenv("SCHOOL_ADDRESS", "Stocks Green Primary School, Tonbridge")

    if not api_key:
        raise HTTPException(status_code=503, detail="Google Maps API not configured")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/directions/json",
                params={
                    "origin": origin,
                    "destination": destination,
                    "departure_time": "now",
                    "traffic_model": "best_guess",
                    "key": api_key
                },
                timeout=30
            )
            data = response.json()

        if data.get("status") != "OK" or not data.get("routes"):
            return {"error": f"No route found: {data.get('status')}", "origin": origin, "destination": destination}

        route = data["routes"][0]
        leg = route["legs"][0]

        # Get duration with traffic if available
        if "duration_in_traffic" in leg:
            duration_mins = round(leg["duration_in_traffic"]["value"] / 60)
        else:
            duration_mins = round(leg["duration"]["value"] / 60)

        typical_mins = round(leg["duration"]["value"] / 60)
        delay = duration_mins - typical_mins
        distance_km = round(leg["distance"]["value"] / 1000, 1)

        if delay <= 0:
            traffic_level, traffic_icon = "light", "🟢"
        elif delay <= 5:
            traffic_level, traffic_icon = "moderate", "🟡"
        elif delay <= 15:
            traffic_level, traffic_icon = "heavy", "🔴"
        else:
            traffic_level, traffic_icon = "severe", "⚠️"

        return {
            "route": "school",
            "origin": origin,
            "destination": destination,
            "duration_mins": duration_mins,
            "typical_mins": typical_mins,
            "delay_mins": max(0, delay),
            "distance_km": distance_km,
            "traffic_level": traffic_level,
            "traffic_icon": traffic_icon,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/directions")
async def get_directions(
    destination: str = Query(..., description="Destination address"),
    origin: Optional[str] = Query(default=None, description="Origin (default: home)"),
    mode: str = Query(default="driving", description="Travel mode: driving, walking, bicycling, transit")
):
    """Get directions to a destination using Google Maps Directions API."""
    import httpx
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not origin:
        origin = os.getenv("HOME_ADDRESS", "47 Correnden Road, TN10 3AU")

    if not api_key:
        raise HTTPException(status_code=503, detail="Google Maps API not configured")

    try:
        params = {
            "origin": origin,
            "destination": destination,
            "mode": mode.lower(),
            "key": api_key
        }

        if mode.lower() == "driving":
            params["departure_time"] = "now"
            params["traffic_model"] = "best_guess"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/directions/json",
                params=params,
                timeout=30
            )
            data = response.json()

        if data.get("status") != "OK" or not data.get("routes"):
            return {"error": f"No route found to {destination}: {data.get('status')}"}

        route = data["routes"][0]
        leg = route["legs"][0]

        if "duration_in_traffic" in leg:
            duration_mins = round(leg["duration_in_traffic"]["value"] / 60)
        else:
            duration_mins = round(leg["duration"]["value"] / 60)

        distance_km = round(leg["distance"]["value"] / 1000, 1)

        return {
            "origin": origin,
            "destination": destination,
            "mode": mode,
            "duration_mins": duration_mins,
            "distance_km": distance_km,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/places/search")
async def places_search(
    query: str = Query(..., description="Search query (e.g., 'pizza near Caterham')"),
    location: Optional[str] = Query(default=None, description="Location to search near (default: home)")
):
    """Search for places using Google Places API."""
    import httpx
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Google Maps API not configured")

    if not location:
        location = os.getenv("HOME_ADDRESS", "47 Correnden Road, TN10 3AU")

    try:
        # First, geocode the location to get lat/lng
        async with httpx.AsyncClient() as client:
            geo_response = await client.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={"address": location, "key": api_key},
                timeout=30
            )
            geo_data = geo_response.json()

        lat_lng = None
        if geo_data.get("status") == "OK" and geo_data.get("results"):
            loc = geo_data["results"][0]["geometry"]["location"]
            lat_lng = f"{loc['lat']},{loc['lng']}"

        # Search for places
        params = {
            "query": query,
            "key": api_key
        }
        if lat_lng:
            params["location"] = lat_lng
            params["radius"] = 10000  # 10km

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/place/textsearch/json",
                params=params,
                timeout=30
            )
            data = response.json()

        if data.get("status") != "OK":
            return {"error": f"Search failed: {data.get('status')}"}

        places = []
        for place in data.get("results", [])[:10]:
            places.append({
                "place_id": place.get("place_id"),
                "name": place.get("name"),
                "address": place.get("formatted_address", ""),
                "rating": place.get("rating"),
                "user_ratings_total": place.get("user_ratings_total"),
                "open_now": place.get("opening_hours", {}).get("open_now"),
                "types": place.get("types", [])[:3]
            })

        return {
            "query": query,
            "location": location,
            "count": len(places),
            "places": places,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/places/details")
async def places_details(
    place_id: str = Query(..., description="Google Place ID")
):
    """Get detailed info about a place (hours, phone, reviews)."""
    import httpx
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Google Maps API not configured")

    try:
        params = {
            "place_id": place_id,
            "fields": "name,formatted_address,formatted_phone_number,opening_hours,rating,reviews,website,url,price_level",
            "key": api_key
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/place/details/json",
                params=params,
                timeout=30
            )
            data = response.json()

        if data.get("status") != "OK":
            return {"error": f"Details failed: {data.get('status')}"}

        result = data.get("result", {})
        hours = result.get("opening_hours", {})

        # Extract recent reviews
        reviews = []
        for review in result.get("reviews", [])[:3]:
            reviews.append({
                "author": review.get("author_name"),
                "rating": review.get("rating"),
                "text": review.get("text", "")[:200],
                "time": review.get("relative_time_description")
            })

        return {
            "place_id": place_id,
            "name": result.get("name"),
            "address": result.get("formatted_address"),
            "phone": result.get("formatted_phone_number"),
            "website": result.get("website"),
            "maps_url": result.get("url"),
            "rating": result.get("rating"),
            "price_level": result.get("price_level"),
            "open_now": hours.get("open_now"),
            "hours": hours.get("weekday_text", []),
            "reviews": reviews,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/places/nearby")
async def places_nearby(
    location: Optional[str] = Query(default=None, description="Location to search near"),
    type: str = Query(default="restaurant", description="Place type: restaurant, cafe, supermarket, gas_station, etc"),
    radius: int = Query(default=5000, description="Search radius in meters (max 50000)")
):
    """Find places near a location by type."""
    import httpx
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Google Maps API not configured")

    if not location:
        location = os.getenv("HOME_ADDRESS", "47 Correnden Road, TN10 3AU")

    try:
        # Geocode the location
        async with httpx.AsyncClient() as client:
            geo_response = await client.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={"address": location, "key": api_key},
                timeout=30
            )
            geo_data = geo_response.json()

        if geo_data.get("status") != "OK" or not geo_data.get("results"):
            return {"error": f"Could not geocode location: {location}"}

        loc = geo_data["results"][0]["geometry"]["location"]

        # Nearby search
        params = {
            "location": f"{loc['lat']},{loc['lng']}",
            "radius": min(radius, 50000),
            "type": type,
            "key": api_key
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
                params=params,
                timeout=30
            )
            data = response.json()

        if data.get("status") != "OK":
            return {"error": f"Search failed: {data.get('status')}"}

        places = []
        for place in data.get("results", [])[:10]:
            places.append({
                "place_id": place.get("place_id"),
                "name": place.get("name"),
                "address": place.get("vicinity", ""),
                "rating": place.get("rating"),
                "open_now": place.get("opening_hours", {}).get("open_now"),
                "types": place.get("types", [])[:3]
            })

        return {
            "location": location,
            "type": type,
            "radius_m": radius,
            "count": len(places),
            "places": places,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/directions/matrix")
async def directions_matrix(
    destinations: str = Query(..., description="Comma-separated destinations"),
    origin: Optional[str] = Query(default=None, description="Origin (default: home)")
):
    """Get travel times to multiple destinations."""
    import httpx
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Google Maps API not configured")

    if not origin:
        origin = os.getenv("HOME_ADDRESS", "47 Correnden Road, TN10 3AU")

    try:
        params = {
            "origins": origin,
            "destinations": destinations,
            "mode": "driving",
            "departure_time": "now",
            "key": api_key
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/distancematrix/json",
                params=params,
                timeout=30
            )
            data = response.json()

        if data.get("status") != "OK":
            return {"error": f"Matrix failed: {data.get('status')}"}

        dest_list = [d.strip() for d in destinations.split(",")]
        results = []

        for i, element in enumerate(data.get("rows", [{}])[0].get("elements", [])):
            if element.get("status") == "OK":
                duration_mins = round(element.get("duration_in_traffic", element.get("duration", {})).get("value", 0) / 60)
                distance_km = round(element.get("distance", {}).get("value", 0) / 1000, 1)
                results.append({
                    "destination": dest_list[i] if i < len(dest_list) else f"Destination {i+1}",
                    "duration_mins": duration_mins,
                    "distance_km": distance_km
                })
            else:
                results.append({
                    "destination": dest_list[i] if i < len(dest_list) else f"Destination {i+1}",
                    "error": element.get("status")
                })

        return {
            "origin": origin,
            "results": results,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# EV Charging Endpoint (Ohme)
# ============================================================

_ohme_client = None


@app.get("/ev/status")
async def ev_charging_status():
    """Get EV charging status from Ohme using ohmepy library."""
    from ohme import OhmeApiClient
    from dotenv import load_dotenv
    load_dotenv()

    global _ohme_client

    email = os.getenv("OHME_EMAIL")
    password = os.getenv("OHME_PASSWORD")

    if not email or not password:
        raise HTTPException(status_code=503, detail="Ohme not configured")

    try:
        # Create client if needed
        if _ohme_client is None:
            _ohme_client = OhmeApiClient(email=email, password=password)
            await _ohme_client.async_login()
            await _ohme_client.async_update_device_info()

        # Fetch latest charge session
        await _ohme_client.async_get_charge_session()

        # Determine status string
        status = _ohme_client.status.value if _ohme_client.status else "unknown"
        mode = _ohme_client.mode.value if _ohme_client.mode else None

        # Check battery data source - Ohme extrapolates if no car API connection
        battery_soc = _ohme_client._charge_session.get("batterySoc", {})
        battery_source = battery_soc.get("source", "unknown")
        battery_level = _ohme_client.battery

        # If extrapolated, the % is just energy added this session, not actual SOC
        # Mark as unreliable
        battery_reliable = battery_source not in ("EXTRAPOLATION", "DEFAULT")

        return {
            "status": status,
            "mode": mode,
            "battery_level": battery_level if battery_reliable else None,
            "battery_level_estimated": battery_level if not battery_reliable else None,
            "battery_source": battery_source,
            "battery_note": "Estimated from session energy (no car API)" if not battery_reliable else None,
            "target_level": _ohme_client.target_soc,
            "charge_rate_kw": round(_ohme_client.power.watts / 1000, 2) if _ohme_client.power.watts else 0,
            "plugged_in": status != "unplugged",
            "energy_added_wh": _ohme_client.energy,
            "available": _ohme_client.available,
            "charger_model": _ohme_client.device_info.get("model", "Unknown"),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except Exception as e:
        # Reset client on error
        _ohme_client = None
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Ring Doorbell Endpoint
# ============================================================

_ring_client = None
RING_TOKEN_FILE = Path(__file__).parent.parent / "ring_token.json"


@app.get("/ring/status")
async def ring_doorbell_status():
    """Get Ring doorbell status and recent activity."""
    import json
    from ring_doorbell import Auth, Ring

    global _ring_client

    if not RING_TOKEN_FILE.exists():
        raise HTTPException(
            status_code=503,
            detail="Ring not authenticated. Run setup_ring_auth.py first."
        )

    try:
        # Load token
        token_data = json.loads(RING_TOKEN_FILE.read_text())

        def token_updated(token: dict):
            RING_TOKEN_FILE.write_text(json.dumps(token, indent=2))

        if _ring_client is None:
            auth = Auth("HadleyAPI/1.0", token_data, token_updated)
            _ring_client = Ring(auth)
            await _ring_client.async_update_data()

        devices = _ring_client.devices()
        doorbells = devices.doorbells

        if not doorbells:
            return {
                "status": "no_doorbells",
                "message": "No Ring doorbells found",
                "fetched_at": datetime.now(UK_TZ).isoformat()
            }

        # Get first doorbell
        doorbell = doorbells[0]

        # Get recent events
        await doorbell.async_history(limit=5)
        recent_events = []
        for event in doorbell.last_history[:5]:
            recent_events.append({
                "type": event.get("kind", "unknown"),
                "answered": event.get("answered", False),
                "time": event.get("created_at", "unknown")
            })

        return {
            "status": doorbell.connection_status or "unknown",
            "name": doorbell.name,
            "battery_level": doorbell.battery_life,
            "wifi_signal": doorbell.wifi_signal_strength,
            "wifi_signal_category": doorbell.wifi_signal_category,
            "firmware": doorbell.firmware,
            "model": doorbell.model,
            "recent_events": recent_events,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except Exception as e:
        _ring_client = None
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Kia Connect Endpoint (Direct car data)
# ============================================================

_kia_manager = None
KIA_TOKEN_FILE = Path(__file__).parent.parent / "kia_token.json"


@app.get("/kia/status")
async def kia_vehicle_status():
    """Get vehicle status directly from Kia Connect API.

    This provides actual battery SOC, range, charging status, etc.
    from the car itself (not extrapolated by Ohme).
    """
    import json
    from hyundai_kia_connect_api import VehicleManager
    from dotenv import load_dotenv
    load_dotenv()

    global _kia_manager

    # Get credentials from env
    email = os.getenv("KIA_EMAIL")
    password = os.getenv("KIA_PASSWORD")
    pin = os.getenv("KIA_PIN", "")

    if not email or not password:
        raise HTTPException(
            status_code=503,
            detail="Kia not configured. Add KIA_EMAIL and KIA_PASSWORD to .env"
        )

    try:
        # Create manager if needed (Region 1 = Europe, Brand 1 = Kia)
        if _kia_manager is None:
            _kia_manager = VehicleManager(
                region=1,
                brand=1,
                username=email,
                password=password,
                pin=pin
            )

        # Refresh token and get latest data
        await _kia_manager.check_and_refresh_token()
        await _kia_manager.update_all_vehicles_with_cached_state()

        if not _kia_manager.vehicles:
            return {
                "status": "no_vehicles",
                "message": "No vehicles found in Kia account",
                "fetched_at": datetime.now(UK_TZ).isoformat()
            }

        # Get first vehicle
        vehicle = list(_kia_manager.vehicles.values())[0]

        return {
            "name": vehicle.name,
            "model": vehicle.model,
            "battery_level": vehicle.ev_battery_percentage,
            "battery_soc_12v": vehicle.car_battery_percentage,
            "range_km": vehicle.ev_driving_range,
            "charging_status": vehicle.ev_battery_is_charging,
            "plugged_in": vehicle.ev_battery_is_plugged_in,
            "charge_target": vehicle.ev_charge_limits_ac,
            "estimated_charge_time": vehicle.ev_estimated_current_charge_duration,
            "odometer_km": vehicle.odometer,
            "location": {
                "latitude": vehicle.location_latitude,
                "longitude": vehicle.location_longitude
            } if vehicle.location_latitude else None,
            "locked": vehicle.is_locked,
            "last_updated": vehicle.last_updated_at.isoformat() if vehicle.last_updated_at else None,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except Exception as e:
        _kia_manager = None
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ev/combined")
async def ev_combined_status():
    """Combined EV status from both Kia Connect and Ohme.

    Kia provides: actual battery %, range, charging status
    Ohme provides: charge rate, energy added, smart charge scheduling
    """
    kia_data = None
    ohme_data = None

    # Try to get Kia data
    try:
        kia_response = await kia_vehicle_status()
        kia_data = kia_response
    except Exception:
        pass

    # Try to get Ohme data
    try:
        ohme_response = await ev_charging_status()
        ohme_data = ohme_response
    except Exception:
        pass

    if not kia_data and not ohme_data:
        raise HTTPException(status_code=503, detail="Neither Kia nor Ohme available")

    return {
        "battery_level": kia_data.get("battery_level") if kia_data else None,
        "battery_source": "kia_connect" if kia_data and kia_data.get("battery_level") else "ohme_estimated",
        "range_km": kia_data.get("range_km") if kia_data else None,
        "charging": kia_data.get("charging_status") if kia_data else (ohme_data.get("charge_rate_kw", 0) > 0 if ohme_data else None),
        "plugged_in": kia_data.get("plugged_in") if kia_data else (ohme_data.get("plugged_in") if ohme_data else None),
        "charge_rate_kw": ohme_data.get("charge_rate_kw") if ohme_data else None,
        "charge_mode": ohme_data.get("mode") if ohme_data else None,
        "energy_added_wh": ohme_data.get("energy_added_wh") if ohme_data else None,
        "charger_available": ohme_data.get("available") if ohme_data else None,
        "kia_last_updated": kia_data.get("last_updated") if kia_data else None,
        "fetched_at": datetime.now(UK_TZ).isoformat()
    }


# ============================================================
# Geocoding, Timezone, Elevation Endpoints
# ============================================================

@app.get("/geocode")
async def geocode(
    address: Optional[str] = Query(default=None, description="Address to geocode"),
    latlng: Optional[str] = Query(default=None, description="Lat,lng to reverse geocode")
):
    """Convert address to coordinates or coordinates to address."""
    import httpx
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Google Maps API not configured")

    if not address and not latlng:
        raise HTTPException(status_code=400, detail="Provide either 'address' or 'latlng' parameter")

    try:
        params = {"key": api_key}
        if address:
            params["address"] = address
        else:
            params["latlng"] = latlng

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params=params,
                timeout=30
            )
            data = response.json()

        if data.get("status") != "OK" or not data.get("results"):
            return {"error": f"Geocoding failed: {data.get('status')}"}

        result = data["results"][0]
        location = result["geometry"]["location"]

        # Extract address components
        components = {}
        for comp in result.get("address_components", []):
            for type_ in comp.get("types", []):
                components[type_] = comp.get("long_name")

        return {
            "formatted_address": result.get("formatted_address"),
            "latitude": location["lat"],
            "longitude": location["lng"],
            "postcode": components.get("postal_code"),
            "city": components.get("postal_town") or components.get("locality"),
            "country": components.get("country"),
            "place_id": result.get("place_id"),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/timezone")
async def timezone(
    location: str = Query(..., description="Location name or lat,lng coordinates")
):
    """Get timezone information for a location."""
    import httpx
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Google Maps API not configured")

    try:
        # Check if location is already lat,lng
        if ',' in location and all(part.replace('.', '').replace('-', '').isdigit() for part in location.split(',')):
            lat_lng = location
        else:
            # Geocode the location first
            async with httpx.AsyncClient() as client:
                geo_response = await client.get(
                    "https://maps.googleapis.com/maps/api/geocode/json",
                    params={"address": location, "key": api_key},
                    timeout=30
                )
                geo_data = geo_response.json()

            if geo_data.get("status") != "OK" or not geo_data.get("results"):
                return {"error": f"Could not find location: {location}"}

            loc = geo_data["results"][0]["geometry"]["location"]
            lat_lng = f"{loc['lat']},{loc['lng']}"

        # Get timezone
        import time
        timestamp = int(time.time())

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/timezone/json",
                params={
                    "location": lat_lng,
                    "timestamp": timestamp,
                    "key": api_key
                },
                timeout=30
            )
            data = response.json()

        if data.get("status") != "OK":
            return {"error": f"Timezone lookup failed: {data.get('status')}"}

        # Calculate local time
        utc_offset = data.get("rawOffset", 0) + data.get("dstOffset", 0)
        local_time = datetime.utcnow() + timedelta(seconds=utc_offset)

        return {
            "location": location,
            "timezone_id": data.get("timeZoneId"),
            "timezone_name": data.get("timeZoneName"),
            "utc_offset_hours": utc_offset / 3600,
            "local_time": local_time.strftime("%H:%M"),
            "local_datetime": local_time.strftime("%Y-%m-%d %H:%M:%S"),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/elevation")
async def elevation(
    location: str = Query(..., description="Location name or lat,lng coordinates")
):
    """Get elevation for a location."""
    import httpx
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Google Maps API not configured")

    try:
        # Check if location is already lat,lng
        if ',' in location and all(part.replace('.', '').replace('-', '').isdigit() for part in location.split(',')):
            lat_lng = location
            location_name = location
        else:
            # Geocode the location first
            async with httpx.AsyncClient() as client:
                geo_response = await client.get(
                    "https://maps.googleapis.com/maps/api/geocode/json",
                    params={"address": location, "key": api_key},
                    timeout=30
                )
                geo_data = geo_response.json()

            if geo_data.get("status") != "OK" or not geo_data.get("results"):
                return {"error": f"Could not find location: {location}"}

            loc = geo_data["results"][0]["geometry"]["location"]
            lat_lng = f"{loc['lat']},{loc['lng']}"
            location_name = geo_data["results"][0].get("formatted_address", location)

        # Get elevation
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/elevation/json",
                params={
                    "locations": lat_lng,
                    "key": api_key
                },
                timeout=30
            )
            data = response.json()

        if data.get("status") != "OK" or not data.get("results"):
            return {"error": f"Elevation lookup failed: {data.get('status')}"}

        result = data["results"][0]
        elevation_m = result.get("elevation", 0)

        return {
            "location": location_name,
            "elevation_meters": round(elevation_m, 1),
            "elevation_feet": round(elevation_m * 3.28084, 1),
            "resolution_meters": round(result.get("resolution", 0), 1),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Gmail Attachments Endpoint
# ============================================================

@app.get("/gmail/attachments")
async def gmail_attachments(
    message_id: str = Query(..., description="Email message ID"),
    attachment_id: Optional[str] = Query(default=None, description="Specific attachment ID to download")
):
    """List or download email attachments."""
    from .google_auth import get_gmail_service
    import base64

    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=503, detail="Gmail not configured")

        # Get the message
        message = service.users().messages().get(
            userId='me',
            id=message_id,
            format='full'
        ).execute()

        # Find attachments
        attachments = []
        payload = message.get('payload', {})

        def find_attachments(part, path=""):
            if part.get('filename') and part.get('body', {}).get('attachmentId'):
                attachments.append({
                    "id": part['body']['attachmentId'],
                    "filename": part['filename'],
                    "mimeType": part.get('mimeType', 'application/octet-stream'),
                    "size": part.get('body', {}).get('size', 0)
                })
            for i, subpart in enumerate(part.get('parts', [])):
                find_attachments(subpart, f"{path}/{i}")

        find_attachments(payload)

        # If specific attachment requested, download it
        if attachment_id:
            attachment = service.users().messages().attachments().get(
                userId='me',
                messageId=message_id,
                id=attachment_id
            ).execute()

            # Find filename for this attachment
            filename = "attachment"
            for att in attachments:
                if att['id'] == attachment_id:
                    filename = att['filename']
                    break

            data = attachment.get('data', '')
            # Return base64 encoded data
            return {
                "message_id": message_id,
                "attachment_id": attachment_id,
                "filename": filename,
                "size": attachment.get('size', 0),
                "data_base64": data,
                "fetched_at": datetime.now(UK_TZ).isoformat()
            }

        return {
            "message_id": message_id,
            "attachment_count": len(attachments),
            "attachments": attachments,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gmail/attachment/text")
async def gmail_attachment_text(
    message_id: str = Query(..., description="Email message ID"),
    attachment_id: str = Query(..., description="Attachment ID to extract text from")
):
    """Extract text from PDF or text attachments."""
    from .google_auth import get_gmail_service
    import base64
    import io

    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=503, detail="Gmail not configured")

        # Get the attachment
        attachment = service.users().messages().attachments().get(
            userId='me',
            messageId=message_id,
            id=attachment_id
        ).execute()

        data = attachment.get('data', '')
        if not data:
            return {"error": "No attachment data", "text": ""}

        # Decode base64 data
        file_data = base64.urlsafe_b64decode(data)

        # Get message to find filename and mimetype
        message = service.users().messages().get(
            userId='me',
            id=message_id,
            format='full'
        ).execute()

        # Find attachment info
        filename = "attachment"
        mimetype = "application/octet-stream"
        payload = message.get('payload', {})

        def find_attachment_info(part):
            nonlocal filename, mimetype
            if part.get('body', {}).get('attachmentId') == attachment_id:
                filename = part.get('filename', 'attachment')
                mimetype = part.get('mimeType', 'application/octet-stream')
                return True
            for subpart in part.get('parts', []):
                if find_attachment_info(subpart):
                    return True
            return False

        find_attachment_info(payload)

        # If we didn't find the attachment info, check based on the data itself
        # PDF files start with %PDF
        if filename == "attachment" and file_data[:4] == b'%PDF':
            filename = "document.pdf"
            mimetype = "application/pdf"

        extracted_text = ""

        # Extract text based on file type
        if mimetype == 'application/pdf' or filename.lower().endswith('.pdf') or file_data[:4] == b'%PDF':
            try:
                import pypdf
                pdf_reader = pypdf.PdfReader(io.BytesIO(file_data))
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        extracted_text += page_text + "\n\n"
            except ImportError:
                # Fallback: try PyPDF2
                try:
                    import PyPDF2
                    pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_data))
                    for page in pdf_reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            extracted_text += page_text + "\n\n"
                except ImportError:
                    return {"error": "PDF library not installed. Install with: pip install pypdf", "text": ""}
        elif mimetype.startswith('text/') or filename.lower().endswith(('.txt', '.csv', '.ics', '.html')):
            # Text-based file
            try:
                extracted_text = file_data.decode('utf-8', errors='ignore')
            except Exception:
                extracted_text = file_data.decode('latin-1', errors='ignore')
        else:
            return {"error": f"Unsupported file type: {mimetype}", "text": "", "filename": filename}

        return {
            "message_id": message_id,
            "attachment_id": attachment_id,
            "filename": filename,
            "mimetype": mimetype,
            "text": extracted_text[:20000],  # Limit to 20k chars
            "truncated": len(extracted_text) > 20000,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Calendar Recurring & Invites Endpoints
# ============================================================

@app.post("/calendar/recurring")
async def calendar_recurring(
    summary: str = Query(..., description="Event title"),
    start_time: str = Query(..., description="Start time (HH:MM)"),
    days: str = Query(..., description="Days: MO,TU,WE,TH,FR,SA,SU"),
    duration_mins: int = Query(default=60, description="Duration in minutes"),
    start_date: Optional[str] = Query(default=None, description="Start date (YYYY-MM-DD, default: today)"),
    end_date: Optional[str] = Query(default=None, description="End date (YYYY-MM-DD, optional)"),
    location: Optional[str] = Query(default=None, description="Event location"),
    color_id: Optional[int] = Query(default=None, description="Google Calendar color (1=lavender,2=sage,3=grape,4=flamingo,5=banana,6=tangerine,7=peacock,8=graphite,9=blueberry,10=basil,11=tomato)"),
    transparency: Optional[str] = Query(default=None, description="'transparent' (show as free) or 'opaque' (show as busy)"),
    exclude_dates: Optional[str] = Query(default=None, description="Comma-separated dates (YYYY-MM-DD) to exclude (e.g. school holidays)")
):
    """Create a recurring calendar event with optional color, free/busy, and exclusions."""
    from .google_auth import get_calendar_service

    try:
        service = get_calendar_service()
        if not service:
            raise HTTPException(status_code=503, detail="Calendar not configured")

        # Parse start date
        if start_date:
            base_date = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=UK_TZ)
        else:
            base_date = datetime.now(UK_TZ)

        # Parse time
        hour, minute = map(int, start_time.split(':'))
        start_dt = base_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        end_dt = start_dt + timedelta(minutes=duration_mins)

        # Build recurrence rules
        rrule = f"RRULE:FREQ=WEEKLY;BYDAY={days.upper()}"
        if end_date:
            rrule += f";UNTIL={end_date.replace('-', '')}T235959Z"

        recurrence = [rrule]

        # Add EXDATE for excluded dates (e.g. school holidays)
        if exclude_dates:
            for date_str in exclude_dates.split(','):
                date_str = date_str.strip()
                if date_str:
                    recurrence.append(f"EXDATE;TZID=Europe/London:{date_str.replace('-', '')}T{hour:02d}{minute:02d}00")

        event_body = {
            'summary': summary,
            'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'Europe/London'},
            'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'Europe/London'},
            'recurrence': recurrence
        }

        if location:
            event_body['location'] = location
        if color_id is not None:
            event_body['colorId'] = str(color_id)
        if transparency:
            event_body['transparency'] = transparency

        event = service.events().insert(calendarId='primary', body=event_body).execute()

        return {
            "status": "created",
            "event_id": event['id'],
            "summary": summary,
            "start_time": start_time,
            "days": days,
            "duration_mins": duration_mins,
            "recurrence": recurrence,
            "link": event.get('htmlLink', ''),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/calendar/invite")
async def calendar_invite(
    event_id: str = Query(..., description="Event ID to invite to"),
    email: str = Query(..., description="Email address to invite")
):
    """Add an attendee to a calendar event."""
    from .google_auth import get_calendar_service

    try:
        service = get_calendar_service()
        if not service:
            raise HTTPException(status_code=503, detail="Calendar not configured")

        # Get existing event
        event = service.events().get(calendarId='primary', eventId=event_id).execute()

        # Add attendee
        attendees = event.get('attendees', [])
        attendees.append({'email': email})
        event['attendees'] = attendees

        # Update event and send notification
        updated = service.events().update(
            calendarId='primary',
            eventId=event_id,
            body=event,
            sendUpdates='all'
        ).execute()

        return {
            "status": "invited",
            "event_id": event_id,
            "summary": updated.get('summary', ''),
            "invited": email,
            "attendee_count": len(updated.get('attendees', [])),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Drive Create & Share Endpoints
# ============================================================

class DriveCreateBody(BaseModel):
    content: Optional[str] = None
    folder_name: Optional[str] = None


@app.post("/drive/create")
async def drive_create(
    title: str = Query(..., description="Document title"),
    type: str = Query(default="document", description="Type: document, spreadsheet, presentation"),
    folder_id: Optional[str] = Query(default=None, description="Parent folder ID (optional)"),
    body: Optional[DriveCreateBody] = None
):
    """Create a new Google Doc, Sheet, or Slides — optionally with content.

    Send a JSON body with 'content' to populate the document.
    Use 'folder_name' in the body to place it in a folder by name (created if missing).
    """
    from .google_auth import get_drive_service
    import io
    from googleapiclient.http import MediaIoBaseUpload

    try:
        service = get_drive_service()
        if not service:
            raise HTTPException(status_code=503, detail="Drive not configured")

        mime_types = {
            "document": "application/vnd.google-apps.document",
            "spreadsheet": "application/vnd.google-apps.spreadsheet",
            "presentation": "application/vnd.google-apps.presentation",
            "doc": "application/vnd.google-apps.document",
            "sheet": "application/vnd.google-apps.spreadsheet",
            "slides": "application/vnd.google-apps.presentation"
        }

        target_mime = mime_types.get(type.lower())
        if not target_mime:
            raise HTTPException(status_code=400, detail=f"Unknown type: {type}. Use document, spreadsheet, or presentation")

        content = body.content if body else None
        folder_name = body.folder_name if body else None

        # Resolve folder_name → folder_id (find or create)
        if folder_name and not folder_id:
            query = (
                f"name = '{folder_name.replace(chr(39), chr(92)+chr(39))}' "
                f"and mimeType = 'application/vnd.google-apps.folder' "
                f"and trashed = false"
            )
            results = service.files().list(q=query, fields='files(id,name)', pageSize=1).execute()
            folders = results.get('files', [])
            if folders:
                folder_id = folders[0]['id']
            else:
                # Create the folder
                folder_meta = {'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder'}
                folder = service.files().create(body=folder_meta, fields='id').execute()
                folder_id = folder['id']

        file_metadata = {'name': title, 'mimeType': target_mime}
        if folder_id:
            file_metadata['parents'] = [folder_id]

        if content:
            # Upload content as HTML (preserves basic formatting) and convert to Google Doc
            upload_mime = 'text/html' if '<' in content and '>' in content else 'text/plain'
            media = MediaIoBaseUpload(
                io.BytesIO(content.encode('utf-8')),
                mimetype=upload_mime,
                resumable=False
            )
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,name,webViewLink'
            ).execute()
        else:
            file = service.files().create(body=file_metadata, fields='id,name,webViewLink').execute()

        return {
            "status": "created",
            "file_id": file['id'],
            "name": file['name'],
            "type": type,
            "link": file.get('webViewLink', ''),
            "has_content": bool(content),
            "folder_id": folder_id or None,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/drive/upload")
async def drive_upload(
    file_path: str = Query(..., description="Local file path to upload"),
    folder_id: Optional[str] = Query(default=None, description="Parent folder ID (optional)"),
    title: Optional[str] = Query(default=None, description="Override filename (optional)"),
):
    """Upload a local file to Google Drive. Returns file ID and link for use as calendar attachments etc."""
    from .google_auth import get_drive_service
    from googleapiclient.http import MediaFileUpload
    import mimetypes

    try:
        service = get_drive_service()
        if not service:
            raise HTTPException(status_code=503, detail="Drive not configured")

        p = Path(file_path)
        if not p.is_file():
            raise HTTPException(status_code=400, detail=f"File not found: {file_path}")

        content_type, _ = mimetypes.guess_type(str(p))
        if content_type is None:
            content_type = "application/octet-stream"

        file_metadata = {"name": title or p.name}
        if folder_id:
            file_metadata["parents"] = [folder_id]

        media = MediaFileUpload(str(p), mimetype=content_type, resumable=False)
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id,name,webViewLink,webContentLink",
        ).execute()

        return {
            "status": "uploaded",
            "file_id": file["id"],
            "name": file["name"],
            "mime_type": content_type,
            "link": file.get("webViewLink", ""),
            "download_link": file.get("webContentLink", ""),
            "fetched_at": datetime.now(UK_TZ).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/drive/share")
async def drive_share(
    file_id: str = Query(..., description="File ID to share"),
    email: str = Query(..., description="Email to share with"),
    role: str = Query(default="writer", description="Role: reader, commenter, writer")
):
    """Share a Drive file with someone."""
    from .google_auth import get_drive_service

    try:
        service = get_drive_service()
        if not service:
            raise HTTPException(status_code=503, detail="Drive not configured")

        permission = {
            'type': 'user',
            'role': role.lower(),
            'emailAddress': email
        }

        service.permissions().create(
            fileId=file_id,
            body=permission,
            sendNotificationEmail=True
        ).execute()

        # Get file info
        file = service.files().get(fileId=file_id, fields='name,webViewLink').execute()

        return {
            "status": "shared",
            "file_id": file_id,
            "file_name": file.get('name', ''),
            "shared_with": email,
            "role": role,
            "link": file.get('webViewLink', ''),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Places Autocomplete Endpoint
# ============================================================

@app.get("/places/autocomplete")
async def places_autocomplete(
    input: str = Query(..., description="Partial place name to autocomplete"),
    location: Optional[str] = Query(default=None, description="Bias results near this location")
):
    """Get place name suggestions for autocomplete."""
    import httpx
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Google Maps API not configured")

    try:
        params = {
            "input": input,
            "key": api_key,
            "types": "establishment|geocode"
        }

        # Add location bias if provided
        if location:
            # Geocode location first
            async with httpx.AsyncClient() as client:
                geo_response = await client.get(
                    "https://maps.googleapis.com/maps/api/geocode/json",
                    params={"address": location, "key": api_key},
                    timeout=30
                )
                geo_data = geo_response.json()

            if geo_data.get("status") == "OK" and geo_data.get("results"):
                loc = geo_data["results"][0]["geometry"]["location"]
                params["location"] = f"{loc['lat']},{loc['lng']}"
                params["radius"] = 50000  # 50km bias

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/place/autocomplete/json",
                params=params,
                timeout=30
            )
            data = response.json()

        if data.get("status") != "OK" and data.get("status") != "ZERO_RESULTS":
            return {"error": f"Autocomplete failed: {data.get('status')}"}

        suggestions = []
        for pred in data.get("predictions", [])[:5]:
            suggestions.append({
                "description": pred.get("description"),
                "place_id": pred.get("place_id"),
                "main_text": pred.get("structured_formatting", {}).get("main_text"),
                "secondary_text": pred.get("structured_formatting", {}).get("secondary_text")
            })

        return {
            "input": input,
            "suggestions": suggestions,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Contacts Endpoint
# ============================================================

@app.get("/contacts/search")
async def contacts_search(
    q: str = Query(..., description="Search query (name, email, phone)")
):
    """Search Google Contacts."""
    from .google_auth import get_credentials
    from googleapiclient.discovery import build

    try:
        creds = get_credentials()
        if not creds:
            raise HTTPException(status_code=503, detail="Google auth not configured")

        # Build People API service
        service = build('people', 'v1', credentials=creds)

        # Search contacts
        results = service.people().searchContacts(
            query=q,
            readMask='names,emailAddresses,phoneNumbers,organizations',
            pageSize=10
        ).execute()

        contacts = []
        for result in results.get('results', []):
            person = result.get('person', {})
            names = person.get('names', [{}])
            emails = person.get('emailAddresses', [])
            phones = person.get('phoneNumbers', [])
            orgs = person.get('organizations', [])

            contacts.append({
                "name": names[0].get('displayName', '') if names else '',
                "email": emails[0].get('value', '') if emails else '',
                "phone": phones[0].get('value', '') if phones else '',
                "organization": orgs[0].get('name', '') if orgs else '',
                "resource_name": person.get('resourceName', '')
            })

        return {
            "query": q,
            "count": len(contacts),
            "contacts": contacts,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Gmail Archive, Trash, Mark Read Endpoints
# ============================================================

@app.post("/gmail/archive")
async def gmail_archive(message_id: str = Query(..., description="Email message ID")):
    """Archive an email (remove from inbox)."""
    from .google_auth import get_gmail_service

    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=503, detail="Gmail not configured")

        # Remove INBOX label to archive
        service.users().messages().modify(
            userId='me',
            id=message_id,
            body={'removeLabelIds': ['INBOX']}
        ).execute()

        return {
            "status": "archived",
            "message_id": message_id,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/gmail/trash")
async def gmail_trash(message_id: str = Query(..., description="Email message ID")):
    """Move an email to trash."""
    from .google_auth import get_gmail_service

    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=503, detail="Gmail not configured")

        service.users().messages().trash(userId='me', id=message_id).execute()

        return {
            "status": "trashed",
            "message_id": message_id,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/gmail/mark-read")
async def gmail_mark_read(
    message_id: str = Query(..., description="Email message ID"),
    read: bool = Query(default=True, description="True to mark as read, False for unread")
):
    """Mark an email as read or unread."""
    from .google_auth import get_gmail_service

    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=503, detail="Gmail not configured")

        if read:
            body = {'removeLabelIds': ['UNREAD']}
        else:
            body = {'addLabelIds': ['UNREAD']}

        service.users().messages().modify(
            userId='me',
            id=message_id,
            body=body
        ).execute()

        return {
            "status": "marked_read" if read else "marked_unread",
            "message_id": message_id,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/gmail/forward")
async def gmail_forward(
    message_id: str = Query(..., description="Email message ID to forward"),
    to: str = Query(..., description="Recipient email address"),
    comment: Optional[str] = Query(default=None, description="Optional comment to add")
):
    """Forward an email."""
    from .google_auth import get_gmail_service
    import base64
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=503, detail="Gmail not configured")

        # Get original message
        original = service.users().messages().get(
            userId='me',
            id=message_id,
            format='full'
        ).execute()

        headers = {h['name']: h['value'] for h in original.get('payload', {}).get('headers', [])}
        original_subject = headers.get('Subject', '(no subject)')
        original_from = headers.get('From', 'Unknown')
        original_date = headers.get('Date', '')

        # Extract body
        def extract_text(part):
            text = ""
            if part.get('mimeType') == 'text/plain':
                data = part.get('body', {}).get('data', '')
                if data:
                    text = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
            for subpart in part.get('parts', []):
                text += extract_text(subpart)
            return text

        original_body = extract_text(original.get('payload', {}))

        # Build forwarded message
        forward_body = ""
        if comment:
            forward_body = f"{comment}\n\n"
        forward_body += f"---------- Forwarded message ----------\n"
        forward_body += f"From: {original_from}\n"
        forward_body += f"Date: {original_date}\n"
        forward_body += f"Subject: {original_subject}\n\n"
        forward_body += original_body

        message = MIMEText(forward_body)
        message['to'] = to
        message['subject'] = f"Fwd: {original_subject}"

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        sent = service.users().messages().send(
            userId='me',
            body={'raw': raw}
        ).execute()

        return {
            "status": "forwarded",
            "original_message_id": message_id,
            "new_message_id": sent['id'],
            "to": to,
            "subject": f"Fwd: {original_subject}",
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Calendar Calendars List & Freebusy Endpoints
# ============================================================

@app.get("/calendar/calendars")
async def calendar_calendars():
    """List all calendars."""
    from .google_auth import get_calendar_service

    try:
        service = get_calendar_service()
        if not service:
            raise HTTPException(status_code=503, detail="Calendar not configured")

        calendars_result = service.calendarList().list().execute()

        calendars = []
        for cal in calendars_result.get('items', []):
            calendars.append({
                "id": cal['id'],
                "summary": cal.get('summary', ''),
                "description": cal.get('description', ''),
                "primary": cal.get('primary', False),
                "access_role": cal.get('accessRole', ''),
                "background_color": cal.get('backgroundColor', '')
            })

        return {
            "count": len(calendars),
            "calendars": calendars,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/calendar/busy")
async def calendar_busy(
    email: str = Query(..., description="Email address to check"),
    date: Optional[str] = Query(default=None, description="Date to check (YYYY-MM-DD, default: today)")
):
    """Check if someone is busy using freebusy API."""
    from .google_auth import get_calendar_service

    try:
        service = get_calendar_service()
        if not service:
            raise HTTPException(status_code=503, detail="Calendar not configured")

        if date:
            check_date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UK_TZ)
        else:
            check_date = datetime.now(UK_TZ)

        start_of_day = check_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        body = {
            "timeMin": start_of_day.isoformat(),
            "timeMax": end_of_day.isoformat(),
            "items": [{"id": email}]
        }

        result = service.freebusy().query(body=body).execute()
        calendar_data = result.get('calendars', {}).get(email, {})
        busy_times = calendar_data.get('busy', [])

        formatted_busy = []
        for busy in busy_times:
            start = datetime.fromisoformat(busy['start'].replace('Z', '+00:00'))
            end = datetime.fromisoformat(busy['end'].replace('Z', '+00:00'))
            formatted_busy.append({
                "start": start.astimezone(UK_TZ).strftime("%H:%M"),
                "end": end.astimezone(UK_TZ).strftime("%H:%M")
            })

        return {
            "email": email,
            "date": check_date.strftime("%Y-%m-%d"),
            "is_busy": len(busy_times) > 0,
            "busy_periods": formatted_busy,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Drive Recent, Trash, Folder, Move Endpoints
# ============================================================

@app.get("/drive/recent")
async def drive_recent(limit: int = Query(default=10, le=20)):
    """Get recently accessed files."""
    from .google_auth import get_drive_service

    try:
        service = get_drive_service()
        if not service:
            raise HTTPException(status_code=503, detail="Drive not configured")

        results = service.files().list(
            pageSize=limit,
            orderBy='viewedByMeTime desc',
            fields='files(id, name, mimeType, webViewLink, viewedByMeTime, modifiedTime)',
            q="'me' in owners or 'me' in readers"
        ).execute()

        files = []
        for f in results.get('files', []):
            files.append({
                "id": f['id'],
                "name": f['name'],
                "type": f.get('mimeType', '').split('.')[-1],
                "link": f.get('webViewLink', ''),
                "viewed": f.get('viewedByMeTime', ''),
                "modified": f.get('modifiedTime', '')
            })

        return {
            "count": len(files),
            "files": files,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/drive/trash")
async def drive_trash(file_id: str = Query(..., description="File ID to trash")):
    """Move a file to trash."""
    from .google_auth import get_drive_service

    try:
        service = get_drive_service()
        if not service:
            raise HTTPException(status_code=503, detail="Drive not configured")

        # Get file name first
        file = service.files().get(fileId=file_id, fields='name').execute()

        # Trash it
        service.files().update(fileId=file_id, body={'trashed': True}).execute()

        return {
            "status": "trashed",
            "file_id": file_id,
            "file_name": file.get('name', ''),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/drive/folder")
async def drive_folder(
    name: str = Query(..., description="Folder name"),
    parent_id: Optional[str] = Query(default=None, description="Parent folder ID (optional)")
):
    """Create a new folder."""
    from .google_auth import get_drive_service

    try:
        service = get_drive_service()
        if not service:
            raise HTTPException(status_code=503, detail="Drive not configured")

        file_metadata = {
            'name': name,
            'mimeType': 'application/vnd.google-apps.folder'
        }

        if parent_id:
            file_metadata['parents'] = [parent_id]

        folder = service.files().create(body=file_metadata, fields='id,name,webViewLink').execute()

        return {
            "status": "created",
            "folder_id": folder['id'],
            "name": folder['name'],
            "link": folder.get('webViewLink', ''),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/drive/move")
async def drive_move(
    file_id: str = Query(..., description="File ID to move"),
    folder_id: str = Query(..., description="Destination folder ID")
):
    """Move a file to a folder."""
    from .google_auth import get_drive_service

    try:
        service = get_drive_service()
        if not service:
            raise HTTPException(status_code=503, detail="Drive not configured")

        # Get current parents
        file = service.files().get(fileId=file_id, fields='name,parents').execute()
        previous_parents = ",".join(file.get('parents', []))

        # Move file
        service.files().update(
            fileId=file_id,
            addParents=folder_id,
            removeParents=previous_parents,
            fields='id,name,parents'
        ).execute()

        return {
            "status": "moved",
            "file_id": file_id,
            "file_name": file.get('name', ''),
            "to_folder": folder_id,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Google Tasks Endpoints
# ============================================================

@app.get("/tasks/list")
async def tasks_list(
    tasklist: str = Query(default="@default", description="Task list ID (default: primary)")
):
    """Get tasks from Google Tasks."""
    from .google_auth import get_credentials
    from googleapiclient.discovery import build

    try:
        creds = get_credentials()
        if not creds:
            raise HTTPException(status_code=503, detail="Google auth not configured")

        service = build('tasks', 'v1', credentials=creds)

        results = service.tasks().list(
            tasklist=tasklist,
            showCompleted=False,
            maxResults=20
        ).execute()

        tasks = []
        for task in results.get('items', []):
            tasks.append({
                "id": task['id'],
                "title": task.get('title', ''),
                "notes": task.get('notes', ''),
                "due": task.get('due', ''),
                "status": task.get('status', ''),
                "updated": task.get('updated', '')
            })

        return {
            "tasklist": tasklist,
            "count": len(tasks),
            "tasks": tasks,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tasks/create")
async def tasks_create(
    title: str = Query(..., description="Task title"),
    notes: Optional[str] = Query(default=None, description="Task notes"),
    due: Optional[str] = Query(default=None, description="Due date (YYYY-MM-DD)"),
    tasklist: str = Query(default="@default", description="Task list ID")
):
    """Create a new task."""
    from .google_auth import get_credentials
    from googleapiclient.discovery import build

    try:
        creds = get_credentials()
        if not creds:
            raise HTTPException(status_code=503, detail="Google auth not configured")

        service = build('tasks', 'v1', credentials=creds)

        task_body = {'title': title}
        if notes:
            task_body['notes'] = notes
        if due:
            task_body['due'] = f"{due}T00:00:00.000Z"

        task = service.tasks().insert(tasklist=tasklist, body=task_body).execute()

        return {
            "status": "created",
            "task_id": task['id'],
            "title": title,
            "due": due,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tasks/complete")
async def tasks_complete(
    task_id: str = Query(..., description="Task ID"),
    tasklist: str = Query(default="@default", description="Task list ID")
):
    """Mark a task as complete."""
    from .google_auth import get_credentials
    from googleapiclient.discovery import build

    try:
        creds = get_credentials()
        if not creds:
            raise HTTPException(status_code=503, detail="Google auth not configured")

        service = build('tasks', 'v1', credentials=creds)

        # Get current task
        task = service.tasks().get(tasklist=tasklist, task=task_id).execute()
        task['status'] = 'completed'

        updated = service.tasks().update(tasklist=tasklist, task=task_id, body=task).execute()

        return {
            "status": "completed",
            "task_id": task_id,
            "title": updated.get('title', ''),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Translate Endpoint
# ============================================================

@app.get("/translate")
async def translate(
    text: str = Query(..., description="Text to translate"),
    target: str = Query(default="en", description="Target language code (e.g., en, es, fr, de, ja, zh)"),
    source: Optional[str] = Query(default=None, description="Source language (auto-detect if not specified)")
):
    """Translate text using Google Translate API."""
    import httpx
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")  # Same key works for translate
    if not api_key:
        raise HTTPException(status_code=503, detail="Google API not configured")

    try:
        params = {
            "q": text,
            "target": target,
            "key": api_key
        }
        if source:
            params["source"] = source

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://translation.googleapis.com/language/translate/v2",
                params=params,
                timeout=30
            )
            data = response.json()

        if "error" in data:
            return {"error": data["error"].get("message", "Translation failed")}

        translations = data.get("data", {}).get("translations", [])
        if not translations:
            return {"error": "No translation returned"}

        result = translations[0]

        return {
            "original": text,
            "translated": result.get("translatedText", ""),
            "source_language": result.get("detectedSourceLanguage", source or "auto"),
            "target_language": target,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# YouTube Search Endpoint
# ============================================================

@app.get("/youtube/search")
async def youtube_search(
    q: str = Query(..., description="Search query"),
    limit: int = Query(default=5, le=10, description="Number of results")
):
    """Search YouTube videos."""
    import httpx
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")  # Same key can work, or use YOUTUBE_API_KEY
    youtube_key = os.getenv("YOUTUBE_API_KEY", api_key)

    if not youtube_key:
        raise HTTPException(status_code=503, detail="YouTube API not configured")

    try:
        params = {
            "part": "snippet",
            "q": q,
            "type": "video",
            "maxResults": limit,
            "key": youtube_key
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://www.googleapis.com/youtube/v3/search",
                params=params,
                timeout=30
            )
            data = response.json()

        if "error" in data:
            return {"error": data["error"].get("message", "Search failed")}

        videos = []
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            video_id = item.get("id", {}).get("videoId", "")
            videos.append({
                "video_id": video_id,
                "title": snippet.get("title", ""),
                "channel": snippet.get("channelTitle", ""),
                "description": snippet.get("description", "")[:150],
                "published": snippet.get("publishedAt", ""),
                "thumbnail": snippet.get("thumbnails", {}).get("medium", {}).get("url", ""),
                "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
            })

        return {
            "query": q,
            "count": len(videos),
            "videos": videos,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# BATCH 4: Gmail Reply, Vacation, Filters, Signature
# ============================================================

@app.post("/gmail/reply")
async def gmail_reply(
    message_id: str = Query(..., description="Message ID to reply to"),
    body: str = Query(..., description="Reply text"),
    attachments: list[str] = Query(default=[], description="Local file paths to attach"),
):
    """Reply to an email, optionally with file attachments."""
    from .google_auth import get_gmail_service
    import base64

    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=503, detail="Gmail not configured")

        # Get original message
        original = service.users().messages().get(
            userId='me', id=message_id, format='metadata',
            metadataHeaders=['Subject', 'From', 'To', 'Message-ID']
        ).execute()

        headers = {h['name']: h['value'] for h in original.get('payload', {}).get('headers', [])}
        thread_id = original.get('threadId')

        # Build reply
        message = _build_mime_message(body, attachments)
        message['to'] = headers.get('From', '')
        subject = headers.get('Subject', '')
        message['subject'] = f"Re: {subject}" if not subject.startswith('Re:') else subject
        message['In-Reply-To'] = headers.get('Message-ID', '')
        message['References'] = headers.get('Message-ID', '')

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        sent = service.users().messages().send(
            userId='me',
            body={'raw': raw, 'threadId': thread_id}
        ).execute()

        return {
            "status": "replied",
            "original_id": message_id,
            "reply_id": sent['id'],
            "to": headers.get('From', ''),
            "attachments": [Path(a).name for a in attachments],
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gmail/vacation")
async def gmail_vacation_get():
    """Get vacation responder settings."""
    from .google_auth import get_gmail_service

    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=503, detail="Gmail not configured")

        settings = service.users().settings().getVacation(userId='me').execute()

        return {
            "enabled": settings.get('enableAutoReply', False),
            "subject": settings.get('responseSubject', ''),
            "message": settings.get('responseBodyPlainText', ''),
            "start_time": settings.get('startTime'),
            "end_time": settings.get('endTime'),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/gmail/vacation")
async def gmail_vacation_set(
    enabled: bool = Query(..., description="Enable or disable"),
    subject: Optional[str] = Query(default=None, description="Auto-reply subject"),
    message: Optional[str] = Query(default=None, description="Auto-reply message")
):
    """Set vacation responder."""
    from .google_auth import get_gmail_service

    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=503, detail="Gmail not configured")

        body = {'enableAutoReply': enabled}
        if subject:
            body['responseSubject'] = subject
        if message:
            body['responseBodyPlainText'] = message

        service.users().settings().updateVacation(userId='me', body=body).execute()

        return {
            "status": "updated",
            "enabled": enabled,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gmail/filters")
async def gmail_filters():
    """List email filters."""
    from .google_auth import get_gmail_service

    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=503, detail="Gmail not configured")

        results = service.users().settings().filters().list(userId='me').execute()

        filters = []
        for f in results.get('filter', []):
            criteria = f.get('criteria', {})
            action = f.get('action', {})
            filters.append({
                "id": f.get('id'),
                "from": criteria.get('from'),
                "to": criteria.get('to'),
                "subject": criteria.get('subject'),
                "has_words": criteria.get('query'),
                "add_labels": action.get('addLabelIds', []),
                "remove_labels": action.get('removeLabelIds', []),
                "forward_to": action.get('forward')
            })

        return {
            "count": len(filters),
            "filters": filters,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gmail/signature")
async def gmail_signature():
    """Get email signature."""
    from .google_auth import get_gmail_service

    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=503, detail="Gmail not configured")

        # Get send-as addresses to find primary
        sendas = service.users().settings().sendAs().list(userId='me').execute()

        signatures = []
        for addr in sendas.get('sendAs', []):
            if addr.get('isPrimary'):
                signatures.append({
                    "email": addr.get('sendAsEmail'),
                    "signature": addr.get('signature', ''),
                    "is_primary": True
                })

        return {
            "signatures": signatures,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# BATCH 5: Calendar Search, QuickAdd, Next, Conflicts
# ============================================================

@app.get("/calendar/search")
async def calendar_search(
    q: str = Query(..., description="Search query"),
    limit: int = Query(default=10, le=25)
):
    """Search calendar events."""
    from .google_auth import get_calendar_service

    try:
        service = get_calendar_service()
        if not service:
            raise HTTPException(status_code=503, detail="Calendar not configured")

        now = datetime.now(UK_TZ)
        all_items = _fetch_all_calendars(
            service,
            timeMin=(now - timedelta(days=365)).isoformat(),
            timeMax=(now + timedelta(days=365)).isoformat(),
            q=q,
            singleEvents=True,
            orderBy='startTime',
            maxResults=limit
        )

        events = []
        for event in all_items[:limit]:
            events.append({
                "id": event['id'],
                "summary": event.get('summary', '(No title)'),
                "start": event.get('start', {}).get('dateTime', event.get('start', {}).get('date', '')),
                "end": event.get('end', {}).get('dateTime', event.get('end', {}).get('date', '')),
                "location": event.get('location', ''),
                "calendar": event.get('_calendar', 'Chris')
            })

        events.sort(key=lambda e: e['start'] or '')

        return {
            "query": q,
            "count": len(events),
            "events": events,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/calendar/quickadd")
async def calendar_quickadd(
    text: str = Query(..., description="Natural language event description")
):
    """Create event using natural language (e.g., 'Lunch with Sarah tomorrow at noon')."""
    from .google_auth import get_calendar_service

    try:
        service = get_calendar_service()
        if not service:
            raise HTTPException(status_code=503, detail="Calendar not configured")

        event = service.events().quickAdd(calendarId='primary', text=text).execute()

        return {
            "status": "created",
            "event_id": event['id'],
            "summary": event.get('summary', ''),
            "start": event.get('start', {}).get('dateTime', event.get('start', {}).get('date', '')),
            "end": event.get('end', {}).get('dateTime', event.get('end', {}).get('date', '')),
            "link": event.get('htmlLink', ''),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/calendar/next")
async def calendar_next(limit: int = Query(default=5, le=10)):
    """Get next upcoming events."""
    from .google_auth import get_calendar_service

    try:
        service = get_calendar_service()
        if not service:
            raise HTTPException(status_code=503, detail="Calendar not configured")

        now = datetime.now(UK_TZ)
        all_items = _fetch_all_calendars(
            service,
            timeMin=now.isoformat(),
            singleEvents=True,
            orderBy='startTime',
            maxResults=limit
        )

        events = []
        for event in all_items:
            start = event.get('start', {}).get('dateTime', event.get('start', {}).get('date', ''))
            events.append({
                "id": event['id'],
                "summary": event.get('summary', '(No title)'),
                "start": start,
                "location": event.get('location', ''),
                "calendar": event.get('_calendar', 'Chris')
            })

        events.sort(key=lambda e: e['start'] or '')
        events = events[:limit]

        return {
            "count": len(events),
            "events": events,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/calendar/conflicts")
async def calendar_conflicts(
    start_date: Optional[str] = Query(default=None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(default=None, description="End date (YYYY-MM-DD)")
):
    """Find scheduling conflicts (overlapping events)."""
    from .google_auth import get_calendar_service

    try:
        service = get_calendar_service()
        if not service:
            raise HTTPException(status_code=503, detail="Calendar not configured")

        now = datetime.now(UK_TZ)
        if start_date:
            start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=UK_TZ)
        else:
            start = now
        if end_date:
            end = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, tzinfo=UK_TZ)
        else:
            end = start + timedelta(days=7)

        events_result = service.events().list(
            calendarId='primary',
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        conflicts = []

        for i, event1 in enumerate(events):
            start1 = event1.get('start', {}).get('dateTime')
            end1 = event1.get('end', {}).get('dateTime')
            if not start1 or not end1:
                continue

            start1_dt = datetime.fromisoformat(start1)
            end1_dt = datetime.fromisoformat(end1)

            for event2 in events[i+1:]:
                start2 = event2.get('start', {}).get('dateTime')
                end2 = event2.get('end', {}).get('dateTime')
                if not start2 or not end2:
                    continue

                start2_dt = datetime.fromisoformat(start2)
                end2_dt = datetime.fromisoformat(end2)

                # Check overlap
                if start1_dt < end2_dt and start2_dt < end1_dt:
                    conflicts.append({
                        "event1": {"summary": event1.get('summary', ''), "start": start1},
                        "event2": {"summary": event2.get('summary', ''), "start": start2}
                    })

        return {
            "period": f"{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}",
            "conflict_count": len(conflicts),
            "conflicts": conflicts,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# BATCH 6: Drive Download, Copy, Rename, Export, Permissions, Storage, Starred, Shared
# ============================================================

@app.get("/drive/download")
async def drive_download(file_id: str = Query(..., description="File ID")):
    """Get download link for a file."""
    from .google_auth import get_drive_service

    try:
        service = get_drive_service()
        if not service:
            raise HTTPException(status_code=503, detail="Drive not configured")

        file = service.files().get(
            fileId=file_id,
            fields='id,name,mimeType,webContentLink,webViewLink'
        ).execute()

        return {
            "file_id": file_id,
            "name": file.get('name', ''),
            "mime_type": file.get('mimeType', ''),
            "download_link": file.get('webContentLink', ''),
            "view_link": file.get('webViewLink', ''),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/drive/copy")
async def drive_copy(
    file_id: str = Query(..., description="File ID to copy"),
    name: Optional[str] = Query(default=None, description="New file name")
):
    """Copy a file."""
    from .google_auth import get_drive_service

    try:
        service = get_drive_service()
        if not service:
            raise HTTPException(status_code=503, detail="Drive not configured")

        body = {}
        if name:
            body['name'] = name

        copied = service.files().copy(fileId=file_id, body=body, fields='id,name,webViewLink').execute()

        return {
            "status": "copied",
            "original_id": file_id,
            "new_id": copied['id'],
            "name": copied.get('name', ''),
            "link": copied.get('webViewLink', ''),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/drive/rename")
async def drive_rename(
    file_id: str = Query(..., description="File ID"),
    name: str = Query(..., description="New name")
):
    """Rename a file."""
    from .google_auth import get_drive_service

    try:
        service = get_drive_service()
        if not service:
            raise HTTPException(status_code=503, detail="Drive not configured")

        updated = service.files().update(
            fileId=file_id,
            body={'name': name},
            fields='id,name'
        ).execute()

        return {
            "status": "renamed",
            "file_id": file_id,
            "new_name": updated.get('name', ''),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/drive/export")
async def drive_export(
    file_id: str = Query(..., description="File ID"),
    format: str = Query(default="pdf", description="Export format: pdf, docx, xlsx, pptx, txt")
):
    """Export a Google Doc/Sheet/Slides to downloadable format."""
    from .google_auth import get_drive_service

    try:
        service = get_drive_service()
        if not service:
            raise HTTPException(status_code=503, detail="Drive not configured")

        mime_map = {
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "txt": "text/plain"
        }

        mime_type = mime_map.get(format.lower())
        if not mime_type:
            raise HTTPException(status_code=400, detail=f"Unknown format: {format}")

        # Get file info
        file = service.files().get(fileId=file_id, fields='name,mimeType').execute()

        # Note: Actual export would return binary data, here we return the export link
        export_link = f"https://www.googleapis.com/drive/v3/files/{file_id}/export?mimeType={mime_type}"

        return {
            "file_id": file_id,
            "name": file.get('name', ''),
            "export_format": format,
            "export_mime": mime_type,
            "note": "Use export link with OAuth token to download",
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/drive/permissions")
async def drive_permissions(file_id: str = Query(..., description="File ID")):
    """List who has access to a file."""
    from .google_auth import get_drive_service

    try:
        service = get_drive_service()
        if not service:
            raise HTTPException(status_code=503, detail="Drive not configured")

        file = service.files().get(fileId=file_id, fields='name').execute()
        perms = service.permissions().list(fileId=file_id, fields='permissions(id,emailAddress,role,type)').execute()

        permissions = []
        for p in perms.get('permissions', []):
            permissions.append({
                "email": p.get('emailAddress', ''),
                "role": p.get('role', ''),
                "type": p.get('type', '')
            })

        return {
            "file_id": file_id,
            "file_name": file.get('name', ''),
            "permissions": permissions,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/drive/storage")
async def drive_storage():
    """Get Drive storage usage."""
    from .google_auth import get_drive_service

    try:
        service = get_drive_service()
        if not service:
            raise HTTPException(status_code=503, detail="Drive not configured")

        about = service.about().get(fields='storageQuota').execute()
        quota = about.get('storageQuota', {})

        limit_gb = int(quota.get('limit', 0)) / (1024**3)
        usage_gb = int(quota.get('usage', 0)) / (1024**3)
        trash_gb = int(quota.get('usageInDriveTrash', 0)) / (1024**3)

        return {
            "limit_gb": round(limit_gb, 2),
            "usage_gb": round(usage_gb, 2),
            "trash_gb": round(trash_gb, 2),
            "available_gb": round(limit_gb - usage_gb, 2),
            "percent_used": round((usage_gb / limit_gb) * 100, 1) if limit_gb > 0 else 0,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/drive/starred")
async def drive_starred(limit: int = Query(default=10, le=20)):
    """Get starred files."""
    from .google_auth import get_drive_service

    try:
        service = get_drive_service()
        if not service:
            raise HTTPException(status_code=503, detail="Drive not configured")

        results = service.files().list(
            q="starred=true",
            pageSize=limit,
            fields='files(id,name,mimeType,webViewLink,modifiedTime)'
        ).execute()

        files = []
        for f in results.get('files', []):
            files.append({
                "id": f['id'],
                "name": f['name'],
                "type": f.get('mimeType', '').split('.')[-1],
                "link": f.get('webViewLink', ''),
                "modified": f.get('modifiedTime', '')
            })

        return {
            "count": len(files),
            "files": files,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/drive/shared")
async def drive_shared(limit: int = Query(default=10, le=20)):
    """Get files shared with me."""
    from .google_auth import get_drive_service

    try:
        service = get_drive_service()
        if not service:
            raise HTTPException(status_code=503, detail="Drive not configured")

        results = service.files().list(
            q="sharedWithMe=true",
            pageSize=limit,
            orderBy='sharedWithMeTime desc',
            fields='files(id,name,mimeType,webViewLink,sharingUser)'
        ).execute()

        files = []
        for f in results.get('files', []):
            sharing_user = f.get('sharingUser', {})
            files.append({
                "id": f['id'],
                "name": f['name'],
                "type": f.get('mimeType', '').split('.')[-1],
                "link": f.get('webViewLink', ''),
                "shared_by": sharing_user.get('displayName', sharing_user.get('emailAddress', ''))
            })

        return {
            "count": len(files),
            "files": files,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# BATCH 7: Sheets Read, Write, Append, Clear, Info
# ============================================================

@app.get("/sheets/read")
async def sheets_read(
    spreadsheet_id: str = Query(..., description="Spreadsheet ID"),
    range: str = Query(default="A1:Z100", description="Range to read (e.g., 'Sheet1!A1:D10')")
):
    """Read data from a Google Sheet."""
    from .google_auth import get_credentials
    from googleapiclient.discovery import build

    try:
        creds = get_credentials()
        if not creds:
            raise HTTPException(status_code=503, detail="Google auth not configured")

        service = build('sheets', 'v4', credentials=creds)
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range
        ).execute()

        values = result.get('values', [])

        return {
            "spreadsheet_id": spreadsheet_id,
            "range": range,
            "row_count": len(values),
            "data": values,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sheets/write")
async def sheets_write(
    spreadsheet_id: str = Query(..., description="Spreadsheet ID"),
    range: str = Query(..., description="Range to write (e.g., 'A1')"),
    values: str = Query(..., description="Values as JSON array, e.g., [[\"A\",\"B\"],[\"C\",\"D\"]]")
):
    """Write data to a Google Sheet."""
    from .google_auth import get_credentials
    from googleapiclient.discovery import build
    import json

    try:
        creds = get_credentials()
        if not creds:
            raise HTTPException(status_code=503, detail="Google auth not configured")

        data = json.loads(values)
        service = build('sheets', 'v4', credentials=creds)

        result = service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range,
            valueInputOption='USER_ENTERED',
            body={'values': data}
        ).execute()

        return {
            "status": "written",
            "spreadsheet_id": spreadsheet_id,
            "range": result.get('updatedRange', range),
            "cells_updated": result.get('updatedCells', 0),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sheets/append")
async def sheets_append(
    spreadsheet_id: str = Query(..., description="Spreadsheet ID"),
    range: str = Query(default="A1", description="Range to append after"),
    values: str = Query(..., description="Row values as JSON array, e.g., [\"A\",\"B\",\"C\"]")
):
    """Append a row to a Google Sheet."""
    from .google_auth import get_credentials
    from googleapiclient.discovery import build
    import json

    try:
        creds = get_credentials()
        if not creds:
            raise HTTPException(status_code=503, detail="Google auth not configured")

        row = json.loads(values)
        if not isinstance(row[0], list):
            row = [row]

        service = build('sheets', 'v4', credentials=creds)
        result = service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range,
            valueInputOption='USER_ENTERED',
            insertDataOption='INSERT_ROWS',
            body={'values': row}
        ).execute()

        return {
            "status": "appended",
            "spreadsheet_id": spreadsheet_id,
            "range": result.get('updates', {}).get('updatedRange', ''),
            "rows_appended": result.get('updates', {}).get('updatedRows', 0),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sheets/clear")
async def sheets_clear(
    spreadsheet_id: str = Query(..., description="Spreadsheet ID"),
    range: str = Query(..., description="Range to clear")
):
    """Clear data from a range in a Google Sheet."""
    from .google_auth import get_credentials
    from googleapiclient.discovery import build

    try:
        creds = get_credentials()
        if not creds:
            raise HTTPException(status_code=503, detail="Google auth not configured")

        service = build('sheets', 'v4', credentials=creds)
        service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range=range
        ).execute()

        return {
            "status": "cleared",
            "spreadsheet_id": spreadsheet_id,
            "range": range,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sheets/info")
async def sheets_info(spreadsheet_id: str = Query(..., description="Spreadsheet ID")):
    """Get spreadsheet metadata."""
    from .google_auth import get_credentials
    from googleapiclient.discovery import build

    try:
        creds = get_credentials()
        if not creds:
            raise HTTPException(status_code=503, detail="Google auth not configured")

        service = build('sheets', 'v4', credentials=creds)
        spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()

        sheets = []
        for sheet in spreadsheet.get('sheets', []):
            props = sheet.get('properties', {})
            grid = props.get('gridProperties', {})
            sheets.append({
                "id": props.get('sheetId'),
                "title": props.get('title', ''),
                "rows": grid.get('rowCount', 0),
                "columns": grid.get('columnCount', 0)
            })

        return {
            "spreadsheet_id": spreadsheet_id,
            "title": spreadsheet.get('properties', {}).get('title', ''),
            "sheet_count": len(sheets),
            "sheets": sheets,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# BATCH 8: Docs Read, Append
# ============================================================

@app.get("/docs/read")
async def docs_read(document_id: str = Query(..., description="Document ID")):
    """Read content from a Google Doc."""
    from .google_auth import get_credentials
    from googleapiclient.discovery import build

    try:
        creds = get_credentials()
        if not creds:
            raise HTTPException(status_code=503, detail="Google auth not configured")

        service = build('docs', 'v1', credentials=creds)
        doc = service.documents().get(documentId=document_id).execute()

        # Extract text content
        content = []
        for element in doc.get('body', {}).get('content', []):
            if 'paragraph' in element:
                for elem in element['paragraph'].get('elements', []):
                    if 'textRun' in elem:
                        content.append(elem['textRun'].get('content', ''))

        text = ''.join(content)

        return {
            "document_id": document_id,
            "title": doc.get('title', ''),
            "content": text[:10000],  # Limit to 10k chars
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/docs/append")
async def docs_append(
    document_id: str = Query(..., description="Document ID"),
    text: str = Query(..., description="Text to append")
):
    """Append text to a Google Doc."""
    from .google_auth import get_credentials
    from googleapiclient.discovery import build

    try:
        creds = get_credentials()
        if not creds:
            raise HTTPException(status_code=503, detail="Google auth not configured")

        service = build('docs', 'v1', credentials=creds)

        # Get doc to find end index
        doc = service.documents().get(documentId=document_id).execute()
        end_index = doc.get('body', {}).get('content', [{}])[-1].get('endIndex', 1) - 1

        # Insert text at end
        requests = [{
            'insertText': {
                'location': {'index': end_index},
                'text': '\n' + text
            }
        }]

        service.documents().batchUpdate(documentId=document_id, body={'requests': requests}).execute()

        return {
            "status": "appended",
            "document_id": document_id,
            "text_length": len(text),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# BATCH 9: Maps Static, StreetView, Distance
# ============================================================

@app.get("/maps/static")
async def maps_static(
    location: str = Query(..., description="Location or address"),
    zoom: int = Query(default=14, description="Zoom level (1-20)"),
    size: str = Query(default="400x300", description="Image size WxH")
):
    """Generate a static map image URL."""
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Google Maps API not configured")

    url = f"https://maps.googleapis.com/maps/api/staticmap?center={location}&zoom={zoom}&size={size}&key={api_key}"

    return {
        "location": location,
        "zoom": zoom,
        "size": size,
        "image_url": url,
        "fetched_at": datetime.now(UK_TZ).isoformat()
    }


@app.get("/maps/streetview")
async def maps_streetview(
    location: str = Query(..., description="Location or address"),
    heading: int = Query(default=0, description="Camera heading (0-360)"),
    size: str = Query(default="400x300", description="Image size WxH")
):
    """Generate a Street View image URL."""
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Google Maps API not configured")

    url = f"https://maps.googleapis.com/maps/api/streetview?location={location}&heading={heading}&size={size}&key={api_key}"

    return {
        "location": location,
        "heading": heading,
        "size": size,
        "image_url": url,
        "fetched_at": datetime.now(UK_TZ).isoformat()
    }


@app.get("/distance")
async def distance(
    origin: str = Query(..., description="Origin location"),
    destination: str = Query(..., description="Destination location")
):
    """Get straight-line distance between two points."""
    import httpx
    from dotenv import load_dotenv
    import math
    load_dotenv()

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Google Maps API not configured")

    try:
        async with httpx.AsyncClient() as client:
            # Geocode origin
            r1 = await client.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={"address": origin, "key": api_key}
            )
            d1 = r1.json()
            if d1.get("status") != "OK":
                return {"error": f"Could not geocode origin: {origin}"}
            loc1 = d1["results"][0]["geometry"]["location"]

            # Geocode destination
            r2 = await client.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={"address": destination, "key": api_key}
            )
            d2 = r2.json()
            if d2.get("status") != "OK":
                return {"error": f"Could not geocode destination: {destination}"}
            loc2 = d2["results"][0]["geometry"]["location"]

        # Haversine formula
        R = 6371  # Earth radius in km
        lat1, lon1 = math.radians(loc1["lat"]), math.radians(loc1["lng"])
        lat2, lon2 = math.radians(loc2["lat"]), math.radians(loc2["lng"])

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        distance_km = R * c

        return {
            "origin": origin,
            "destination": destination,
            "distance_km": round(distance_km, 1),
            "distance_miles": round(distance_km * 0.621371, 1),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/location/{person}")
async def location_lookup(person: str = "abby"):
    """Get a family member's real-time location and distance from home.

    Uses Google Maps location sharing (via cookies) + Distance Matrix API.
    Person: 'chris' or 'abby'.
    """
    from integrations.location import get_location, format_location_response
    result = await get_location(person.lower())
    return {
        "person": result.name,
        "latitude": result.latitude,
        "longitude": result.longitude,
        "address": result.address,
        "battery_level": result.battery_level,
        "charging": result.charging,
        "location_age_seconds": result.location_age_seconds,
        "distance_km": result.distance_km,
        "distance_miles": result.distance_miles,
        "duration_text": result.duration_text,
        "duration_seconds": result.duration_seconds,
        "formatted": format_location_response(result),
        "error": result.error,
    }


# ============================================================
# BATCH 10: Utilities - Currency, Units, Calculate, Color, Encode
# ============================================================

@app.get("/currency")
async def currency(
    amount: float = Query(..., description="Amount to convert"),
    from_currency: str = Query(..., description="From currency code (e.g., USD)"),
    to_currency: str = Query(..., description="To currency code (e.g., GBP)")
):
    """Convert currency."""
    import httpx

    try:
        # Using exchangerate-api (free tier)
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.exchangerate-api.com/v4/latest/{from_currency.upper()}",
                timeout=30
            )
            data = response.json()

        if "rates" not in data:
            return {"error": "Currency conversion failed"}

        rate = data["rates"].get(to_currency.upper())
        if not rate:
            return {"error": f"Unknown currency: {to_currency}"}

        converted = amount * rate

        return {
            "amount": amount,
            "from": from_currency.upper(),
            "to": to_currency.upper(),
            "rate": round(rate, 4),
            "result": round(converted, 2),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/units")
async def units(
    value: float = Query(..., description="Value to convert"),
    from_unit: str = Query(..., description="From unit"),
    to_unit: str = Query(..., description="To unit")
):
    """Convert units."""
    conversions = {
        # Length
        ("km", "miles"): lambda x: x * 0.621371,
        ("miles", "km"): lambda x: x * 1.60934,
        ("m", "ft"): lambda x: x * 3.28084,
        ("ft", "m"): lambda x: x * 0.3048,
        ("cm", "in"): lambda x: x * 0.393701,
        ("in", "cm"): lambda x: x * 2.54,
        # Weight
        ("kg", "lb"): lambda x: x * 2.20462,
        ("lb", "kg"): lambda x: x * 0.453592,
        ("g", "oz"): lambda x: x * 0.035274,
        ("oz", "g"): lambda x: x * 28.3495,
        # Temperature
        ("c", "f"): lambda x: (x * 9/5) + 32,
        ("f", "c"): lambda x: (x - 32) * 5/9,
        # Volume
        ("l", "gal"): lambda x: x * 0.264172,
        ("gal", "l"): lambda x: x * 3.78541,
        ("ml", "floz"): lambda x: x * 0.033814,
        ("floz", "ml"): lambda x: x * 29.5735,
    }

    key = (from_unit.lower(), to_unit.lower())
    if key not in conversions:
        return {"error": f"Unknown conversion: {from_unit} to {to_unit}"}

    result = conversions[key](value)

    return {
        "value": value,
        "from_unit": from_unit,
        "to_unit": to_unit,
        "result": round(result, 4),
        "fetched_at": datetime.now(UK_TZ).isoformat()
    }


@app.get("/calculate")
async def calculate(expression: str = Query(..., description="Math expression")):
    """Evaluate a math expression."""
    import re

    try:
        # Sanitize - only allow numbers, operators, parentheses, and some functions
        safe_expr = expression.replace('^', '**')  # Support ^ for power

        # Only allow safe characters
        if not re.match(r'^[\d\s\+\-\*\/\(\)\.\%\*]+$', safe_expr):
            # Check for allowed function names
            allowed = ['sqrt', 'sin', 'cos', 'tan', 'log', 'abs', 'round', 'pi']
            test_expr = safe_expr
            for func in allowed:
                test_expr = test_expr.replace(func, '')
            if not re.match(r'^[\d\s\+\-\*\/\(\)\.\%\*]+$', test_expr):
                return {"error": "Invalid expression"}

        import math
        # Create safe namespace
        safe_dict = {
            'sqrt': math.sqrt, 'sin': math.sin, 'cos': math.cos,
            'tan': math.tan, 'log': math.log, 'abs': abs,
            'round': round, 'pi': math.pi
        }
        result = eval(safe_expr, {"__builtins__": {}}, safe_dict)

        return {
            "expression": expression,
            "result": result,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except Exception as e:
        return {"error": f"Calculation error: {str(e)}"}


@app.get("/color")
async def color(value: str = Query(..., description="Color value (hex, rgb, or name)")):
    """Convert color between formats."""
    import re

    try:
        # Common color names
        names = {
            "red": (255, 0, 0), "green": (0, 128, 0), "blue": (0, 0, 255),
            "white": (255, 255, 255), "black": (0, 0, 0), "yellow": (255, 255, 0),
            "orange": (255, 165, 0), "purple": (128, 0, 128), "pink": (255, 192, 203),
            "gray": (128, 128, 128), "grey": (128, 128, 128)
        }

        r, g, b = 0, 0, 0

        # Parse hex
        if value.startswith('#'):
            hex_val = value[1:]
            if len(hex_val) == 3:
                hex_val = ''.join([c*2 for c in hex_val])
            r, g, b = int(hex_val[0:2], 16), int(hex_val[2:4], 16), int(hex_val[4:6], 16)

        # Parse rgb(r,g,b)
        elif value.lower().startswith('rgb'):
            match = re.search(r'(\d+)\s*,\s*(\d+)\s*,\s*(\d+)', value)
            if match:
                r, g, b = int(match.group(1)), int(match.group(2)), int(match.group(3))

        # Parse name
        elif value.lower() in names:
            r, g, b = names[value.lower()]
        else:
            return {"error": f"Unknown color format: {value}"}

        hex_color = f"#{r:02x}{g:02x}{b:02x}"

        return {
            "input": value,
            "hex": hex_color,
            "rgb": f"rgb({r}, {g}, {b})",
            "r": r, "g": g, "b": b,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except Exception as e:
        return {"error": f"Color parse error: {str(e)}"}


@app.get("/encode")
async def encode(
    text: str = Query(..., description="Text to encode/decode"),
    action: str = Query(default="encode", description="encode or decode"),
    format: str = Query(default="base64", description="base64 or url")
):
    """Encode or decode text."""
    import base64
    import urllib.parse

    try:
        if format == "base64":
            if action == "encode":
                result = base64.b64encode(text.encode()).decode()
            else:
                result = base64.b64decode(text.encode()).decode()
        elif format == "url":
            if action == "encode":
                result = urllib.parse.quote(text)
            else:
                result = urllib.parse.unquote(text)
        else:
            return {"error": f"Unknown format: {format}"}

        return {
            "input": text,
            "action": action,
            "format": format,
            "result": result,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except Exception as e:
        return {"error": f"Encode error: {str(e)}"}


# ============================================================
# BATCH 11: Generators - QRCode, Shorten, UUID, Random, Password
# ============================================================

@app.get("/qrcode")
async def qrcode(
    data: str = Query(..., description="Data to encode in QR code"),
    size: int = Query(default=200, description="Image size in pixels")
):
    """Generate a QR code image URL."""
    import urllib.parse

    # Using Google Charts API for QR codes
    encoded_data = urllib.parse.quote(data)
    url = f"https://chart.googleapis.com/chart?cht=qr&chs={size}x{size}&chl={encoded_data}"

    return {
        "data": data,
        "size": size,
        "qr_url": url,
        "fetched_at": datetime.now(UK_TZ).isoformat()
    }


@app.get("/shorten")
async def shorten(url: str = Query(..., description="URL to shorten")):
    """Shorten a URL using TinyURL."""
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://tinyurl.com/api-create.php?url={url}",
                timeout=30
            )
            short_url = response.text

        return {
            "original": url,
            "short": short_url,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/uuid")
async def uuid_generate(count: int = Query(default=1, le=10)):
    """Generate UUID(s)."""
    import uuid as uuid_lib

    uuids = [str(uuid_lib.uuid4()) for _ in range(count)]

    return {
        "count": count,
        "uuids": uuids if count > 1 else uuids[0],
        "fetched_at": datetime.now(UK_TZ).isoformat()
    }


@app.get("/random")
async def random_gen(
    min: int = Query(default=1, description="Minimum value"),
    max: int = Query(default=100, description="Maximum value"),
    count: int = Query(default=1, le=100, description="Number of values")
):
    """Generate random numbers."""
    import random

    numbers = [random.randint(min, max) for _ in range(count)]

    return {
        "min": min,
        "max": max,
        "count": count,
        "numbers": numbers if count > 1 else numbers[0],
        "fetched_at": datetime.now(UK_TZ).isoformat()
    }


@app.get("/password")
async def password_gen(
    length: int = Query(default=16, le=64, description="Password length"),
    include_symbols: bool = Query(default=True, description="Include symbols")
):
    """Generate a secure password."""
    import random
    import string

    chars = string.ascii_letters + string.digits
    if include_symbols:
        chars += "!@#$%^&*()_+-=[]{}|;:,.<>?"

    password = ''.join(random.choice(chars) for _ in range(length))

    return {
        "length": length,
        "includes_symbols": include_symbols,
        "password": password,
        "fetched_at": datetime.now(UK_TZ).isoformat()
    }


# ============================================================
# BATCH 12: Date/Time - Countdown, Age, Holidays, Sunrise, Moon
# ============================================================

@app.get("/countdown")
async def countdown(date: str = Query(..., description="Target date (YYYY-MM-DD) or event name")):
    """Calculate days until a date."""

    # Common events
    events = {
        "christmas": f"{datetime.now().year}-12-25",
        "new year": f"{datetime.now().year + 1}-01-01",
        "halloween": f"{datetime.now().year}-10-31",
        "easter": None,  # Complex calculation
    }

    target_str = events.get(date.lower(), date)
    if not target_str:
        return {"error": f"Cannot calculate date for: {date}"}

    try:
        target = datetime.strptime(target_str, "%Y-%m-%d").replace(tzinfo=UK_TZ)
        now = datetime.now(UK_TZ)

        # If date is in past this year, use next year
        if target < now and date.lower() in events:
            target = target.replace(year=target.year + 1)

        delta = target - now
        days = delta.days

        return {
            "target": target_str,
            "days_until": days,
            "weeks_until": round(days / 7, 1),
            "is_past": days < 0,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except ValueError:
        return {"error": f"Invalid date format: {date}"}


@app.get("/age")
async def age(birthdate: str = Query(..., description="Birthdate (YYYY-MM-DD)")):
    """Calculate age from birthdate."""

    try:
        birth = datetime.strptime(birthdate, "%Y-%m-%d")
        today = datetime.now()

        age_years = today.year - birth.year
        if (today.month, today.day) < (birth.month, birth.day):
            age_years -= 1

        # Days until next birthday
        next_birthday = birth.replace(year=today.year)
        if next_birthday < today:
            next_birthday = next_birthday.replace(year=today.year + 1)
        days_until = (next_birthday - today).days

        return {
            "birthdate": birthdate,
            "age_years": age_years,
            "days_until_birthday": days_until,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except ValueError:
        return {"error": f"Invalid date format: {birthdate}"}


@app.get("/holidays")
async def holidays(year: Optional[int] = Query(default=None, description="Year (default: current)")):
    """Get UK bank holidays."""
    import httpx

    if not year:
        year = datetime.now().year

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://www.gov.uk/bank-holidays.json",
                timeout=30
            )
            data = response.json()

        # Get England and Wales holidays
        holidays_list = data.get("england-and-wales", {}).get("events", [])

        # Filter by year and future only
        now = datetime.now().date()
        filtered = []
        for h in holidays_list:
            h_date = datetime.strptime(h['date'], "%Y-%m-%d").date()
            if h_date.year == year:
                filtered.append({
                    "name": h['title'],
                    "date": h['date'],
                    "is_future": h_date >= now
                })

        # Find next holiday
        next_holiday = None
        for h in holidays_list:
            h_date = datetime.strptime(h['date'], "%Y-%m-%d").date()
            if h_date >= now:
                next_holiday = {"name": h['title'], "date": h['date'], "days_until": (h_date - now).days}
                break

        return {
            "year": year,
            "holidays": filtered,
            "next_holiday": next_holiday,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sunrise")
async def sunrise(
    location: Optional[str] = Query(default=None, description="Location (default: home)")
):
    """Get sunrise and sunset times."""
    import httpx
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")

    if not location:
        location = os.getenv("HOME_ADDRESS", "London, UK")

    try:
        # Geocode location
        lat, lng = 51.5074, -0.1278  # Default London

        if api_key:
            async with httpx.AsyncClient() as client:
                geo_response = await client.get(
                    "https://maps.googleapis.com/maps/api/geocode/json",
                    params={"address": location, "key": api_key}
                )
                geo_data = geo_response.json()

            if geo_data.get("status") == "OK" and geo_data.get("results"):
                loc = geo_data["results"][0]["geometry"]["location"]
                lat, lng = loc["lat"], loc["lng"]

        # Get sunrise/sunset from sunrise-sunset.org API
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.sunrise-sunset.org/json?lat={lat}&lng={lng}&formatted=0",
                timeout=30
            )
            data = response.json()

        if data.get("status") != "OK":
            return {"error": "Could not get sunrise/sunset data"}

        results = data["results"]

        # Parse and convert to local time
        def to_local(iso_str):
            dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
            return dt.astimezone(UK_TZ).strftime("%H:%M")

        return {
            "location": location,
            "sunrise": to_local(results["sunrise"]),
            "sunset": to_local(results["sunset"]),
            "solar_noon": to_local(results["solar_noon"]),
            "day_length_hours": round(results["day_length"] / 3600, 1),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/moon")
async def moon():
    """Get current moon phase."""
    import math

    # Calculate moon phase using simple algorithm
    now = datetime.now()

    # Days since known new moon (Jan 6, 2000)
    known_new_moon = datetime(2000, 1, 6, 18, 14)
    days_since = (now - known_new_moon).total_seconds() / 86400

    # Synodic month is ~29.53 days
    synodic_month = 29.530588853
    phase = (days_since % synodic_month) / synodic_month

    # Phase names
    if phase < 0.03 or phase > 0.97:
        phase_name = "New Moon"
        emoji = "🌑"
    elif phase < 0.22:
        phase_name = "Waxing Crescent"
        emoji = "🌒"
    elif phase < 0.28:
        phase_name = "First Quarter"
        emoji = "🌓"
    elif phase < 0.47:
        phase_name = "Waxing Gibbous"
        emoji = "🌔"
    elif phase < 0.53:
        phase_name = "Full Moon"
        emoji = "🌕"
    elif phase < 0.72:
        phase_name = "Waning Gibbous"
        emoji = "🌖"
    elif phase < 0.78:
        phase_name = "Last Quarter"
        emoji = "🌗"
    else:
        phase_name = "Waning Crescent"
        emoji = "🌘"

    # Illumination percentage
    illumination = round((1 - math.cos(2 * math.pi * phase)) / 2 * 100, 1)

    return {
        "phase": phase_name,
        "emoji": emoji,
        "illumination_percent": illumination,
        "days_into_cycle": round(phase * synodic_month, 1),
        "fetched_at": datetime.now(UK_TZ).isoformat()
    }


# ============================================================
# BATCH 13: Network - IP, DNS, WHOIS, Ping
# ============================================================

@app.get("/ip")
async def ip_info(ip: Optional[str] = Query(default=None, description="IP address (default: your IP)")):
    """Get IP address information."""
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            if ip:
                response = await client.get(f"http://ip-api.com/json/{ip}", timeout=30)
            else:
                response = await client.get("http://ip-api.com/json/", timeout=30)
            data = response.json()

        if data.get("status") == "fail":
            return {"error": data.get("message", "IP lookup failed")}

        return {
            "ip": data.get("query"),
            "city": data.get("city"),
            "region": data.get("regionName"),
            "country": data.get("country"),
            "isp": data.get("isp"),
            "timezone": data.get("timezone"),
            "lat": data.get("lat"),
            "lon": data.get("lon"),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dns")
async def dns_lookup(domain: str = Query(..., description="Domain to lookup")):
    """DNS lookup for a domain."""
    import socket

    try:
        # Get various DNS records
        results = {}

        # A record (IPv4)
        try:
            a_records = socket.gethostbyname_ex(domain)
            results["a_records"] = a_records[2]
        except Exception:
            results["a_records"] = []

        # Get hostname
        try:
            results["hostname"] = socket.getfqdn(domain)
        except Exception:
            results["hostname"] = domain

        return {
            "domain": domain,
            "a_records": results.get("a_records", []),
            "hostname": results.get("hostname", ""),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/whois")
async def whois_lookup(domain: str = Query(..., description="Domain to lookup")):
    """WHOIS lookup for a domain."""
    import httpx

    try:
        # Using a WHOIS API
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://whois.freeaiapi.xyz/?name={domain}",
                timeout=30
            )

        if response.status_code != 200:
            return {"error": "WHOIS lookup failed", "domain": domain}

        data = response.json()

        return {
            "domain": domain,
            "registrar": data.get("registrar", "Unknown"),
            "creation_date": data.get("creation_date"),
            "expiration_date": data.get("expiration_date"),
            "name_servers": data.get("name_servers", []),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except Exception as e:
        # Fallback response if API fails
        return {
            "domain": domain,
            "error": "WHOIS lookup unavailable",
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }


@app.get("/ping")
async def ping(url: str = Query(..., description="URL or domain to check")):
    """Check if a website is up."""
    import httpx
    import time

    # Clean URL
    if not url.startswith(('http://', 'https://')):
        url = f"https://{url}"

    try:
        start = time.time()
        async with httpx.AsyncClient() as client:
            response = await client.head(url, timeout=10, follow_redirects=True)
        elapsed = round((time.time() - start) * 1000)  # ms

        return {
            "url": url,
            "status": "up",
            "status_code": response.status_code,
            "response_time_ms": elapsed,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except httpx.TimeoutException:
        return {"url": url, "status": "timeout", "fetched_at": datetime.now(UK_TZ).isoformat()}
    except Exception as e:
        return {"url": url, "status": "down", "error": str(e), "fetched_at": datetime.now(UK_TZ).isoformat()}


# ============================================================
# BATCH 14: Knowledge - Wikipedia, Dictionary, Synonyms, Quote, Fact
# ============================================================

@app.get("/wikipedia")
async def wikipedia(query: str = Query(..., description="Search query")):
    """Get Wikipedia summary."""
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://en.wikipedia.org/api/rest_v1/page/summary/" + query.replace(" ", "_"),
                timeout=30
            )

        if response.status_code == 404:
            return {"error": f"No Wikipedia article found for: {query}"}

        data = response.json()

        return {
            "title": data.get("title", ""),
            "summary": data.get("extract", "")[:1000],
            "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
            "thumbnail": data.get("thumbnail", {}).get("source", ""),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dictionary")
async def dictionary(word: str = Query(..., description="Word to define")):
    """Get word definition."""
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}",
                timeout=30
            )

        if response.status_code == 404:
            return {"error": f"Word not found: {word}"}

        data = response.json()
        if not data:
            return {"error": f"No definition found for: {word}"}

        entry = data[0]
        meanings = []

        for meaning in entry.get("meanings", [])[:3]:
            defs = []
            for d in meaning.get("definitions", [])[:2]:
                defs.append({
                    "definition": d.get("definition", ""),
                    "example": d.get("example", "")
                })
            meanings.append({
                "part_of_speech": meaning.get("partOfSpeech", ""),
                "definitions": defs
            })

        phonetics = entry.get("phonetics", [])
        pronunciation = ""
        audio = ""
        for p in phonetics:
            if p.get("text"):
                pronunciation = p["text"]
            if p.get("audio"):
                audio = p["audio"]

        return {
            "word": word,
            "pronunciation": pronunciation,
            "audio": audio,
            "meanings": meanings,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/synonyms")
async def synonyms(word: str = Query(..., description="Word to find synonyms for")):
    """Get synonyms and antonyms."""
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}",
                timeout=30
            )

        if response.status_code == 404:
            return {"error": f"Word not found: {word}"}

        data = response.json()
        if not data:
            return {"error": f"No data found for: {word}"}

        entry = data[0]
        all_synonyms = set()
        all_antonyms = set()

        for meaning in entry.get("meanings", []):
            all_synonyms.update(meaning.get("synonyms", []))
            all_antonyms.update(meaning.get("antonyms", []))
            for d in meaning.get("definitions", []):
                all_synonyms.update(d.get("synonyms", []))
                all_antonyms.update(d.get("antonyms", []))

        return {
            "word": word,
            "synonyms": list(all_synonyms)[:10],
            "antonyms": list(all_antonyms)[:10],
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/quote")
async def quote(category: Optional[str] = Query(default=None, description="Category: inspire, funny, life")):
    """Get a random quote."""
    import httpx
    import random

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://zenquotes.io/api/random",
                timeout=30
            )
            data = response.json()

        if data and len(data) > 0:
            q = data[0]
            return {
                "quote": q.get("q", ""),
                "author": q.get("a", "Unknown"),
                "fetched_at": datetime.now(UK_TZ).isoformat()
            }

        return {"error": "Could not fetch quote"}

    except Exception as e:
        # Fallback quotes
        fallback = [
            {"q": "The only way to do great work is to love what you do.", "a": "Steve Jobs"},
            {"q": "Innovation distinguishes between a leader and a follower.", "a": "Steve Jobs"},
            {"q": "Stay hungry, stay foolish.", "a": "Steve Jobs"},
        ]
        q = random.choice(fallback)
        return {"quote": q["q"], "author": q["a"], "fetched_at": datetime.now(UK_TZ).isoformat()}


@app.get("/fact")
async def fact():
    """Get a random fact."""
    import httpx
    import random

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://uselessfacts.jsph.pl/api/v2/facts/random",
                timeout=30
            )
            data = response.json()

        return {
            "fact": data.get("text", ""),
            "source": data.get("source", ""),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except Exception as e:
        # Fallback facts
        facts = [
            "Honey never spoils. Archaeologists have found 3000-year-old honey in Egyptian tombs that was still edible.",
            "Octopuses have three hearts and blue blood.",
            "A group of flamingos is called a 'flamboyance'.",
        ]
        return {"fact": random.choice(facts), "fetched_at": datetime.now(UK_TZ).isoformat()}


# ============================================================
# Nutrition Endpoints
# ============================================================

@app.post("/nutrition/log-meal")
async def nutrition_log_meal(
    meal_type: str = Query(..., description="breakfast, lunch, dinner, or snack", regex="^(breakfast|lunch|dinner|snack)$"),
    description: str = Query(..., description="What was eaten"),
    calories: float = Query(..., description="Calories"),
    protein_g: float = Query(..., description="Protein in grams"),
    carbs_g: float = Query(..., description="Carbs in grams"),
    fat_g: float = Query(..., description="Fat in grams")
):
    """Log a meal with macro breakdown. Returns today's totals for context."""
    from domains.nutrition.services.supabase_service import insert_meal, get_today_totals
    from domains.nutrition.services.goals_service import get_goals

    try:
        # Get totals and goals BEFORE insert to avoid race condition
        prev_totals, goals = await asyncio.gather(
            get_today_totals(),
            get_goals()
        )
        targets = goals.get("daily_targets", {})

        # Insert the meal
        result = await insert_meal(meal_type, description, calories, protein_g, carbs_g, fat_g)

        # Calculate new totals (previous + just logged) - avoids race condition
        new_totals = {
            "calories": prev_totals.get("calories", 0) + calories,
            "protein_g": prev_totals.get("protein_g", 0) + protein_g,
            "carbs_g": prev_totals.get("carbs_g", 0) + carbs_g,
            "fat_g": prev_totals.get("fat_g", 0) + fat_g,
        }

        return {
            **result,
            "meal_type": meal_type,
            "description": description,
            "calories": calories,
            "protein_g": protein_g,
            "carbs_g": carbs_g,
            "fat_g": fat_g,
            "logged_at": datetime.now(UK_TZ).isoformat(),
            "today_totals": new_totals,
            "daily_targets": {
                "calories": targets.get("calories", 2000),
                "protein_g": targets.get("protein_g", 150),
                "carbs_g": targets.get("carbs_g", 200),
                "fat_g": targets.get("fat_g", 65),
            },
            "remaining": {
                "calories": max(0, targets.get("calories", 2000) - new_totals["calories"]),
                "protein_g": max(0, targets.get("protein_g", 150) - new_totals["protein_g"]),
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/nutrition/log-water")
async def nutrition_log_water(
    ml: float = Query(..., description="Water amount in millilitres")
):
    """Log water intake. Returns running total and target for context."""
    from domains.nutrition.services.supabase_service import insert_water, get_today_totals
    from domains.nutrition.services.goals_service import get_goals

    try:
        # Get totals and goals BEFORE insert to avoid race condition
        totals, goals = await asyncio.gather(
            get_today_totals(),
            get_goals()
        )
        previous_water = totals.get("water_ml", 0)
        water_goal = goals.get("daily_targets", {}).get("water_ml", 2500)

        # Insert the water
        result = await insert_water(ml)

        # Calculate new total (previous + just logged) - avoids race condition
        water_total = previous_water + ml
        remaining = max(0, water_goal - water_total)

        return {
            **result,
            "ml_logged": ml,
            "logged_at": datetime.now(UK_TZ).isoformat(),
            "today_total_ml": water_total,
            "goal_ml": water_goal,
            "remaining_ml": remaining,
            "progress_pct": round((water_total / water_goal) * 100, 1) if water_goal > 0 else 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/nutrition/meal")
async def nutrition_delete_meal(
    meal_id: str = Query(..., description="UUID of the meal to delete")
):
    """Delete a nutrition log entry by ID."""
    from domains.nutrition.services.supabase_service import delete_meal

    try:
        result = await delete_meal(meal_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/nutrition/water/entries")
async def nutrition_water_entries():
    """Get today's water entries with IDs (for viewing/deleting individual entries)."""
    from domains.nutrition.services.supabase_service import get_today_water_entries

    try:
        entries = await get_today_water_entries()
        total_ml = sum(e.get("water_ml", 0) for e in entries)
        return {
            "count": len(entries),
            "total_ml": total_ml,
            "entries": entries,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/nutrition/water")
async def nutrition_delete_water(
    entry_id: str = Query(..., description="UUID of the water entry to delete")
):
    """Delete a single water entry by ID."""
    from domains.nutrition.services.supabase_service import delete_meal

    try:
        result = await delete_meal(entry_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/nutrition/water/reset")
async def nutrition_water_reset():
    """Delete ALL water entries for today (bulk reset). Use with care."""
    from domains.nutrition.services.supabase_service import delete_today_water

    try:
        result = await delete_today_water()
        return {
            **result,
            "reset_at": datetime.now(UK_TZ).isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/nutrition/date")
async def nutrition_by_date(
    date: str = Query(..., description="Date in YYYY-MM-DD format", regex=r"^\d{4}-\d{2}-\d{2}$")
):
    """Get nutrition totals for a specific date."""
    from domains.nutrition.services.supabase_service import get_nutrition_totals
    from domains.nutrition.services.goals_service import get_goals

    try:
        totals, goals = await asyncio.gather(
            get_nutrition_totals(date),
            get_goals()
        )
        targets = goals.get("daily_targets", {})
        progress = {}
        if targets:
            for key in ["calories", "protein_g", "carbs_g", "fat_g", "water_ml"]:
                target = targets.get(key, 0)
                if target:
                    progress[key] = round((totals.get(key, 0) / target) * 100)

        return {
            "date": date,
            "totals": totals,
            "targets": targets,
            "progress": progress,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/nutrition/date/meals")
async def nutrition_date_meals(
    date: str = Query(..., description="Date in YYYY-MM-DD format", regex=r"^\d{4}-\d{2}-\d{2}$")
):
    """Get list of meals logged on a specific date."""
    from domains.nutrition.services.supabase_service import get_meals_by_date

    try:
        meals = await get_meals_by_date(date)
        return {
            "date": date,
            "count": len(meals),
            "meals": meals,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/nutrition/today")
async def nutrition_today():
    """Get today's nutrition totals and progress vs targets."""
    from domains.nutrition.services.supabase_service import get_today_totals
    from domains.nutrition.services.goals_service import get_goals

    try:
        totals = await get_today_totals()
        goals = await get_goals()

        # Calculate progress percentages
        targets = goals.get("daily_targets", {})
        progress = {}
        if targets:
            for key in ["calories", "protein_g", "carbs_g", "fat_g", "water_ml"]:
                target_key = key if key != "water_ml" else "water_ml"
                target = targets.get(target_key, targets.get(key.replace("_g", ""), 0))
                if target:
                    progress[key] = round((totals.get(key, 0) / target) * 100)

        return {
            "totals": totals,
            "targets": targets,
            "progress": progress,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/nutrition/today/meals")
async def nutrition_today_meals():
    """Get list of meals logged today."""
    from domains.nutrition.services.supabase_service import get_today_meals

    try:
        meals = await get_today_meals()
        return {
            "count": len(meals),
            "meals": meals,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/nutrition/week")
async def nutrition_week():
    """Get last 7 days of nutrition summary."""
    from domains.nutrition.services.supabase_service import get_week_summary

    try:
        summary = await get_week_summary()
        return {
            "days": summary,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/nutrition/goals")
async def nutrition_goals():
    """Get current nutrition and fitness goals."""
    from domains.nutrition.services.goals_service import get_goals

    try:
        goals = await get_goals()
        return {
            **goals,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/nutrition/goals")
async def nutrition_update_goals(
    target_weight_kg: Optional[float] = Query(default=None),
    deadline: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    goal_reason: Optional[str] = Query(default=None),
    calories_target: Optional[int] = Query(default=None),
    protein_target_g: Optional[int] = Query(default=None),
    carbs_target_g: Optional[int] = Query(default=None),
    fat_target_g: Optional[int] = Query(default=None),
    water_target_ml: Optional[int] = Query(default=None),
    steps_target: Optional[int] = Query(default=None)
):
    """Update nutrition/fitness goals. Only provided fields are updated."""
    from domains.nutrition.services.goals_service import update_goal

    try:
        result = await update_goal(
            target_weight_kg=target_weight_kg,
            deadline=deadline,
            goal_reason=goal_reason,
            calories_target=calories_target,
            protein_target_g=protein_target_g,
            carbs_target_g=carbs_target_g,
            fat_target_g=fat_target_g,
            water_target_ml=water_target_ml,
            steps_target=steps_target
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/nutrition/steps")
async def nutrition_steps(
    date: str = Query(default=None, description="Date in YYYY-MM-DD format (default: today)")
):
    """Get step count from Garmin for a given date."""
    from domains.nutrition.services.garmin import get_steps

    try:
        result = await get_steps(date_str=date)
        return {
            **result,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/nutrition/weight")
async def nutrition_weight():
    """Get latest weight from Withings."""
    from domains.nutrition.services.withings import get_weight

    try:
        result = await get_weight()
        return {
            **result,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/nutrition/weight/history")
async def nutrition_weight_history(
    days: int = Query(default=30, le=365, description="Number of days of history")
):
    """Get weight history for trend analysis."""
    from domains.nutrition.services.withings import get_weight_history

    try:
        readings = await get_weight_history(days)
        return {
            "days": days,
            "count": len(readings),
            "readings": readings,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/withings/status")
async def withings_status():
    """Check Withings token status and provide re-auth instructions."""
    from domains.nutrition.services.withings import _tokens, TOKEN_FILE
    has_tokens = bool(_tokens.get("access"))
    file_exists = TOKEN_FILE.exists()

    # Quick test
    result = {}
    if has_tokens:
        from domains.nutrition.services.withings import get_weight
        result = await get_weight(retry=True)

    return {
        "has_tokens": has_tokens,
        "token_file_exists": file_exists,
        "token_file_path": str(TOKEN_FILE),
        "test_result": result,
        "reauth_command": "python scripts/withings_auth.py"
    }


@app.get("/nutrition/favourites")
async def nutrition_favourites():
    """List all saved meal favourites."""
    from domains.nutrition.services.favourites_service import list_favourites

    try:
        favourites = await list_favourites()
        return {
            "count": len(favourites),
            "favourites": favourites,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/nutrition/favourite")
async def nutrition_get_favourite(
    name: str = Query(..., description="Name of the favourite to retrieve")
):
    """Get a favourite meal by name."""
    from domains.nutrition.services.favourites_service import get_favourite

    try:
        result = await get_favourite(name)
        if result:
            return {
                **result,
                "fetched_at": datetime.now(UK_TZ).isoformat()
            }
        raise HTTPException(status_code=404, detail=f"Favourite '{name}' not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/nutrition/favourite")
async def nutrition_save_favourite(
    name: str = Query(..., description="Name for the favourite"),
    description: str = Query(..., description="What the meal contains"),
    calories: float = Query(...),
    protein_g: float = Query(...),
    carbs_g: float = Query(...),
    fat_g: float = Query(...),
    meal_type: Optional[str] = Query(default=None, description="breakfast, lunch, dinner, or snack")
):
    """Save a meal as a favourite for quick logging later."""
    from domains.nutrition.services.favourites_service import save_favourite

    try:
        result = await save_favourite(name, description, calories, protein_g, carbs_g, fat_g, meal_type)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/nutrition/favourite")
async def nutrition_delete_favourite(
    name: str = Query(..., description="Name of the favourite to delete")
):
    """Delete a saved favourite."""
    from domains.nutrition.services.favourites_service import delete_favourite

    try:
        result = await delete_favourite(name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Second Brain (Knowledge Base) Endpoints
# ============================================================

@app.get("/brain/search")
async def brain_search(
    query: str = Query(..., description="Search query"),
    limit: int = Query(default=5, le=20),
    min_similarity: float = Query(default=0.75, ge=0.0, le=1.0),
):
    """Semantic search across Second Brain knowledge base."""
    from domains.second_brain import hybrid_search

    try:
        results = await hybrid_search(
            query=query,
            limit=limit,
            min_similarity=min_similarity,
        )
        return {
            "query": query,
            "count": len(results),
            "results": [
                {
                    "id": r.item.id,
                    "title": r.item.title,
                    "summary": r.item.summary,
                    "source": r.item.source,
                    "topics": r.item.topics,
                    "similarity": round(r.best_similarity, 3),
                    "weighted_score": round(r.weighted_score, 3),
                    "excerpts": r.relevant_excerpts[:3],
                    "content_type": r.item.content_type.value,
                    "created_at": str(r.item.created_at) if r.item.created_at else None,
                }
                for r in results
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class BrainSaveRequest(BaseModel):
    source: str
    note: Optional[str] = None
    tags: Optional[str] = None


@app.post("/brain/save")
async def brain_save(body: BrainSaveRequest):
    """Save content to Second Brain."""
    from domains.second_brain import process_capture
    from domains.second_brain.types import CaptureType

    try:
        user_tags = [t.strip() for t in body.tags.split(",")] if body.tags else None
        item = await process_capture(
            source=body.source,
            capture_type=CaptureType.EXPLICIT,
            user_note=body.note,
            user_tags=user_tags,
            source_system="api:hadley-api",
        )
        if not item:
            raise HTTPException(status_code=422, detail="Failed to process content")
        return {
            "success": True,
            "id": item.id,
            "title": item.title,
            "summary": item.summary,
            "topics": item.topics,
            "word_count": item.word_count,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/brain/stats")
async def brain_stats():
    """Get Second Brain statistics."""
    from domains.second_brain import get_total_active_count, get_topics_with_counts, get_recent_items

    try:
        total = await get_total_active_count()
        topics = await get_topics_with_counts()
        recent = await get_recent_items(limit=5)
        return {
            "total_items": total,
            "topics": [{"topic": t, "count": c} for t, c in topics[:20]],
            "recent": [
                {
                    "id": r.id,
                    "title": r.title,
                    "content_type": r.content_type.value,
                    "created_at": str(r.created_at) if r.created_at else None,
                }
                for r in recent
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Schedule Management
# ============================================================

SCHEDULE_PATH = Path(__file__).parent.parent / "domains" / "peterbot" / "wsl_config" / "SCHEDULE.md"
SCHEDULE_RELOAD_TRIGGER = Path(__file__).parent.parent / "data" / "schedule_reload.trigger"


@app.get("/schedule")
async def get_schedule():
    """Read current SCHEDULE.md content."""
    if not SCHEDULE_PATH.exists():
        raise HTTPException(status_code=404, detail="SCHEDULE.md not found")
    content = SCHEDULE_PATH.read_text(encoding="utf-8")
    return {"content": content, "path": str(SCHEDULE_PATH)}


class ScheduleUpdate(BaseModel):
    content: str
    reason: str = ""


@app.put("/schedule")
async def update_schedule(body: ScheduleUpdate):
    """Update SCHEDULE.md content and trigger reload.

    Peter calls this after getting explicit user approval.
    Creates a backup before writing.
    """
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    # Validate it looks like a valid SCHEDULE.md (has the table header)
    if "| Job |" not in body.content or "| Skill |" not in body.content:
        raise HTTPException(
            status_code=400,
            detail="Invalid SCHEDULE.md format — must contain job table with | Job | Skill | columns"
        )

    # Backup current version
    if SCHEDULE_PATH.exists():
        backup_path = SCHEDULE_PATH.with_suffix(f".md.bak")
        backup_path.write_text(SCHEDULE_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    # Write new content
    SCHEDULE_PATH.write_text(body.content, encoding="utf-8")

    # Trigger reload
    SCHEDULE_RELOAD_TRIGGER.parent.mkdir(parents=True, exist_ok=True)
    SCHEDULE_RELOAD_TRIGGER.write_text(
        f"{datetime.now(UK_TZ).isoformat()}|{body.reason}",
        encoding="utf-8"
    )

    return {
        "status": "updated",
        "message": "SCHEDULE.md updated and reload triggered",
        "reason": body.reason,
    }


@app.post("/schedule/reload")
async def reload_schedule():
    """Trigger a schedule reload without editing the file."""
    SCHEDULE_RELOAD_TRIGGER.parent.mkdir(parents=True, exist_ok=True)
    SCHEDULE_RELOAD_TRIGGER.write_text(
        f"{datetime.now(UK_TZ).isoformat()}|manual_reload",
        encoding="utf-8"
    )
    return {"status": "reload_triggered", "message": "Schedule reload will apply within 10 seconds"}


# ============================================================
# Reminders CRUD
# ============================================================

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")


def _supabase_headers():
    """Headers for Supabase REST API."""
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }


class ReminderCreate(BaseModel):
    task: str
    run_at: str  # ISO 8601 datetime string
    user_id: int
    channel_id: int


class ReminderUpdate(BaseModel):
    task: Optional[str] = None
    run_at: Optional[str] = None  # ISO 8601 datetime string


@app.get("/reminders")
async def list_reminders(user_id: int = Query(..., description="Discord user ID")):
    """List pending (unfired) reminders for a user, sorted by run_at."""
    import httpx

    if not SUPABASE_URL:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/reminders"
                f"?user_id=eq.{user_id}&fired_at=is.null&select=*&order=run_at",
                headers=_supabase_headers(),
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch reminders: {e}")


@app.post("/reminders")
async def create_reminder(body: ReminderCreate):
    """Create a new reminder. Validates time is in the future."""
    import httpx
    import uuid

    if not SUPABASE_URL:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    # Validate run_at is parseable and in the future
    try:
        from dateutil.parser import parse as parse_dt
        run_at = parse_dt(body.run_at)
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=UK_TZ)
        now = datetime.now(UK_TZ)
        if run_at <= now:
            raise HTTPException(status_code=400, detail=f"run_at must be in the future (got {run_at.isoformat()}, now is {now.isoformat()})")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid run_at format: {e}")

    if not body.task.strip():
        raise HTTPException(status_code=400, detail="task cannot be empty")

    reminder_id = f"remind_{uuid.uuid4().hex[:8]}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/reminders",
                headers=_supabase_headers(),
                json={
                    "id": reminder_id,
                    "user_id": body.user_id,
                    "channel_id": body.channel_id,
                    "task": body.task.strip(),
                    "run_at": run_at.isoformat(),
                },
            )
            resp.raise_for_status()
            created = resp.json()
            return created[0] if isinstance(created, list) and created else created
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create reminder: {e}")


@app.patch("/reminders/{reminder_id}")
async def update_reminder(reminder_id: str, body: ReminderUpdate):
    """Update task and/or run_at on a pending reminder."""
    import httpx

    if not SUPABASE_URL:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    updates = {}
    if body.task is not None:
        if not body.task.strip():
            raise HTTPException(status_code=400, detail="task cannot be empty")
        updates["task"] = body.task.strip()

    if body.run_at is not None:
        try:
            from dateutil.parser import parse as parse_dt
            run_at = parse_dt(body.run_at)
            if run_at.tzinfo is None:
                run_at = run_at.replace(tzinfo=UK_TZ)
            if run_at <= datetime.now(UK_TZ):
                raise HTTPException(status_code=400, detail="run_at must be in the future")
            updates["run_at"] = run_at.isoformat()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid run_at format: {e}")

    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update (provide task and/or run_at)")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.patch(
                f"{SUPABASE_URL}/rest/v1/reminders?id=eq.{reminder_id}&fired_at=is.null",
                headers=_supabase_headers(),
                json=updates,
            )
            resp.raise_for_status()
            result = resp.json()
            if not result:
                raise HTTPException(status_code=404, detail="Reminder not found or already fired")
            return result[0] if isinstance(result, list) and result else result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update reminder: {e}")


@app.delete("/reminders/{reminder_id}")
async def delete_reminder(reminder_id: str):
    """Cancel/delete a pending reminder."""
    import httpx

    if not SUPABASE_URL:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # First check it exists
            check = await client.get(
                f"{SUPABASE_URL}/rest/v1/reminders?id=eq.{reminder_id}&select=id",
                headers=_supabase_headers(),
            )
            check.raise_for_status()
            if not check.json():
                raise HTTPException(status_code=404, detail="Reminder not found")

            resp = await client.delete(
                f"{SUPABASE_URL}/rest/v1/reminders?id=eq.{reminder_id}",
                headers=_supabase_headers(),
            )
            resp.raise_for_status()
            return {"status": "deleted", "id": reminder_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete reminder: {e}")


# ============================================================
# Shopping List PDF Generator
# ============================================================

SHOPPING_LIST_DEFAULT_DIR = r"G:\My Drive\AI Work\Shopping Lists"


class ShoppingListRequest(BaseModel):
    categories: dict[str, list[str]]
    title: str = "Shopping List"
    output_dir: str | None = None


@app.post("/shopping-list/generate")
async def generate_shopping_list(req: ShoppingListRequest):
    """Generate a printable shopping list PDF."""
    import sys
    from datetime import datetime as dt

    # Import the generator
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from generate_shopping_list import generate_shopping_list_pdf

    out_dir = Path(req.output_dir) if req.output_dir else Path(SHOPPING_LIST_DEFAULT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.now().strftime("%Y%m%d_%H%M%S")
    filename = f"shopping_list_{timestamp}.pdf"
    output_path = out_dir / filename

    try:
        result = await asyncio.to_thread(
            generate_shopping_list_pdf, str(output_path), req.categories, req.title
        )
        return {
            "status": "created",
            "filename": filename,
            "path": str(result),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")


# ============================================================
# Meal Plan
# ============================================================

MEAL_PLAN_DEFAULT_SHEET = "11R7GRjGNA9oQkjWIXcDYrf_TEcebbu4pAff0R_xsVCo"


class MealPlanCSVImport(BaseModel):
    csv_data: str
    ingredients_csv: str | None = None


class MealPlanIngredientsUpdate(BaseModel):
    ingredients: list[dict]


@app.get("/meal-plan/current")
async def meal_plan_current():
    """Get the current week's meal plan with items and ingredients."""
    from domains.nutrition.services.meal_plan_service import get_current_meal_plan

    try:
        plan = await get_current_meal_plan()
        if not plan:
            return {"plan": None, "message": "No meal plan found for this week"}
        return {"plan": plan, "fetched_at": datetime.now(UK_TZ).isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/meal-plan/week")
async def meal_plan_by_week(date: str = Query(default=None, description="Any date within the week (YYYY-MM-DD), defaults to today")):
    """Get the meal plan for the week containing the given date."""
    from domains.nutrition.services.meal_plan_service import get_meal_plan, _monday_of

    try:
        if date is None:
            date = datetime.now(UK_TZ).date().isoformat()
        week_start = _monday_of(date)
        plan = await get_meal_plan(week_start)
        if not plan:
            return {"plan": None, "week_start": week_start, "message": "No meal plan found for this week"}
        return {"plan": plan, "week_start": week_start, "fetched_at": datetime.now(UK_TZ).isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/meal-plan/{plan_id}")
async def meal_plan_by_id(plan_id: str):
    """Get a meal plan by its ID."""
    from domains.nutrition.services.meal_plan_service import get_meal_plan_by_id

    try:
        plan = await get_meal_plan_by_id(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Meal plan not found")
        return {"plan": plan, "fetched_at": datetime.now(UK_TZ).isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/meal-plan/{plan_id}")
async def meal_plan_delete(plan_id: str):
    """Delete a meal plan and all its items/ingredients."""
    from domains.nutrition.services.meal_plan_service import delete_meal_plan

    try:
        result = await delete_meal_plan(plan_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/meal-plan/import/sheets")
async def meal_plan_import_sheets(
    spreadsheet_id: str = Query(default=MEAL_PLAN_DEFAULT_SHEET, description="Google Sheet ID")
):
    """Import a meal plan from a Google Sheet.

    Reads all tabs, parses meal plan data and optional ingredients tab.
    Expected columns: Date, Day, Adults, Kids, Activities (or similar).
    Ingredients tab: Category, Item, Quantity, Recipe (or similar).
    """
    from .google_auth import get_credentials
    from googleapiclient.discovery import build
    from domains.nutrition.services.meal_plan_service import (
        upsert_meal_plan, upsert_meal_plan_items, set_meal_plan_ingredients
    )
    import re

    try:
        creds = get_credentials()
        if not creds:
            raise HTTPException(status_code=503, detail="Google auth not configured")

        service = build('sheets', 'v4', credentials=creds)

        # Get sheet info
        spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = [s['properties']['title'] for s in spreadsheet.get('sheets', [])]

        # Read all tabs
        all_data = {}
        for sheet_name in sheets:
            result = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=f"'{sheet_name}'!A1:Z100"
            ).execute()
            all_data[sheet_name] = result.get('values', [])

        # Identify meal plan tab and ingredients tab
        meal_rows = None
        ingredient_rows = None
        meal_tab_name = None
        ingredient_tab_name = None

        for tab_name, rows in all_data.items():
            if not rows:
                continue
            header = [str(c).lower().strip() for c in rows[0]]
            if any(h in header for h in ['adults', 'adult', 'dinner', 'meal']):
                meal_rows = rows
                meal_tab_name = tab_name
            elif any(h in header for h in ['category', 'ingredient', 'aisle']):
                ingredient_rows = rows
                ingredient_tab_name = tab_name

        if not meal_rows:
            raise HTTPException(status_code=400, detail=f"No meal plan tab found. Tabs: {sheets}")

        # Parse meal plan tab
        header = [str(c).lower().strip() for c in meal_rows[0]]

        # Find column indices
        date_col = next((i for i, h in enumerate(header) if h in ('date', 'day', 'date/day')), None)
        adults_col = next((i for i, h in enumerate(header) if h in ('adults', 'adult', 'dinner', 'meal', 'adults meal')), None)
        kids_col = next((i for i, h in enumerate(header) if h in ('kids', 'kid', 'kids meal', 'children')), None)
        activities_col = next((i for i, h in enumerate(header) if h in ('activities', 'activity', 'notes')), None)

        if adults_col is None:
            raise HTTPException(status_code=400, detail=f"Could not find adults/meal column. Headers: {header}")

        # Parse rows into items
        items = []
        current_year = datetime.now().year
        last_date = None

        for row in meal_rows[1:]:
            # Pad row to header length
            row = row + [''] * (len(header) - len(row))

            date_str = row[date_col].strip() if date_col is not None else ''
            adults = row[adults_col].strip() if adults_col is not None else ''
            kids = row[kids_col].strip() if kids_col is not None else ''

            # Skip empty rows
            if not adults and not kids:
                continue

            # Parse date (DD/MM or DD/MM/YYYY format)
            if date_str:
                date_match = re.match(r'(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?', date_str)
                if date_match:
                    day = int(date_match.group(1))
                    month = int(date_match.group(2))
                    year = int(date_match.group(3)) if date_match.group(3) else current_year
                    if year < 100:
                        year += 2000
                    try:
                        parsed_date = datetime(year, month, day).date()
                        last_date = parsed_date
                    except ValueError:
                        if last_date:
                            parsed_date = last_date
                        else:
                            continue
                elif last_date:
                    parsed_date = last_date
                else:
                    continue
            elif last_date:
                parsed_date = last_date
            else:
                continue

            # Determine meal_slot (1 or 2 for same-date meals)
            existing_slots = [i['meal_slot'] for i in items if i['date'] == parsed_date.isoformat()]
            meal_slot = len(existing_slots) + 1

            # Detect source_tag from Activities column (or adults meal as fallback)
            source_tag = None
            activities = row[activities_col].strip().lower() if activities_col is not None and len(row) > activities_col else ''
            adults_lower = adults.lower()
            if 'gousto' in activities or 'gousto' in adults_lower:
                source_tag = 'gousto'
            elif 'out' in activities or 'chris out' in adults_lower:
                source_tag = 'chris_out'

            items.append({
                "date": parsed_date.isoformat(),
                "meal_slot": meal_slot,
                "adults_meal": adults or None,
                "kids_meal": kids or None,
                "source_tag": source_tag,
                "recipe_url": None
            })

        if not items:
            raise HTTPException(status_code=400, detail="No valid meal plan items found in sheet")

        # Determine week_start from earliest date
        earliest = min(i['date'] for i in items)
        from domains.nutrition.services.meal_plan_service import _monday_of
        week_start = _monday_of(earliest)

        # Upsert plan
        plan = await upsert_meal_plan(
            week_start=week_start,
            source="sheets",
            sheet_id=spreadsheet_id
        )

        # Upsert items
        upserted_items = await upsert_meal_plan_items(plan["id"], items)

        # Parse ingredients — check for separate tab first, then same-tab "List" column
        upserted_ingredients = []
        if ingredient_rows and len(ingredient_rows) > 1:
            ing_header = [str(c).lower().strip() for c in ingredient_rows[0]]
            cat_col = next((i for i, h in enumerate(ing_header) if h in ('category', 'aisle', 'section')), None)
            item_col = next((i for i, h in enumerate(ing_header) if h in ('item', 'ingredient', 'name')), None)
            qty_col = next((i for i, h in enumerate(ing_header) if h in ('quantity', 'qty', 'amount')), None)
            recipe_col = next((i for i, h in enumerate(ing_header) if h in ('recipe', 'for', 'for recipe', 'meal')), None)

            if item_col is not None:
                ingredients = []
                for row in ingredient_rows[1:]:
                    row = row + [''] * (len(ing_header) - len(row))
                    item_name = row[item_col].strip() if item_col is not None else ''
                    if not item_name:
                        continue
                    ingredients.append({
                        "category": row[cat_col].strip() if cat_col is not None and row[cat_col].strip() else "Other",
                        "item": item_name,
                        "quantity": row[qty_col].strip() if qty_col is not None else None,
                        "for_recipe": row[recipe_col].strip() if recipe_col is not None else None,
                    })

                if ingredients:
                    upserted_ingredients = await set_meal_plan_ingredients(plan["id"], ingredients)

        # Fallback: check for a "list" column on the same meal plan tab
        if not upserted_ingredients and meal_rows:
            from scripts.categorise_groceries import categorise_item

            list_col = next((i for i, h in enumerate(header) if h in ('list', 'shopping list', 'shopping', 'ingredients')), None)
            if list_col is not None:
                ingredients = []
                for row in meal_rows[1:]:
                    row = row + [''] * (len(header) - len(row))
                    item_name = row[list_col].strip() if list_col is not None else ''
                    if not item_name:
                        continue
                    ingredients.append({
                        "category": categorise_item(item_name),
                        "item": item_name,
                        "quantity": None,
                        "for_recipe": None,
                    })
                if ingredients:
                    upserted_ingredients = await set_meal_plan_ingredients(plan["id"], ingredients)

        return {
            "status": "imported",
            "plan_id": plan["id"],
            "week_start": week_start,
            "items_count": len(upserted_items),
            "ingredients_count": len(upserted_ingredients),
            "tabs_found": {
                "meal_plan": meal_tab_name,
                "ingredients": ingredient_tab_name
            },
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sheet import failed: {e}")


@app.post("/meal-plan/import/csv")
async def meal_plan_import_csv(req: MealPlanCSVImport):
    """Import a meal plan from CSV data.

    CSV format: Date,Day,Adults,Kids,Activities
    Optional ingredients_csv: Category,Item,Quantity,Recipe
    """
    import csv
    import io
    import re
    from domains.nutrition.services.meal_plan_service import (
        upsert_meal_plan, upsert_meal_plan_items, set_meal_plan_ingredients, _monday_of
    )

    try:
        # Parse meal CSV
        reader = csv.DictReader(io.StringIO(req.csv_data))
        items = []
        current_year = datetime.now().year
        last_date = None

        for row in reader:
            # Normalise column names
            normalised = {k.lower().strip(): v.strip() for k, v in row.items() if k}

            adults = normalised.get('adults', normalised.get('adult', normalised.get('meal', normalised.get('dinner', ''))))
            kids = normalised.get('kids', normalised.get('kid', normalised.get('children', '')))
            date_str = normalised.get('date', normalised.get('day', ''))

            if not adults and not kids:
                continue

            # Parse date
            if date_str:
                date_match = re.match(r'(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?', date_str)
                if date_match:
                    day = int(date_match.group(1))
                    month = int(date_match.group(2))
                    year = int(date_match.group(3)) if date_match.group(3) else current_year
                    if year < 100:
                        year += 2000
                    try:
                        parsed_date = datetime(year, month, day).date()
                        last_date = parsed_date
                    except ValueError:
                        if last_date:
                            parsed_date = last_date
                        else:
                            continue
                elif last_date:
                    parsed_date = last_date
                else:
                    continue
            elif last_date:
                parsed_date = last_date
            else:
                continue

            existing_slots = [i['meal_slot'] for i in items if i['date'] == parsed_date.isoformat()]
            meal_slot = len(existing_slots) + 1

            source_tag = None
            if 'gousto' in adults.lower():
                source_tag = 'gousto'
            elif 'chris out' in adults.lower() or 'out' == adults.lower():
                source_tag = 'chris_out'

            items.append({
                "date": parsed_date.isoformat(),
                "meal_slot": meal_slot,
                "adults_meal": adults or None,
                "kids_meal": kids or None,
                "source_tag": source_tag,
                "recipe_url": None
            })

        if not items:
            raise HTTPException(status_code=400, detail="No valid items found in CSV")

        earliest = min(i['date'] for i in items)
        week_start = _monday_of(earliest)

        plan = await upsert_meal_plan(week_start=week_start, source="csv")
        upserted_items = await upsert_meal_plan_items(plan["id"], items)

        # Parse ingredients CSV if provided
        upserted_ingredients = []
        if req.ingredients_csv:
            ing_reader = csv.DictReader(io.StringIO(req.ingredients_csv))
            ingredients = []
            for row in ing_reader:
                normalised = {k.lower().strip(): v.strip() for k, v in row.items() if k}
                item_name = normalised.get('item', normalised.get('ingredient', normalised.get('name', '')))
                if not item_name:
                    continue
                ingredients.append({
                    "category": normalised.get('category', normalised.get('aisle', 'Other')) or 'Other',
                    "item": item_name,
                    "quantity": normalised.get('quantity', normalised.get('qty', None)),
                    "for_recipe": normalised.get('recipe', normalised.get('for', None)),
                })
            if ingredients:
                upserted_ingredients = await set_meal_plan_ingredients(plan["id"], ingredients)

        return {
            "status": "imported",
            "plan_id": plan["id"],
            "week_start": week_start,
            "items_count": len(upserted_items),
            "ingredients_count": len(upserted_ingredients),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CSV import failed: {e}")


@app.post("/meal-plan/import/gousto")
async def meal_plan_import_gousto():
    """Search Gmail for recent Gousto order confirmation emails and extract recipe names.

    Matches extracted recipes against the current meal plan items tagged as 'gousto'.
    """
    from .google_auth import get_gmail_service
    from domains.nutrition.services.meal_plan_service import get_current_meal_plan
    import base64
    import re
    from html import unescape

    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=503, detail="Gmail not configured")

        # Search for recent Gousto emails
        results = service.users().messages().list(
            userId='me',
            q='from:gousto.co.uk newer_than:14d',
            maxResults=5
        ).execute()

        messages = results.get('messages', [])
        if not messages:
            return {
                "status": "no_emails",
                "message": "No recent Gousto emails found (last 14 days)",
                "recipes_found": [],
                "fetched_at": datetime.now(UK_TZ).isoformat()
            }

        # Extract recipe names from order confirmation emails only
        all_recipes = []
        for msg in messages:
            detail = service.users().messages().get(
                userId='me',
                id=msg['id'],
                format='full'
            ).execute()

            # Only process order summary emails, skip marketing
            msg_headers = {h['name']: h['value'] for h in detail.get('payload', {}).get('headers', [])}
            subject = msg_headers.get('Subject', '').lower()
            if 'summary' not in subject and 'your order' not in subject and 'your box' not in subject:
                continue

            # Extract plain text body
            body_text = ""
            payload = detail.get('payload', {})

            def extract_text(parts):
                text = ""
                if isinstance(parts, list):
                    for part in parts:
                        if part.get('mimeType') == 'text/plain':
                            data = part.get('body', {}).get('data', '')
                            if data:
                                text += base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
                        elif part.get('parts'):
                            text += extract_text(part['parts'])
                return text

            if payload.get('mimeType') == 'text/plain':
                data = payload.get('body', {}).get('data', '')
                if data:
                    body_text = base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
            elif payload.get('parts'):
                body_text = extract_text(payload['parts'])

            if not body_text:
                # Try HTML fallback
                def extract_html(parts):
                    text = ""
                    if isinstance(parts, list):
                        for part in parts:
                            if part.get('mimeType') == 'text/html':
                                data = part.get('body', {}).get('data', '')
                                if data:
                                    html = base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
                                    # Strip HTML tags
                                    text += re.sub(r'<[^>]+>', ' ', unescape(html))
                            elif part.get('parts'):
                                text += extract_html(part['parts'])
                    return text

                body_text = extract_html(payload.get('parts', []))

            if not body_text:
                continue

            # Parse Gousto recipe names from the email
            # Gousto order summary emails list recipes in a structured block:
            #   Recipe Name
            #   Eat-by-date:
            #   DD Mon - DD Mon
            #   Cooking time: XX mins
            #   See recipe
            # We find lines immediately before "Cooking time:" — those are recipe names.
            lines = [l.strip() for l in body_text.split('\n')]
            for i, line in enumerate(lines):
                if line.lower().startswith('cooking time:'):
                    # Walk backwards to find the recipe name (skip eat-by-date lines, URLs)
                    for j in range(i - 1, max(i - 8, -1), -1):
                        candidate = lines[j].strip()
                        if not candidate:
                            continue
                        # Skip date lines, "See recipe", "Eat-by-date:", URLs etc
                        if re.match(r'^\d{1,2}\s+\w+\s*-?\s*$', candidate):
                            continue  # partial date like "11 Feb" or "10 Feb -"
                        if re.match(r'^\d{1,2}\s+\w+\s*-\s*\d{1,2}\s+\w+', candidate):
                            continue  # full date range like "10 Feb - 11 Feb"
                        if candidate.lower() in ('eat-by-date:', 'see recipe', 'start drooling'):
                            continue
                        if candidate.startswith('(') or candidate.startswith('http'):
                            continue  # URL lines
                        # This should be the recipe name
                        if len(candidate) > 5 and candidate not in all_recipes:
                            all_recipes.append(candidate)
                        break

        # Match against current meal plan
        plan = await get_current_meal_plan()
        matched = []
        unmatched = list(all_recipes)

        if plan and plan.get('items'):
            gousto_items = [i for i in plan['items'] if i.get('source_tag') == 'gousto']
            for recipe in all_recipes:
                for item in gousto_items:
                    meal_name = (item.get('adults_meal') or '').lower()
                    if recipe.lower() in meal_name or meal_name in recipe.lower():
                        matched.append({
                            "recipe": recipe,
                            "matched_meal": item.get('adults_meal'),
                            "date": item.get('date')
                        })
                        if recipe in unmatched:
                            unmatched.remove(recipe)
                        break

        return {
            "status": "found" if all_recipes else "no_recipes",
            "emails_checked": len(messages),
            "recipes_found": all_recipes,
            "matched": matched,
            "unmatched": unmatched,
            "plan_id": plan["id"] if plan else None,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gousto import failed: {e}")


@app.get("/meal-plan/shopping-list")
async def meal_plan_shopping_list(plan_id: str = Query(default=None, description="Plan ID (defaults to current week)")):
    """Get meal plan ingredients as shopping-list-compatible categories."""
    from domains.nutrition.services.meal_plan_service import (
        get_current_meal_plan, get_shopping_list_categories
    )

    try:
        if not plan_id:
            plan = await get_current_meal_plan()
            if not plan:
                return {"categories": {}, "message": "No meal plan found for this week"}
            plan_id = plan["id"]

        categories = await get_shopping_list_categories(plan_id)

        if not categories:
            return {
                "categories": {},
                "message": "No ingredients found. Add ingredients to the meal plan or import from sheets.",
                "plan_id": plan_id
            }

        total_items = sum(len(items) for items in categories.values())
        return {
            "categories": categories,
            "category_count": len(categories),
            "item_count": total_items,
            "plan_id": plan_id,
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/meal-plan/shopping-list/generate")
async def meal_plan_shopping_list_generate(
    plan_id: str = Query(default=None, description="Plan ID (defaults to current week)"),
    title: str = Query(default=None, description="PDF title (auto-generated if not provided)")
):
    """Generate a shopping list PDF from the current meal plan's ingredients."""
    import sys
    from datetime import datetime as dt
    from domains.nutrition.services.meal_plan_service import (
        get_current_meal_plan, get_meal_plan_by_id, get_shopping_list_categories
    )

    try:
        if plan_id:
            plan = await get_meal_plan_by_id(plan_id)
        else:
            plan = await get_current_meal_plan()

        if not plan:
            raise HTTPException(status_code=404, detail="No meal plan found")

        categories = await get_shopping_list_categories(plan["id"])
        if not categories:
            raise HTTPException(status_code=400, detail="No ingredients in this meal plan")

        # Generate title from week_start if not provided
        if not title:
            from datetime import datetime as dt2
            week_date = dt2.fromisoformat(plan["week_start"])
            title = f"Meal Plan - w/c {week_date.strftime('%d %b %Y')}"

        # Generate PDF using existing shopping list generator
        scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        from generate_shopping_list import generate_shopping_list_pdf

        out_dir = Path(SHOPPING_LIST_DEFAULT_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        timestamp = dt.now().strftime("%Y%m%d_%H%M%S")
        filename = f"meal_plan_shopping_{timestamp}.pdf"
        output_path = out_dir / filename

        result = await asyncio.to_thread(
            generate_shopping_list_pdf, str(output_path), categories, title
        )

        return {
            "status": "created",
            "filename": filename,
            "path": str(result),
            "plan_id": plan["id"],
            "week_start": plan["week_start"],
            "category_count": len(categories),
            "item_count": sum(len(v) for v in categories.values())
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")


@app.post("/meal-plan/export-pdf")
async def meal_plan_export_pdf(
    plan_id: str = Query(default=None, description="Plan ID (defaults to current week)"),
    title: str = Query(default=None, description="PDF title (auto-generated if not provided)")
):
    """Generate a landscape meal plan PDF showing the weekly grid."""
    import sys
    from datetime import datetime as dt
    from domains.nutrition.services.meal_plan_service import (
        get_current_meal_plan, get_meal_plan_by_id
    )

    try:
        if plan_id:
            plan = await get_meal_plan_by_id(plan_id)
        else:
            plan = await get_current_meal_plan()

        if not plan:
            raise HTTPException(status_code=404, detail="No meal plan found")

        if not plan.get("items"):
            raise HTTPException(status_code=400, detail="No meals in this plan")

        # Import the generator
        scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        from generate_meal_plan_pdf import generate_meal_plan_pdf

        out_dir = Path(SHOPPING_LIST_DEFAULT_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        timestamp = dt.now().strftime("%Y%m%d_%H%M%S")
        filename = f"meal_plan_{timestamp}.pdf"
        output_path = out_dir / filename

        result = await asyncio.to_thread(
            generate_meal_plan_pdf, str(output_path), plan, title
        )

        return {
            "status": "created",
            "filename": filename,
            "path": str(result),
            "plan_id": plan["id"],
            "week_start": plan["week_start"],
            "days_count": len(plan.get("items", [])),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Meal plan PDF generation failed: {e}")


@app.put("/meal-plan/{plan_id}/ingredients")
async def meal_plan_update_ingredients(plan_id: str, req: MealPlanIngredientsUpdate):
    """Replace all ingredients for a meal plan.

    Each ingredient: {category, item, quantity?, for_recipe?}
    """
    from domains.nutrition.services.meal_plan_service import set_meal_plan_ingredients

    try:
        result = await set_meal_plan_ingredients(plan_id, req.ingredients)
        return {
            "status": "updated",
            "plan_id": plan_id,
            "ingredients_count": len(result),
            "fetched_at": datetime.now(UK_TZ).isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Hadley Bricks Proxy - forwards /hb/* to HB app on port 3000
# ============================================================

HB_BASE_URL = os.environ.get("HADLEY_BRICKS_LOCAL_URL", "http://localhost:3000")
HB_API_KEY = os.environ.get("HADLEY_BRICKS_API_KEY", "")


@app.api_route("/hb/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def hb_proxy(request: Request, path: str):
    """Proxy all /hb/* requests to Hadley Bricks app on localhost:3000/api/*.

    Injects the service API key so Peter can call HB endpoints without
    managing auth himself. Supports all HTTP methods.
    """
    import httpx

    target_url = f"{HB_BASE_URL}/api/{path}"

    # Forward query params
    if request.url.query:
        target_url += f"?{request.url.query}"

    # Build headers — inject API key, forward content-type
    headers = {"x-api-key": HB_API_KEY}
    if request.headers.get("content-type"):
        headers["content-type"] = request.headers["content-type"]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Read body for non-GET requests
            body = None
            if request.method != "GET":
                body = await request.body()

            response = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
            )

        # Return the HB response as-is
        return Response(
            content=response.content,
            status_code=response.status_code,
            media_type=response.headers.get("content-type", "application/json"),
        )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Hadley Bricks app is not running (port 3000). Check HadleyBricks NSSM service."
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Hadley Bricks request timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"HB proxy error: {str(e)}")


# ============================================================
# Investment ML Pipeline
# ============================================================

HB_PROJECT_DIR = os.environ.get(
    "HADLEY_BRICKS_DIR",
    r"C:\Users\Chris Hadley\claude-projects\hadley-bricks-inventory-management",
)


@app.post("/investment/retrain")
async def investment_retrain(request: Request, step: Optional[str] = Query(None)):
    """Trigger the Python LightGBM investment prediction pipeline.

    Query params:
        step: Optional - run a single step (build|features|train|score).
              If omitted, runs the full pipeline.
    """
    import subprocess

    ml_dir = os.path.join(HB_PROJECT_DIR, "scripts", "ml")
    if not os.path.isdir(ml_dir):
        raise HTTPException(status_code=500, detail=f"ML directory not found: {ml_dir}")

    cmd = ["python", "run_pipeline.py"]
    if step:
        if step not in ("build", "features", "train", "score"):
            raise HTTPException(status_code=400, detail=f"Invalid step: {step}. Must be build|features|train|score")
        cmd.extend(["--step", step])

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            cwd=ml_dir,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout
        )

        return {
            "status": "success" if result.returncode == 0 else "error",
            "returncode": result.returncode,
            "stdout": result.stdout[-5000:] if result.stdout else "",
            "stderr": result.stderr[-2000:] if result.stderr else "",
            "step": step or "full",
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Pipeline timed out after 10 minutes")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


# ============================================================
# Model Provider Management
# ============================================================

MODEL_CONFIG_PATH = Path(__file__).parent.parent / "data" / "model_config.json"

VALID_PROVIDERS = ["claude_cc", "claude_cc2", "kimi"]

MODEL_DEFAULT_STATE = {
    "active_provider": "claude_cc",
    "reason": "default",
    "switched_at": None,
    "auto_switch_enabled": True,
    "kimi_requests": 0,
    "failover_history": [],
}


def _read_model_config() -> dict:
    """Read model config from data/model_config.json."""
    try:
        with open(MODEL_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return MODEL_DEFAULT_STATE.copy()


def _write_model_config(data: dict) -> None:
    """Write model config atomically."""
    import tempfile
    MODEL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = MODEL_CONFIG_PATH.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(str(tmp_path), str(MODEL_CONFIG_PATH))


@app.get("/model/status")
async def get_model_status():
    """Get current model provider status."""
    state = _read_model_config()
    # Migrate legacy 'claude' → 'claude_cc'
    if state.get("active_provider") == "claude":
        state["active_provider"] = "claude_cc"
    state["provider_priority"] = VALID_PROVIDERS
    return state


class ModelSwitchRequest(BaseModel):
    provider: str
    reason: str = "manual"


@app.put("/model/switch")
async def switch_model_provider(req: ModelSwitchRequest):
    """Switch active model provider."""
    # Accept legacy 'claude' as 'claude_cc'
    provider = "claude_cc" if req.provider == "claude" else req.provider
    if provider not in VALID_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Provider must be one of {VALID_PROVIDERS}"
        )

    state = _read_model_config()
    old = state.get("active_provider", "claude_cc")
    if old == "claude":
        old = "claude_cc"
    state["active_provider"] = provider
    state["reason"] = req.reason
    state["switched_at"] = datetime.now(UK_TZ).isoformat()
    if provider.startswith("claude_"):
        state["kimi_requests"] = 0

    # Record in failover history
    history = state.get("failover_history", [])
    history.append({
        "from": old,
        "to": provider,
        "reason": req.reason,
        "at": datetime.now(UK_TZ).isoformat(),
    })
    state["failover_history"] = history[-20:]

    _write_model_config(state)

    return {"status": "ok", "switched": f"{old} → {provider}", "reason": req.reason}


class AutoSwitchRequest(BaseModel):
    enabled: bool


@app.put("/model/auto-switch")
async def toggle_auto_switch(req: AutoSwitchRequest):
    """Toggle automatic provider switching."""
    state = _read_model_config()
    state["auto_switch_enabled"] = req.enabled
    _write_model_config(state)

    return {"status": "ok", "auto_switch_enabled": req.enabled}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8100)
