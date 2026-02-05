#!/usr/bin/env python3
"""
Ring Authentication Setup Script

Run this once to authenticate with Ring and save the token.
The token will be saved to ring_token.json for the Hadley API to use.
"""

import asyncio
import json
from pathlib import Path
from ring_doorbell import Auth, Requires2FAError

TOKEN_FILE = Path(__file__).parent / "ring_token.json"


def token_updated_callback(token: dict) -> None:
    """Save token when it's updated."""
    TOKEN_FILE.write_text(json.dumps(token, indent=2))
    print(f"Token saved to {TOKEN_FILE}")


async def main():
    print("Ring Doorbell Authentication Setup")
    print("=" * 40)

    # Get credentials from env or prompt
    import os
    from dotenv import load_dotenv
    load_dotenv()

    email = os.getenv("RING_EMAIL")
    if not email:
        email = input("Enter your Ring email: ").strip()
    else:
        print(f"Using email from .env: {email}")

    password = input("Enter your Ring password: ").strip()

    auth = Auth("HadleyAPI/1.0", None, token_updated_callback)

    try:
        print("\nAttempting login...")
        await auth.async_fetch_token(email, password)
        print("Login successful without 2FA!")
    except Requires2FAError:
        print("\n2FA required! Check your phone for the code.")
        code = input("Enter the 2FA code from SMS: ").strip()

        try:
            await auth.async_fetch_token(email, password, code)
            print("\nLogin successful with 2FA!")
        except Exception as e:
            print(f"\n2FA authentication failed: {e}")
            return
    except Exception as e:
        print(f"\nLogin failed: {e}")
        return

    # Verify token was saved
    if TOKEN_FILE.exists():
        print(f"\nToken saved successfully to: {TOKEN_FILE}")
        print("The Hadley API will now be able to access your Ring devices.")
    else:
        print("\nWarning: Token file was not created.")


if __name__ == "__main__":
    asyncio.run(main())
