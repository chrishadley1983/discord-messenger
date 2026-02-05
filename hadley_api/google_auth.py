"""Google OAuth handling with automatic token refresh."""

import os
from pathlib import Path
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Load .env file from parent directory (Discord-Messenger root)
# This ensures credentials work regardless of where the API is started from
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# Load from environment
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN")

# Full scopes for all Hadley API endpoints
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.settings.basic",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/contacts",  # Full read/write access
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/documents",
]

_credentials = None


def get_credentials():
    """Get valid Google credentials, refreshing if needed."""
    global _credentials

    if not all([GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN]):
        return None

    if _credentials and _credentials.valid:
        return _credentials

    # Create credentials from refresh token
    # Note: Don't specify scopes here - use whatever scopes the token was granted
    # Specifying scopes that don't match the original grant causes invalid_scope errors
    _credentials = Credentials(
        token=None,
        refresh_token=GOOGLE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
    )

    # Refresh to get access token
    if _credentials.expired or not _credentials.valid:
        _credentials.refresh(Request())

    return _credentials


def get_gmail_service():
    """Get Gmail API service."""
    creds = get_credentials()
    if not creds:
        return None
    return build('gmail', 'v1', credentials=creds)


def get_calendar_service():
    """Get Calendar API service."""
    creds = get_credentials()
    if not creds:
        return None
    return build('calendar', 'v3', credentials=creds)


def get_drive_service():
    """Get Drive API service."""
    creds = get_credentials()
    if not creds:
        return None
    return build('drive', 'v3', credentials=creds)
