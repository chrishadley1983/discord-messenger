"""RSS feed fetching and article extraction."""

import feedparser
import httpx
from bs4 import BeautifulSoup

from logger import logger
from ..config import SOURCES


async def fetch_feed(category: str, limit: int = 10) -> list[dict]:
    """Fetch headlines from RSS feeds by category."""
    try:
        if category == "all":
            sources = []
            for cat_sources in SOURCES.values():
                sources.extend(cat_sources)
        else:
            sources = SOURCES.get(category, [])

        if not sources:
            return {"error": f"Unknown category: {category}", "headlines": []}

        headlines = []

        for source_name, url in sources:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:limit // len(sources) + 1]:
                    headlines.append({
                        "title": entry.get("title", "No title"),
                        "url": entry.get("link", ""),
                        "source": source_name,
                        "published": entry.get("published", "")
                    })
            except Exception as e:
                logger.warning(f"Failed to fetch from {source_name}: {e}")

        # Sort by freshness and limit
        headlines = headlines[:limit]

        logger.info(f"Fetched {len(headlines)} headlines for category '{category}'")
        return {"headlines": headlines}
    except Exception as e:
        logger.error(f"Feed fetch error: {e}")
        return {"error": str(e), "headlines": []}


async def fetch_article(url: str) -> dict:
    """Fetch and extract text content from an article URL."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            response = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Remove script, style, nav, footer elements
        for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
            element.decompose()

        # Try to find article content
        article = soup.find("article")
        if article:
            text = article.get_text(separator="\n", strip=True)
        else:
            # Fall back to body
            body = soup.find("body")
            text = body.get_text(separator="\n", strip=True) if body else ""

        # Clean up whitespace
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        text = "\n".join(lines)

        # Truncate if too long
        max_chars = 4000
        if len(text) > max_chars:
            text = text[:max_chars] + "...[truncated]"

        logger.info(f"Fetched article: {url[:50]}...")
        return {"content": text, "url": url}
    except Exception as e:
        logger.error(f"Article fetch error: {e}")
        return {"error": str(e), "content": None, "url": url}
