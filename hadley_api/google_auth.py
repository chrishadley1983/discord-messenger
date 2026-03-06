"""Google OAuth handling with automatic token refresh.

Supports multiple accounts:
- "personal" (default): Chris's personal Gmail (GOOGLE_REFRESH_TOKEN)
- "hadley-bricks": chris@hadleybricks.co.uk (GOOGLE_REFRESH_TOKEN_HB)
"""

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
GOOGLE_REFRESH_TOKEN_HB = os.getenv("GOOGLE_REFRESH_TOKEN_HB")

# Account name -> refresh token mapping
_ACCOUNT_TOKENS = {
    "personal": GOOGLE_REFRESH_TOKEN,
    "hadley-bricks": GOOGLE_REFRESH_TOKEN_HB,
}

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

# Per-account credential cache
_credentials_cache: dict[str, Credentials] = {}


def get_credentials(account: str = "personal"):
    """Get valid Google credentials, refreshing if needed.

    Args:
        account: Account name - "personal" or "hadley-bricks"
    """
    global _credentials_cache

    refresh_token = _ACCOUNT_TOKENS.get(account, GOOGLE_REFRESH_TOKEN)

    if not all([GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, refresh_token]):
        return None

    cached = _credentials_cache.get(account)
    if cached and cached.valid:
        return cached

    # Create credentials from refresh token
    # Note: Don't specify scopes here - use whatever scopes the token was granted
    # Specifying scopes that don't match the original grant causes invalid_scope errors
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
    )

    # Refresh to get access token
    if creds.expired or not creds.valid:
        creds.refresh(Request())

    _credentials_cache[account] = creds
    return creds


def get_gmail_service(account: str = "personal"):
    """Get Gmail API service.

    Args:
        account: Account name - "personal" or "hadley-bricks"
    """
    creds = get_credentials(account)
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
