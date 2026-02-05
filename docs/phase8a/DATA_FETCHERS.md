# Phase 8a Data Fetchers

Add these to `domains/peterbot/data_fetchers.py`:

```python
# ============================================================
# PHASE 8a: Gmail / Calendar / Drive / Notion Data Fetchers
# ============================================================

import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import requests

# Import config
from config import (
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN,
    NOTION_API_KEY, NOTION_TODOS_DATABASE_ID, NOTION_IDEAS_DATABASE_ID
)


# === GOOGLE AUTH HELPER ===

def get_google_access_token() -> Optional[str]:
    """Refresh and return Google access token."""
    if not all([GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN]):
        return None
    
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": GOOGLE_REFRESH_TOKEN,
            "grant_type": "refresh_token"
        }
    )
    
    if response.status_code == 200:
        return response.json().get("access_token")
    return None


# === GMAIL FETCHERS ===

def get_email_summary_data() -> Dict[str, Any]:
    """Fetch unread email summary for email-summary skill."""
    token = get_google_access_token()
    if not token:
        return {"error": "Google auth not configured"}
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get unread count
    unread_response = requests.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages",
        headers=headers,
        params={"q": "is:unread", "maxResults": 20}
    )
    
    if unread_response.status_code != 200:
        return {"error": f"Gmail API error: {unread_response.status_code}"}
    
    messages = unread_response.json().get("messages", [])
    unread_count = unread_response.json().get("resultSizeEstimate", 0)
    
    # Get details for recent unread
    emails = []
    for msg in messages[:10]:  # Limit to 10
        detail = requests.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg['id']}",
            headers=headers,
            params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]}
        ).json()
        
        headers_dict = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
        emails.append({
            "id": msg["id"],
            "from": headers_dict.get("From", "Unknown"),
            "subject": headers_dict.get("Subject", "(no subject)"),
            "date": headers_dict.get("Date", ""),
            "snippet": detail.get("snippet", "")[:100]
        })
    
    return {
        "unread_count": unread_count,
        "emails": emails,
        "fetched_at": datetime.now().isoformat()
    }


# === CALENDAR FETCHERS ===

def get_schedule_today_data() -> Dict[str, Any]:
    """Fetch today's calendar events for schedule-today skill."""
    token = get_google_access_token()
    if not token:
        return {"error": "Google auth not configured"}
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get today's bounds (UK time)
    today = datetime.now()
    start_of_day = today.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)
    
    response = requests.get(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        headers=headers,
        params={
            "timeMin": start_of_day.isoformat() + "Z",
            "timeMax": end_of_day.isoformat() + "Z",
            "singleEvents": True,
            "orderBy": "startTime"
        }
    )
    
    if response.status_code != 200:
        return {"error": f"Calendar API error: {response.status_code}"}
    
    events = []
    for event in response.json().get("items", []):
        start = event.get("start", {})
        end = event.get("end", {})
        
        events.append({
            "id": event.get("id"),
            "title": event.get("summary", "(no title)"),
            "start": start.get("dateTime") or start.get("date"),
            "end": end.get("dateTime") or end.get("date"),
            "location": event.get("location"),
            "attendees": [a.get("email") for a in event.get("attendees", [])[:5]],
            "all_day": "date" in start
        })
    
    return {
        "date": today.strftime("%A %d %B"),
        "events": events,
        "event_count": len(events),
        "fetched_at": datetime.now().isoformat()
    }


def get_schedule_week_data() -> Dict[str, Any]:
    """Fetch this week's calendar events for schedule-week skill."""
    token = get_google_access_token()
    if not token:
        return {"error": "Google auth not configured"}
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get next 7 days
    today = datetime.now()
    start = today.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7)
    
    response = requests.get(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        headers=headers,
        params={
            "timeMin": start.isoformat() + "Z",
            "timeMax": end.isoformat() + "Z",
            "singleEvents": True,
            "orderBy": "startTime"
        }
    )
    
    if response.status_code != 200:
        return {"error": f"Calendar API error: {response.status_code}"}
    
    # Group by day
    events_by_day = {}
    for event in response.json().get("items", []):
        event_start = event.get("start", {})
        start_str = event_start.get("dateTime") or event_start.get("date")
        
        if start_str:
            # Parse date
            if "T" in start_str:
                day_key = start_str.split("T")[0]
            else:
                day_key = start_str
            
            if day_key not in events_by_day:
                events_by_day[day_key] = []
            
            events_by_day[day_key].append({
                "title": event.get("summary", "(no title)"),
                "start": start_str,
                "location": event.get("location")
            })
    
    return {
        "start_date": start.strftime("%A %d %B"),
        "end_date": end.strftime("%A %d %B"),
        "events_by_day": events_by_day,
        "total_events": sum(len(v) for v in events_by_day.values()),
        "fetched_at": datetime.now().isoformat()
    }


# === NOTION FETCHERS ===

def _notion_request(endpoint: str, method: str = "GET", data: dict = None) -> dict:
    """Make a request to Notion API."""
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    url = f"https://api.notion.com/v1{endpoint}"
    
    if method == "GET":
        response = requests.get(url, headers=headers)
    else:
        response = requests.post(url, headers=headers, json=data or {})
    
    return response.json()


def get_notion_todos_data() -> Dict[str, Any]:
    """Fetch todos from Notion for notion-todos skill."""
    if not NOTION_API_KEY or not NOTION_TODOS_DATABASE_ID:
        return {"error": "Notion not configured"}
    
    # Query database for incomplete tasks
    result = _notion_request(
        f"/databases/{NOTION_TODOS_DATABASE_ID}/query",
        method="POST",
        data={
            "filter": {
                "property": "Status",
                "status": {
                    "does_not_equal": "Done"
                }
            },
            "sorts": [
                {"property": "Priority", "direction": "descending"},
                {"property": "Due", "direction": "ascending"}
            ]
        }
    )
    
    if "error" in result:
        return {"error": result.get("message", "Notion API error")}
    
    todos = []
    for page in result.get("results", []):
        props = page.get("properties", {})
        
        # Extract title (usually first property or "Name")
        title_prop = props.get("Name") or props.get("Title") or props.get("Task")
        title = ""
        if title_prop and title_prop.get("title"):
            title = "".join([t.get("plain_text", "") for t in title_prop["title"]])
        
        # Extract other properties
        priority = None
        if "Priority" in props:
            priority_prop = props["Priority"]
            if priority_prop.get("select"):
                priority = priority_prop["select"].get("name")
        
        due_date = None
        if "Due" in props and props["Due"].get("date"):
            due_date = props["Due"]["date"].get("start")
        
        todos.append({
            "id": page["id"],
            "title": title,
            "priority": priority,
            "due": due_date,
            "url": page.get("url")
        })
    
    return {
        "todos": todos,
        "count": len(todos),
        "fetched_at": datetime.now().isoformat()
    }


def get_notion_ideas_data() -> Dict[str, Any]:
    """Fetch ideas from Notion for notion-ideas skill."""
    if not NOTION_API_KEY or not NOTION_IDEAS_DATABASE_ID:
        return {"error": "Notion not configured"}
    
    # Query database for recent ideas
    result = _notion_request(
        f"/databases/{NOTION_IDEAS_DATABASE_ID}/query",
        method="POST",
        data={
            "sorts": [
                {"timestamp": "created_time", "direction": "descending"}
            ],
            "page_size": 20
        }
    )
    
    if "error" in result:
        return {"error": result.get("message", "Notion API error")}
    
    ideas = []
    for page in result.get("results", []):
        props = page.get("properties", {})
        
        # Extract title
        title_prop = props.get("Name") or props.get("Title") or props.get("Idea")
        title = ""
        if title_prop and title_prop.get("title"):
            title = "".join([t.get("plain_text", "") for t in title_prop["title"]])
        
        # Extract category/tags
        category = None
        if "Category" in props and props["Category"].get("select"):
            category = props["Category"]["select"].get("name")
        elif "Tags" in props and props["Tags"].get("multi_select"):
            category = ", ".join([t["name"] for t in props["Tags"]["multi_select"]])
        
        ideas.append({
            "id": page["id"],
            "title": title,
            "category": category,
            "created": page.get("created_time"),
            "url": page.get("url")
        })
    
    return {
        "ideas": ideas,
        "count": len(ideas),
        "fetched_at": datetime.now().isoformat()
    }


# === REGISTER IN SKILL_DATA_FETCHERS ===

# Add to existing SKILL_DATA_FETCHERS dict:
# 
# SKILL_DATA_FETCHERS = {
#     ... existing entries ...
#     
#     # Phase 8a
#     "email-summary": get_email_summary_data,
#     "schedule-today": get_schedule_today_data,
#     "schedule-week": get_schedule_week_data,
#     "notion-todos": get_notion_todos_data,
#     "notion-ideas": get_notion_ideas_data,
# }
```
