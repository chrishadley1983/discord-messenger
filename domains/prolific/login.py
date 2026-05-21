"""One-time manual login to Prolific in the Chrome-Prolific profile.

Usage (from the project root):
    python -m domains.prolific.login

Launches Chrome HEADED so you can log in with Google or email/password.
Cookies persist in the dedicated profile dir; subsequent monitor runs use
the same session in headless mode.
"""

from __future__ import annotations

import asyncio
import sys

from logger import logger

from .chrome import _chrome_alive, ensure_chrome_running
from .config import CDP_PORT, LOGIN_URL, STUDIES_URL


async def _open_login() -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await ctx.new_page()
        await page.goto(LOGIN_URL)

        print()
        print("=" * 60)
        print("  Chrome-Prolific is now open. Log in to Prolific.")
        print(f"  Then navigate to {STUDIES_URL} — this script will exit")
        print("  automatically once it detects you're on /studies.")
        print("  (Or press Enter here if it gets stuck.)")
        print("=" * 60)
        print()

        # Wait for either: navigation to /studies OR the user pressing Enter.
        # Whichever fires first wins. We swallow EOFError so it still works when
        # invoked from a shell embed that doesn't keep stdin open.
        async def _wait_for_studies():
            try:
                await page.wait_for_url("**/studies**", timeout=300_000)  # 5 min
            except Exception as e:
                logger.debug(f"wait_for_url ended: {e}")

        async def _wait_for_input():
            try:
                await asyncio.to_thread(input)
            except EOFError:
                # Stdin closed — fall back to a long sleep so the URL watcher wins.
                await asyncio.sleep(300)

        done, pending = await asyncio.wait(
            [asyncio.create_task(_wait_for_studies()), asyncio.create_task(_wait_for_input())],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()

        print(f"Detected URL: {page.url}")
        # Leave Chrome running so cookies persist; just disconnect this client.
        try:
            await page.close()
        except Exception:
            pass


def main() -> None:
    # ensure_chrome_running short-circuits if CDP is already up, so if the bot
    # has Chrome-Prolific running headless we'd silently attach to the invisible
    # window. Detect and bail with a clear message instead.
    if _chrome_alive():
        print(
            f"ERROR: Chrome is already listening on CDP port {CDP_PORT}.\n"
            "The DiscordBot service is probably running it headless, which means\n"
            "this login script would attach to an invisible window.\n\n"
            "Stop the bot first, then re-run this script:\n"
            "    Stop-Service DiscordBot\n"
            "    python -m domains.prolific.login\n"
            "    Start-Service DiscordBot   # after you've logged in\n",
            file=sys.stderr,
        )
        sys.exit(1)

    ensure_chrome_running(headless=False)
    asyncio.run(_open_login())


if __name__ == "__main__":
    main()
