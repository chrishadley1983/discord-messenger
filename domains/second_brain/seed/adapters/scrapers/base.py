"""Base class for email link scrapers.

Each scraper defines how to find emails, extract links, and scrape
structured content from linked pages.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class ScrapedItem:
    """Structured content scraped from a linked page."""

    title: str
    content: str  # Formatted markdown
    url: str  # Canonical URL (dedup key)
    topics: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    order_date: Optional[datetime] = None


class BaseEmailLinkScraper(ABC):
    """Base class for email link scrapers.

    Subclasses define:
    - Which emails to search for (gmail_query)
    - How to extract links from email HTML (extract_links)
    - How to scrape each linked page (scrape_link)
    """

    name: str = "base"
    gmail_query: str = ""
    default_topics: list[str] = []
    needs_playwright: bool = True

    @abstractmethod
    def extract_links(self, email_html: str) -> list[str]:
        """Extract relevant URLs from email HTML body.

        Returns:
            List of canonical URLs to scrape.
        """
        pass

    @abstractmethod
    async def scrape_link(self, page, url: str) -> Optional[ScrapedItem]:
        """Scrape structured content from a single link.

        Args:
            page: Playwright Page object (or None if needs_playwright=False).
            url: The URL to scrape.

        Returns:
            ScrapedItem with structured content, or None if scrape failed.
        """
        pass

    def get_order_date(self, email: dict) -> Optional[datetime]:
        """Parse email date header into datetime.

        Default implementation handles common RFC email date formats.
        """
        date_str = email.get("date", "")
        if not date_str:
            return None

        for fmt in [
            "%a, %d %b %Y %H:%M:%S %z",
            "%d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S",
        ]:
            try:
                return datetime.strptime(date_str.split(" (")[0].strip(), fmt)
            except ValueError:
                continue
        return None

    async def setup(self):
        """Optional pre-scrape initialisation."""
        pass

    async def teardown(self):
        """Optional post-scrape cleanup."""
        pass
