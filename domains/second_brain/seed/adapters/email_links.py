"""Email link scraper adapter.

Orchestrates email-based link scraping: finds emails matching
source-specific Gmail queries, extracts URLs, scrapes each linked
page for structured content, and yields SeedItems.

Manages a shared Playwright browser for JS-rendered sites.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

import httpx

from logger import logger
from ...config import HADLEY_API_BASE
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter
from .scrapers import GoustoRecipeScraper, AirbnbBookingScraper
from .scrapers.base import BaseEmailLinkScraper

# All registered scrapers
SCRAPERS: list[BaseEmailLinkScraper] = [
    GoustoRecipeScraper(),
    AirbnbBookingScraper(),
]


@register_adapter
class EmailLinkScraperAdapter(SeedAdapter):
    """Scrape structured content from links found in emails."""

    name = "email-link-scraper"
    description = "Extract and scrape links from emails (Gousto recipes, Airbnb bookings, etc.)"
    source_system = "seed:email-links"

    def __init__(self, config: dict[str, Any] = None):
        super().__init__(config)
        self.api_base = config.get("api_base", HADLEY_API_BASE) if config else HADLEY_API_BASE
        self.years_back = config.get("years_back", 0.1) if config else 0.1
        self.per_scraper_limit = config.get("per_scraper_limit", 10) if config else 10

    async def validate(self) -> tuple[bool, str]:
        """Check Gmail API is reachable."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_base}/gmail/labels",
                    timeout=5,
                )
                if response.status_code == 200:
                    return True, ""
                return False, f"Gmail API returned {response.status_code}"
        except Exception as e:
            return False, f"Cannot reach Gmail API: {e}"

    async def fetch(self, limit: int = 100) -> list[SeedItem]:
        """Fetch structured content by scraping links from emails."""
        items: list[SeedItem] = []
        after_date = (datetime.now() - timedelta(days=365 * self.years_back)).strftime("%Y/%m/%d")

        # Launch Playwright browser once for all scrapers
        browser = None
        playwright_ctx = None
        try:
            from playwright.async_api import async_playwright
            playwright_ctx = await async_playwright().start()
            browser = await playwright_ctx.chromium.launch(headless=True)
            logger.info("Playwright browser launched for email link scraping")
        except ImportError:
            logger.warning("Playwright not installed — JS-rendered scrapers will be skipped")
        except Exception as e:
            logger.warning(f"Failed to launch Playwright: {e}")

        async with httpx.AsyncClient(timeout=120) as client:
            for scraper in SCRAPERS:
                if len(items) >= limit:
                    break

                if scraper.needs_playwright and not browser:
                    logger.info(f"Skipping {scraper.name} (needs Playwright)")
                    continue

                try:
                    await scraper.setup()
                    scraper_items = await self._run_scraper(
                        client=client,
                        scraper=scraper,
                        browser=browser,
                        after_date=after_date,
                        limit=self.per_scraper_limit,
                    )
                    items.extend(scraper_items)
                    logger.info(f"Scraper {scraper.name}: {len(scraper_items)} items")
                except Exception as e:
                    logger.error(f"Scraper {scraper.name} failed: {e}")
                finally:
                    await scraper.teardown()

        # Cleanup Playwright
        if browser:
            await browser.close()
        if playwright_ctx:
            await playwright_ctx.stop()

        logger.info(f"Email link scraper total: {len(items)} items")
        return items[:limit]

    async def _run_scraper(
        self,
        client: httpx.AsyncClient,
        scraper: BaseEmailLinkScraper,
        browser,
        after_date: str,
        limit: int,
    ) -> list[SeedItem]:
        """Run a single scraper: search emails, extract links, scrape pages."""
        items: list[SeedItem] = []

        # Search Gmail
        query = f"{scraper.gmail_query} after:{after_date}"
        logger.info(f"[{scraper.name}] Searching: {query}")

        response = await client.get(
            f"{self.api_base}/gmail/search",
            params={"q": query, "limit": limit * 2},  # Fetch extra to account for emails with no links
            timeout=60,
        )

        if response.status_code != 200:
            logger.warning(f"[{scraper.name}] Gmail search failed: {response.status_code}")
            return items

        emails = response.json().get("emails", [])
        logger.info(f"[{scraper.name}] Found {len(emails)} emails")

        # Collect all unique links across emails, track which email each came from
        link_email_map: dict[str, dict] = {}  # url -> email dict

        for email in emails:
            email_id = email.get("id")
            if not email_id:
                continue

            # Fetch full email body
            body_resp = await client.get(
                f"{self.api_base}/gmail/get",
                params={"id": email_id},
                timeout=30,
            )
            if body_resp.status_code != 200:
                continue

            email_body = body_resp.json().get("body", "")
            if not email_body:
                continue

            # Store date on email dict for later use
            email["_body"] = email_body

            # Extract links
            links = scraper.extract_links(email_body)
            for link in links:
                if link not in link_email_map:
                    link_email_map[link] = email

        logger.info(f"[{scraper.name}] Extracted {len(link_email_map)} unique links")

        if not link_email_map:
            return items

        # Scrape each link (sequentially to be respectful to target sites)
        page = await browser.new_page() if browser else None
        try:
            for url, email in list(link_email_map.items())[:limit]:
                scraped = await scraper.scrape_link(page, url)
                if not scraped:
                    continue

                order_date = scraped.order_date or scraper.get_order_date(email)

                # Build dedup key — for Airbnb, include booking date
                if hasattr(scraper, "_make_dedup_key"):
                    source_url = scraper._make_dedup_key(scraped.url, order_date)
                else:
                    source_url = scraped.url

                # Add order date to content if available
                if order_date and "Ordered:" not in scraped.content:
                    # Insert order date after the first line
                    lines = scraped.content.split("\n", 1)
                    if len(lines) == 2:
                        scraped.content = (
                            f"{lines[0]}\n"
                            f"**Ordered:** {order_date.strftime('%Y-%m-%d')}\n"
                            f"{lines[1]}"
                        )

                items.append(SeedItem(
                    title=scraped.title,
                    content=scraped.content,
                    source_url=source_url,
                    source_id=scraped.url,
                    topics=list(set(scraper.default_topics + scraped.topics)),
                    created_at=order_date,
                    metadata=scraped.metadata,
                ))
        finally:
            if page:
                await page.close()

        return items

    def get_default_topics(self) -> list[str]:
        return ["email-link"]
