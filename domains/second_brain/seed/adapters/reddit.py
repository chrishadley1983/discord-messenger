"""Reddit saved/interacted adapter.

Imports saved posts, upvoted content, and commented threads from Reddit
using cookie auth extracted from the Chrome CDP session (port 9222).

No API key or praw required — uses Reddit's .json endpoints with session cookies.

Requires:
  - Chrome running with --remote-debugging-port=9222
  - Reddit logged in within that Chrome session
"""

import asyncio
import time
from datetime import datetime, timezone

from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter

CDP_ENDPOINT = "http://localhost:9222"
REQUEST_DELAY = 2  # seconds between Reddit API calls


def _extract_reddit_cookies() -> dict[str, str]:
    """Extract Reddit cookies from the Chrome CDP session."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_ENDPOINT)
        ctx = browser.contexts[0]
        cookies = ctx.cookies(["https://www.reddit.com"])
        return {c["name"]: c["value"] for c in cookies}


def _build_session(cookies: dict[str, str]):
    """Build a requests session with Reddit cookies."""
    import requests

    session = requests.Session()
    for name, value in cookies.items():
        session.cookies.set(name, value, domain=".reddit.com")
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
    )
    return session


def _get_username(session) -> str | None:
    """Get the logged-in Reddit username."""
    resp = session.get("https://www.reddit.com/api/me.json", params={"raw_json": 1})
    if resp.status_code == 200:
        return resp.json().get("data", {}).get("name")
    return None


def _fetch_listing(session, url: str, limit: int = 100) -> list[dict]:
    """Fetch a paginated Reddit listing, respecting rate limits."""
    items = []
    after = None

    while len(items) < limit:
        params = {"limit": min(100, limit - len(items)), "raw_json": 1}
        if after:
            params["after"] = after

        resp = session.get(url, params=params)

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 60))
            logger.warning(f"Reddit rate limited, waiting {retry_after}s")
            time.sleep(retry_after)
            continue

        if resp.status_code != 200:
            logger.error(f"Reddit API error {resp.status_code}: {resp.text[:200]}")
            break

        data = resp.json()
        children = data.get("data", {}).get("children", [])
        if not children:
            break

        items.extend(children)
        after = data.get("data", {}).get("after")
        if not after:
            break

        time.sleep(REQUEST_DELAY)

    return items


@register_adapter
class RedditAdapter(SeedAdapter):
    """Import saved, upvoted, and commented Reddit posts via cookie auth."""

    name = "reddit-saved"
    description = "Saved posts, upvotes, and comments from Reddit"
    source_system = "seed:reddit"

    def get_default_topics(self) -> list[str]:
        return ["reddit"]

    async def validate(self) -> tuple[bool, str]:
        # Check Chrome CDP is reachable
        try:
            import requests as _req
            resp = _req.get(f"{CDP_ENDPOINT}/json/version", timeout=5)
            if resp.status_code != 200:
                return False, f"Chrome CDP not responding on {CDP_ENDPOINT}"
        except Exception:
            return False, f"Chrome CDP not reachable on {CDP_ENDPOINT}"

        # Check we can get Reddit cookies
        try:
            cookies = await asyncio.to_thread(_extract_reddit_cookies)
            if "reddit_session" not in cookies:
                return False, "No reddit_session cookie — log into Reddit in Chrome CDP browser"
        except Exception as e:
            return False, f"Failed to extract Reddit cookies: {e}"

        return True, ""

    async def fetch(self, limit: int = 50) -> list[SeedItem]:
        items: list[SeedItem] = []

        try:
            # Extract fresh cookies from CDP
            cookies = await asyncio.to_thread(_extract_reddit_cookies)
            session = _build_session(cookies)
            username = await asyncio.to_thread(_get_username, session)

            if not username:
                logger.error("Reddit: could not determine username from cookies")
                return items

            logger.info(f"Reddit: logged in as {username}")

            # Allocate limits across the three sources
            saved_limit = max(limit // 2, 10)
            upvoted_limit = max(limit // 4, 5)
            comments_limit = max(limit // 4, 5)

            # Saved posts
            saved_url = f"https://www.reddit.com/user/{username}/saved.json"
            saved_raw = await asyncio.to_thread(_fetch_listing, session, saved_url, saved_limit)
            for raw in saved_raw:
                item = self._to_seed_item(raw, source="saved")
                if item:
                    items.append(item)

            # Upvoted posts (only high-score ones)
            if len(items) < limit:
                upvoted_url = f"https://www.reddit.com/user/{username}/upvoted.json"
                upvoted_raw = await asyncio.to_thread(_fetch_listing, session, upvoted_url, upvoted_limit)
                for raw in upvoted_raw:
                    score = raw.get("data", {}).get("score", 0)
                    if score >= 10:
                        item = self._to_seed_item(raw, source="upvoted")
                        if item:
                            items.append(item)

            # Recent comments
            if len(items) < limit:
                comments_url = f"https://www.reddit.com/user/{username}/comments.json"
                comments_raw = await asyncio.to_thread(_fetch_listing, session, comments_url, comments_limit)
                for raw in comments_raw:
                    item = self._comment_to_seed_item(raw)
                    if item:
                        items.append(item)

        except Exception as e:
            logger.error(f"Reddit fetch failed: {e}")

        logger.info(f"Fetched {len(items)} Reddit items")
        return items[:limit]

    def _to_seed_item(self, raw: dict, source: str = "saved") -> SeedItem | None:
        """Convert a Reddit listing child to a SeedItem."""
        try:
            kind = raw.get("kind", "")
            d = raw.get("data", {})

            if kind == "t3":
                # Submission (post)
                return self._post_to_seed_item(d, source)
            elif kind == "t1":
                # Comment
                return self._comment_data_to_seed_item(d)
            return None
        except Exception as e:
            logger.warning(f"Failed to convert Reddit item: {e}")
            return None

    def _post_to_seed_item(self, d: dict, source: str = "saved") -> SeedItem | None:
        """Convert a Reddit post data dict to a SeedItem."""
        title = d.get("title", "")
        if not title:
            return None

        selftext = d.get("selftext", "") or ""
        subreddit = d.get("subreddit", "unknown")
        permalink = f"https://reddit.com{d.get('permalink', '')}"
        score = d.get("score", 0)
        created_utc = d.get("created_utc", 0)
        created = datetime.fromtimestamp(created_utc, tz=timezone.utc) if created_utc else None

        content_parts = [f"# {title}", ""]
        content_parts.append(f"**Subreddit:** r/{subreddit}")
        content_parts.append(f"**Score:** {score}")
        content_parts.append(f"**Source:** {source}")
        content_parts.append("")

        if selftext:
            content_parts.append(selftext[:3000])
            content_parts.append("")

        # Include URL if it's a link post
        url = d.get("url", "")
        if url and not url.startswith("https://www.reddit.com"):
            content_parts.append(f"**Link:** {url}")

        topics = ["reddit", f"r-{subreddit.lower()}"]

        return SeedItem(
            title=f"Reddit: {title[:60]}",
            content="\n".join(content_parts),
            source_url=permalink,
            source_id=d.get("name", d.get("id", "")),
            topics=topics,
            created_at=created,
            content_type="social_save",
        )

    def _comment_data_to_seed_item(self, d: dict) -> SeedItem | None:
        """Convert a Reddit comment data dict to a SeedItem."""
        body = d.get("body", "")
        if len(body) < 50:
            return None

        subreddit = d.get("subreddit", "unknown")
        permalink = f"https://reddit.com{d.get('permalink', '')}"
        created_utc = d.get("created_utc", 0)
        created = datetime.fromtimestamp(created_utc, tz=timezone.utc) if created_utc else None

        # Get parent post title from link_title
        post_title = d.get("link_title", "Unknown")

        content = f"""# Comment on: {post_title}

**Subreddit:** r/{subreddit}
**My comment:**

{body[:2000]}
"""

        return SeedItem(
            title=f"Reddit Comment: {post_title[:50]}",
            content=content,
            source_url=permalink,
            source_id=d.get("name", d.get("id", "")),
            topics=["reddit", f"r-{subreddit.lower()}"],
            created_at=created,
            content_type="discussion",
        )

    def _comment_to_seed_item(self, raw: dict) -> SeedItem | None:
        """Convert a raw listing child comment to SeedItem."""
        return self._comment_data_to_seed_item(raw.get("data", {}))
