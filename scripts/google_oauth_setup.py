"""Google OAuth Setup Script - Get refresh token for Hadley API.

Run this once to get a refresh token, then add it to .env

Uses google-auth-oauthlib for proper Desktop app OAuth flow.
"""

import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

# Load from .env file if present
load_dotenv()

# Get credentials from environment variables
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID") or os.getenv("GOOGLE_OAUTH_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET") or os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    print("ERROR: Missing required environment variables.")
    print("Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET")
    print("in your .env file or environment before running this script.")
    sys.exit(1)

# Full scopes for Hadley API
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


def main():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("ERROR: google-auth-oauthlib not installed.")
        print("Run: pip install google-auth-oauthlib")
        sys.exit(1)

    print("=" * 60)
    print("Google OAuth Setup for Hadley API")
    print("=" * 60)
    print()
    print("This will open a browser window for Google authorization.")
    print()

    # Create a temporary client secrets file (required by the library)
    client_config = {
        "installed": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"]
        }
    }

    # Use InstalledAppFlow which handles Desktop OAuth properly
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)

    # Run local server to handle the OAuth callback
    # This opens browser and waits for authorization
    credentials = flow.run_local_server(
        port=8085,
        prompt="consent",  # Force consent to always get refresh token
        access_type="offline"
    )

    print()
    print("=" * 60)
    print("SUCCESS! Add these to your .env file:")
    print("=" * 60)
    print()
    print(f"GOOGLE_CLIENT_ID={CLIENT_ID}")
    print(f"GOOGLE_CLIENT_SECRET={CLIENT_SECRET}")
    print(f"GOOGLE_REFRESH_TOKEN={credentials.refresh_token}")
    print()

    if credentials.refresh_token:
        print("Refresh token obtained successfully!")
        print()
        print("Scopes granted:")
        for scope in credentials.scopes:
            print(f"  - {scope}")
    else:
        print("WARNING: No refresh token returned.")
        print("You may need to revoke access and try again.")


if __name__ == "__main__":
    main()
