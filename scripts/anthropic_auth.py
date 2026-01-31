"""Anthropic Console Authentication Script.

Run this to authenticate and save session cookies for usage scraping.
Session typically lasts days/weeks before re-auth is needed.

Usage:
    python scripts/anthropic_auth.py
"""

import asyncio
import json
import os
from pathlib import Path

# Try playwright, fall back to install instructions
try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Playwright not installed. Run:")
    print("  py -m pip install playwright")
    print("  py -m playwright install chromium")
    exit(1)

STORAGE_PATH = Path(__file__).parent.parent / "data" / "anthropic_session.json"
CONSOLE_URL = "https://console.anthropic.com"
USAGE_URL = "https://console.anthropic.com/settings/usage"


async def main():
    print("=" * 60)
    print("Anthropic Console Authentication")
    print("=" * 60)
    print()
    print("This will open a browser for you to log in to Anthropic.")
    print("After logging in (including clicking the email 2FA link),")
    print("the session will be saved for the bot to reuse.")
    print()

    # Ensure data directory exists
    STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        # Launch visible browser for user to log in
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        # Navigate to console
        print("Opening Anthropic Console...")
        await page.goto(CONSOLE_URL)

        print()
        print("Please log in to your Anthropic account.")
        print("If you have 2FA, check your email and click the verification link.")
        print()
        print("Once you're logged in and can see the dashboard,")
        input("press Enter here to save the session...")

        # Verify we're logged in by checking for usage page access
        print()
        print("Verifying login...")
        await page.goto(USAGE_URL)
        await page.wait_for_load_state("networkidle")

        # Check if we're on the usage page (not redirected to login)
        current_url = page.url
        if "login" in current_url or "sign" in current_url:
            print("ERROR: Still on login page. Please log in fully before pressing Enter.")
            await browser.close()
            return

        # Save storage state (cookies + localStorage)
        storage = await context.storage_state()

        with open(STORAGE_PATH, "w") as f:
            json.dump(storage, f, indent=2)

        print()
        print("=" * 60)
        print("SUCCESS! Session saved to:")
        print(f"  {STORAGE_PATH}")
        print("=" * 60)
        print()
        print("The bot can now scrape your Anthropic usage data.")
        print("Re-run this script if the session expires (usually after a few weeks).")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
