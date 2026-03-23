"""Netflix viewing history adapter.

Scrapes netflix.com/viewingactivity using Playwright with saved cookies.
First run requires manual login (headed browser) to capture cookies.
Subsequent runs use saved cookies in data/netflix_cookies.json.
"""

import asyncio
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter

PROJECT_ROOT = Path(__file__).resolve().parents[4]  # Discord-Messenger/
COOKIE_FILE = PROJECT_ROOT / "data" / "netflix_cookies.json"


def _parse_date(date_str: str) -> datetime | None:
    """Parse Netflix date format like '01/3/26' (DD/M/YY)."""
    try:
        return datetime.strptime(date_str.strip(), "%d/%m/%y")
    except ValueError:
        try:
            return datetime.strptime(date_str.strip(), "%d/%m/%Y")
        except ValueError:
            logger.warning(f"Could not parse Netflix date: {date_str}")
            return None


def _title_hash(title: str, date_str: str) -> str:
    """Generate a short hash for dedup source URLs."""
    return hashlib.md5(f"{title}:{date_str}".encode()).hexdigest()[:12]


@register_adapter
class NetflixViewingAdapter(SeedAdapter):
    """Import Netflix viewing history via web scraping."""

    name = "netflix-viewing"
    description = "Import viewing history from Netflix"
    source_system = "seed:netflix"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.max_pages = config.get("max_pages", 5) if config else 5
        self.headed = config.get("headed", True) if config else True  # headless gets blocked by Netflix

    async def validate(self) -> tuple[bool, str]:
        if not COOKIE_FILE.exists():
            return False, f"Netflix cookies not found at {COOKIE_FILE}. Run scripts/netflix_login.py first."
        try:
            with open(COOKIE_FILE) as f:
                cookies = json.load(f)
            if not cookies:
                return False, "Netflix cookie file is empty"
            return True, ""
        except Exception as e:
            return False, f"Failed to read cookies: {e}"

    async def fetch(self, limit: int = 200) -> list[SeedItem]:
        """Scrape Netflix viewing activity pages."""
        items = []

        try:
            from playwright.async_api import async_playwright

            with open(COOKIE_FILE) as f:
                cookies = json.load(f)

            p = await async_playwright().__aenter__()
            browser = await p.chromium.launch(
                headless=not self.headed,
                channel="chrome",
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            )

            # Load saved cookies
            await context.add_cookies(cookies)

            page = await context.new_page()
            await page.goto(
                "https://www.netflix.com/viewingactivity",
                wait_until="networkidle",
                timeout=30000,
            )

            # Check we're not on login page
            if "/login" in page.url:
                logger.error("Netflix cookies expired — need to re-login")
                await browser.close()
                await p.stop()
                return items

            # Scroll to load more pages (Netflix lazy-loads)
            pages_loaded = 0
            while pages_loaded < self.max_pages:
                # Check for "Show More" button
                show_more = await page.query_selector('button[data-uia="viewing-activity-footer-button"]')
                if not show_more:
                    # Try generic show more
                    show_more = await page.query_selector(".viewing-activity-footer button, button.btn-showMore")

                if show_more:
                    try:
                        await show_more.click()
                        await page.wait_for_timeout(2000)
                        pages_loaded += 1
                        logger.info(f"Loaded page {pages_loaded + 1} of viewing activity")
                    except Exception:
                        break
                else:
                    break

            # Extract all rows
            rows = await page.query_selector_all("li.retableRow")
            logger.info(f"Found {len(rows)} viewing activity rows")

            # Group by date for daily summaries
            by_date: dict[str, list[str]] = {}

            for row in rows:
                title_el = await row.query_selector(".title a, .col.title a, .title")
                date_el = await row.query_selector(".date, .col.date")

                title = await title_el.inner_text() if title_el else None
                date_str = await date_el.inner_text() if date_el else None

                if not title or not date_str:
                    continue

                # Clean up title (remove duplicate show name prefix)
                title = title.strip()
                by_date.setdefault(date_str.strip(), []).append(title)

            # Save refreshed cookies for next time
            fresh_cookies = await context.cookies()
            netflix_cookies = [c for c in fresh_cookies if "netflix" in c.get("domain", "")]
            if netflix_cookies:
                with open(COOKIE_FILE, "w") as f:
                    json.dump(netflix_cookies, f)

            await browser.close()
            await p.stop()

            # Convert to SeedItems (daily summaries)
            for date_str, titles in by_date.items():
                parsed_date = _parse_date(date_str)

                content_parts = [
                    f"# Netflix Viewing — {date_str}",
                    "",
                    f"**Episodes/films watched:** {len(titles)}",
                    "",
                ]

                # Group by show
                shows: dict[str, list[str]] = {}
                for t in titles:
                    if ": " in t:
                        parts = t.split(": ", 1)
                        show = parts[0]
                        episode = parts[1] if len(parts) > 1 else t
                    else:
                        show = t
                        episode = t
                    shows.setdefault(show, []).append(episode)

                for show, episodes in shows.items():
                    content_parts.append(f"**{show}**")
                    for ep in episodes:
                        content_parts.append(f"- {ep}")
                    content_parts.append("")

                topics = ["netflix", "tv", "watching"]
                # Detect binge watching
                if len(titles) >= 3:
                    topics.append("binge-watching")

                date_key = parsed_date.strftime("%Y-%m-%d") if parsed_date else date_str.replace("/", "-")

                items.append(SeedItem(
                    title=f"Netflix Viewing — {date_str}",
                    content="\n".join(content_parts),
                    source_url=f"netflix://daily/{date_key}",
                    topics=topics,
                    created_at=parsed_date,
                    metadata={
                        "episode_count": len(titles),
                        "shows": list(shows.keys()),
                    },
                    content_type="viewing_history",
                ))

                if len(items) >= limit:
                    break

        except Exception as e:
            logger.exception(f"Failed to scrape Netflix: {e}")

        return items

    def get_default_topics(self) -> list[str]:
        return ["netflix", "tv"]
