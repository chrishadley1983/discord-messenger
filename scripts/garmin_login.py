"""Garmin login script to save session for future use.

Run this once to authenticate with MFA, then subsequent API calls won't need MFA.

Usage:
  Interactive:     py scripts/garmin_login.py
  With MFA code:   py scripts/garmin_login.py 123456
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import garth

from config import GARMIN_EMAIL, GARMIN_PASSWORD

# Session storage directory
SESSION_DIR = Path(os.getenv("LOCALAPPDATA", ".")) / "discord-assistant" / "garmin_session"


def custom_mfa_prompt():
    """Custom MFA prompt that checks for command-line argument."""
    if len(sys.argv) > 1:
        mfa_code = sys.argv[1]
        print(f"Using MFA code from argument: {mfa_code}")
        return mfa_code
    return input("MFA code: ")


def main():
    print("=" * 60)
    print("Garmin Connect Login")
    print("=" * 60)
    print()

    if not GARMIN_EMAIL or not GARMIN_PASSWORD:
        print("ERROR: GARMIN_EMAIL and GARMIN_PASSWORD must be set in .env")
        return

    print(f"Email: {GARMIN_EMAIL}")
    print(f"Session will be saved to: {SESSION_DIR}")
    print()

    # Check if session already exists and is valid
    if SESSION_DIR.exists():
        print("Existing session found. Testing if still valid...")
        try:
            garth.resume(str(SESSION_DIR))
            # Try a simple API call to verify
            today = garth.client.connectapi("/usersummary-service/usersummary/daily/2026-01-29")
            if today:
                print("[OK] Session is still valid!")
                print(f"   Today's steps: {today.get('totalSteps', 0)}")
                return
        except Exception as e:
            print(f"Session expired or invalid: {e}")
            print("Will re-authenticate...")
            print()

    # Perform login
    print("Logging in to Garmin Connect...")
    if len(sys.argv) > 1:
        print(f"MFA code provided: {sys.argv[1]}")
    else:
        print("If MFA is enabled, you'll be prompted to enter the code.")
    print()

    try:
        garth.login(GARMIN_EMAIL, GARMIN_PASSWORD, prompt_mfa=custom_mfa_prompt)

        # Save session
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        garth.save(str(SESSION_DIR))

        print()
        print("[OK] Login successful! Session saved.")
        print()

        # Test the connection using the global client
        print("Testing API access...")
        today = garth.client.connectapi("/usersummary-service/usersummary/daily/2026-01-29")
        if today:
            print(f"   Today's steps: {today.get('totalSteps', 0)}")
            print(f"   Resting HR: {today.get('restingHeartRate', 'N/A')}")

        print()
        print("You can now run backfill_health_data.py without MFA prompts.")

    except Exception as e:
        print(f"[FAILED] Login failed: {e}")


if __name__ == "__main__":
    main()
