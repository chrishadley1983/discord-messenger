#!/usr/bin/env python3
"""
Browser Session Setup Script

Interactive script to authenticate with Amazon/eBay.
Opens a visible browser window for manual login, then saves the session
for Peter to use in headless mode.

Usage:
    python scripts/setup_browser_session.py amazon
    python scripts/setup_browser_session.py ebay
    python scripts/setup_browser_session.py --list
    python scripts/setup_browser_session.py --check amazon

Run this script when:
- Setting up a new site for the first time
- Session cookies have expired
- You need to re-authenticate (e.g., after password change)
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright

# Session storage directory
SESSIONS_DIR = Path(__file__).parent.parent / "data" / "browser_sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

# Domain configurations
DOMAIN_CONFIGS = {
    "amazon": {
        "display_name": "Amazon UK",
        "login_url": "https://www.amazon.co.uk/gp/css/homepage.html",  # Account page - triggers login if needed
        "success_indicator": "Hello,",  # Text that appears when logged in
        "domain": "amazon.co.uk",
    },
    "ebay": {
        "display_name": "eBay UK",
        "login_url": "https://www.ebay.co.uk/signin/",  # Simpler signin URL
        "success_indicator": "Hi ",  # Text that appears when logged in
        "domain": "ebay.co.uk",
    },
}


async def setup_session(site: str, headless: bool = False) -> bool:
    """
    Open browser for manual login and save session.

    Args:
        site: Site key (amazon, ebay)
        headless: If True, just validate existing session

    Returns:
        True if session was saved successfully
    """
    if site not in DOMAIN_CONFIGS:
        print(f"Unknown site: {site}")
        print(f"Available sites: {', '.join(DOMAIN_CONFIGS.keys())}")
        return False

    config = DOMAIN_CONFIGS[site]
    session_file = SESSIONS_DIR / f"{site}.json"
    profile_dir = SESSIONS_DIR / f"{site}_profile"

    print(f"\n{'='*60}")
    print(f"  Setting up {config['display_name']} session")
    print(f"{'='*60}\n")

    async with async_playwright() as p:
        # Launch browser with persistent context
        print(f"Launching browser (profile: {profile_dir})...")

        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=headless,
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"],
        )

        page = browser.pages[0] if browser.pages else await browser.new_page()

        # Navigate to login page
        print(f"Navigating to {config['login_url']}...")
        await page.goto(config["login_url"], wait_until="networkidle")

        if headless:
            # Just check if logged in
            content = await page.content()
            is_logged_in = config["success_indicator"].lower() in content.lower()

            await browser.close()
            return is_logged_in

        # Interactive mode - wait for user to login
        print(f"\n{'*'*60}")
        print(f"  MANUAL ACTION REQUIRED")
        print(f"{'*'*60}")
        print(f"\n  1. Log in to {config['display_name']} in the browser window")
        print(f"  2. Complete any 2FA/verification if prompted")
        print(f"  3. Once logged in, PRESS ENTER in this terminal to save the session")
        print(f"\n  DO NOT close the browser until you press Enter here!")
        print(f"\n{'*'*60}\n")

        # Wait for user to press Enter
        login_detected = False
        try:
            # Use a thread to wait for input while keeping browser alive
            import threading
            input_received = threading.Event()

            def wait_for_input():
                input("  Press ENTER when you have finished logging in... ")
                input_received.set()

            input_thread = threading.Thread(target=wait_for_input, daemon=True)
            input_thread.start()

            # Poll while waiting for input
            while not input_received.is_set():
                try:
                    # Check for login success (informational only)
                    if not login_detected and browser.pages:
                        content = await page.content()
                        if config["success_indicator"].lower() in content.lower():
                            print("\n  Login detected! Press ENTER to save the session.")
                            login_detected = True
                except Exception:
                    pass  # Ignore errors during polling

                await asyncio.sleep(0.5)

        except KeyboardInterrupt:
            print("\n  Cancelled by user.")
            await browser.close()
            return False

        # Save storage state
        print("\n  Saving session...")
        try:
            storage = await browser.storage_state()

            # Add metadata
            session_data = {
                "storage_state": storage,
                "site": site,
                "domain": config["domain"],
                "created_at": datetime.utcnow().isoformat(),
                "profile_dir": str(profile_dir),
            }

            with open(session_file, "w") as f:
                json.dump(session_data, f, indent=2)

            print(f"  Session saved to: {session_file}")

            await browser.close()
            return True

        except Exception as e:
            print(f"\n  Error saving session: {e}")
            try:
                await browser.close()
            except Exception:
                pass
            return False


async def check_session(site: str) -> bool:
    """Check if a session exists and is valid."""
    if site not in DOMAIN_CONFIGS:
        print(f"Unknown site: {site}")
        return False

    config = DOMAIN_CONFIGS[site]
    session_file = SESSIONS_DIR / f"{site}.json"
    profile_dir = SESSIONS_DIR / f"{site}_profile"

    print(f"\nChecking {config['display_name']} session...")

    # Check if files exist
    if not session_file.exists():
        print(f"  Session file not found: {session_file}")
        return False

    if not profile_dir.exists():
        print(f"  Profile directory not found: {profile_dir}")
        return False

    # Load session data
    with open(session_file) as f:
        session_data = json.load(f)

    created_at = session_data.get("created_at", "unknown")
    print(f"  Session created: {created_at}")

    # Check cookie count
    cookies = session_data.get("storage_state", {}).get("cookies", [])
    print(f"  Cookies stored: {len(cookies)}")

    # Try to validate by loading the site
    print(f"  Validating session (headless)...")

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=True,
                viewport={"width": 1280, "height": 800},
            )

            page = browser.pages[0] if browser.pages else await browser.new_page()

            # Go to the main site
            main_url = f"https://www.{config['domain']}/"
            await page.goto(main_url, wait_until="networkidle", timeout=30000)

            # Check for login indicator
            content = await page.content()
            is_logged_in = config["success_indicator"].lower() in content.lower()

            await browser.close()

            if is_logged_in:
                print(f"  Status: VALID (logged in)")
                return True
            else:
                print(f"  Status: EXPIRED (not logged in)")
                return False

        except Exception as e:
            print(f"  Status: ERROR ({e})")
            return False


def list_sessions():
    """List all saved sessions."""
    print(f"\nSaved browser sessions in {SESSIONS_DIR}:\n")

    for site, config in DOMAIN_CONFIGS.items():
        session_file = SESSIONS_DIR / f"{site}.json"
        profile_dir = SESSIONS_DIR / f"{site}_profile"

        print(f"  {config['display_name']} ({site}):")

        if session_file.exists():
            with open(session_file) as f:
                data = json.load(f)
            created = data.get("created_at", "unknown")
            cookies = len(data.get("storage_state", {}).get("cookies", []))
            print(f"    Session file: {session_file.name}")
            print(f"    Created: {created}")
            print(f"    Cookies: {cookies}")
        else:
            print(f"    Session file: NOT FOUND")

        if profile_dir.exists():
            size = sum(f.stat().st_size for f in profile_dir.rglob("*") if f.is_file())
            print(f"    Profile: {profile_dir.name} ({size / 1024 / 1024:.1f} MB)")
        else:
            print(f"    Profile: NOT FOUND")

        print()


async def main():
    parser = argparse.ArgumentParser(
        description="Setup browser sessions for Peter's purchasing feature",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python setup_browser_session.py amazon     # Setup Amazon session
    python setup_browser_session.py ebay       # Setup eBay session
    python setup_browser_session.py --list     # List all sessions
    python setup_browser_session.py --check amazon  # Check if Amazon session is valid
        """,
    )

    parser.add_argument(
        "site",
        nargs="?",
        choices=list(DOMAIN_CONFIGS.keys()),
        help="Site to setup (amazon, ebay)",
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List all saved sessions",
    )
    parser.add_argument(
        "--check",
        "-c",
        metavar="SITE",
        help="Check if a session is valid",
    )

    args = parser.parse_args()

    if args.list:
        list_sessions()
        return

    if args.check:
        valid = await check_session(args.check)
        sys.exit(0 if valid else 1)

    if not args.site:
        parser.print_help()
        print("\nAvailable sites:")
        for site, config in DOMAIN_CONFIGS.items():
            print(f"  {site}: {config['display_name']}")
        sys.exit(1)

    success = await setup_session(args.site)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
