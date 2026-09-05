"""Source fetchers for the merged daily newsletter (skill: newsletter).

Replaces the Grok-dependent morning-briefing pipeline with a resilient
multi-source stack (verified working 2026-07-02):

- AI news:      SerpAPI google_news (real URLs) -> Google News RSS fallback
- Claude Code:  HN Algolia search (free, unlimited)
- Community:    Reddit RSS (.rss works; .json is IP-blocked) + optional Grok x_search
- Tech/UK/F1:   existing RSS feeds via domains.news.services.fetch_feed
- YouTube:      SerpAPI youtube engine (rotating categories) + Supabase dedup

Grok x_search is attempted opportunistically and skipped gracefully when the
xAI account is out of credits (403 permission-denied since ~mid-June 2026).

All fetched items are hard-filtered against URLs already posted to the
channel (data/news_history.jsonl) so repeats are structurally impossible.

SerpAPI free tier is 250 searches/month; this module uses at most 4/day
(2 google_news + 2 youtube) ~= 120/month.
"""

import asyncio
import os
import re
import json
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from logger import logger

UK_TZ = ZoneInfo("Europe/London")
DATA_DIR = Path(__file__).parent.parent.parent / "data"
NEWS_HISTORY_PATH = DATA_DIR / "news_history.jsonl"

SERPAPI_KEY = os.getenv("SERPAPI_KEY")

# SEO aggregator/junk domains that kept outranking primary sources in the
# old Grok pipeline. Filtered in code so the LLM never sees them.
BANNED_DOMAINS = {
    "buildfastwithai.com",
    "aistartupedge.com",
    "neuralbuddies.com",
    "unrot.co",
    "aitntnews.com",
    "tygartmedia.com",
    "memeburn.com",
    "facebook.com",
    "llm-stats.com",
}

# YouTube categories — documentaries run EVERY day (Chris wants at least one
# high-quality documentary daily, highlighted); the rest rotate 2/day.
YOUTUBE_CATEGORIES = {
    "lego_investing": {"name": "Lego Investing", "query": "lego investing retired sets value"},
    "bricklink": {"name": "Bricklink Stores", "query": "bricklink store selling tips"},
    "claude_code": {"name": "Claude Code", "query": "claude code tutorial"},
    "ai_news": {"name": "AI News", "query": "AI news this week"},
    "documentaries": {"name": "Documentaries", "query": "full documentary"},
}

# Long-form threshold for the documentary pick — filters out listicles,
# trailers and shorts that dominate generic documentary searches.
DOCUMENTARY_MIN_MINUTES = 25

# Community subreddits: AI/Claude plus Chris's other interests (Factorio, FIRE).
# Fetched sequentially with a stagger — parallel hits trip Reddit's 429 limiter.
REDDIT_SUBS = ["ClaudeAI", "ClaudeCode", "LocalLLaMA", "factorio", "FIREUK", "FinancialIndependence"]

# Bluesky public search — free, no auth, replaces Grok x_search for community
# buzz. NB: must be api.bsky.app; the public.api.bsky.app edge 403s this IP.
BLUESKY_QUERIES = ["claude code", "anthropic claude"]

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


# ---------------------------------------------------------------------------
# URL normalisation + posted-history dedup
# ---------------------------------------------------------------------------

_TRACKING_PARAMS = re.compile(r"^(utm_|at_|fbclid|gclid|ref$|cmpid)")


def normalize_url(url: str) -> str:
    """Normalise a URL for dedup comparison (strip tracking params etc.)."""
    try:
        url = url.strip().strip("<>")
        parsed = urllib.parse.urlsplit(url)
        host = parsed.netloc.lower().removeprefix("www.")
        params = [
            (k, v) for k, v in urllib.parse.parse_qsl(parsed.query)
            if not _TRACKING_PARAMS.match(k.lower())
        ]
        query = urllib.parse.urlencode(params)
        path = parsed.path.rstrip("/")
        return f"{host}{path}" + (f"?{query}" if query else "")
    except Exception:
        return url


def load_posted_urls(days: int = 10) -> set[str]:
    """URLs already posted to the channel (from news_history.jsonl)."""
    if not NEWS_HISTORY_PATH.exists():
        return set()

    cutoff = datetime.now(UK_TZ) - timedelta(days=days)
    urls: set[str] = set()
    try:
        with open(NEWS_HISTORY_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    ts = datetime.fromisoformat(entry["timestamp"])
                    if ts < cutoff:
                        continue
                    for m in re.finditer(r"\((<?https?://[^)>\s]+>?)\)", entry.get("response", "")):
                        urls.add(normalize_url(m.group(1)))
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
    except Exception as e:
        logger.debug(f"Newsletter posted-URL load failed: {e}")
    return urls


def _is_banned(url: str) -> bool:
    try:
        host = urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")
        return any(host == d or host.endswith("." + d) for d in BANNED_DOMAINS)
    except Exception:
        return False


def _dedupe_filter(items: list[dict], posted: set[str], seen: set[str]) -> list[dict]:
    """Drop items with banned, already-posted, or already-seen-this-run URLs."""
    out = []
    for item in items:
        url = item.get("url", "")
        if not url or _is_banned(url):
            continue
        norm = normalize_url(url)
        if norm in posted or norm in seen:
            continue
        seen.add(norm)
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# Source fetchers
# ---------------------------------------------------------------------------

async def fetch_serpapi_news(query: str, max_items: int = 10) -> list[dict]:
    """AI news via SerpAPI google_news engine (real URLs, clean sources)."""
    if not SERPAPI_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get("https://serpapi.com/search.json", params={
                "engine": "google_news", "q": query, "gl": "gb", "hl": "en",
                "api_key": SERPAPI_KEY,
            })
            resp.raise_for_status()
            data = resp.json()
        items = []
        for r in data.get("news_results", [])[:max_items * 2]:
            # top-level results or nested "stories" clusters
            candidates = r.get("stories", [r])
            for c in candidates[:2]:
                if c.get("link") and c.get("title"):
                    items.append({
                        "title": c["title"],
                        "url": c["link"],
                        "source": (c.get("source") or {}).get("name", ""),
                        "published": c.get("date", ""),
                    })
        logger.info(f"SerpAPI google_news '{query[:40]}': {len(items)} items")
        return items[:max_items]
    except Exception as e:
        logger.warning(f"SerpAPI google_news failed for '{query[:40]}': {e}")
        return []


async def fetch_google_news_rss(query: str, max_items: int = 10) -> list[dict]:
    """Free fallback: Google News RSS search (redirect URLs, still clickable)."""
    try:
        q = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={q}&hl=en-GB&gl=GB&ceid=GB:en"
        async with httpx.AsyncClient(timeout=30, headers=UA) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        import feedparser
        feed = feedparser.parse(resp.text)
        items = []
        for e in feed.entries[:max_items]:
            title = e.get("title", "")
            # Google News titles end " - Source"
            source = ""
            if " - " in title:
                title, source = title.rsplit(" - ", 1)
            items.append({
                "title": title,
                "url": e.get("link", ""),
                "source": source or (e.get("source", {}) or {}).get("title", ""),
                "published": e.get("published", ""),
            })
        logger.info(f"GoogleNews RSS '{query[:40]}': {len(items)} items")
        return items
    except Exception as e:
        logger.warning(f"GoogleNews RSS failed for '{query[:40]}': {e}")
        return []


async def fetch_hn(query: str, hours: int = 36, min_points: int = 15,
                   max_items: int = 8) -> list[dict]:
    """Hacker News stories via Algolia (free)."""
    try:
        since = int((datetime.now().timestamp()) - hours * 3600)
        async with httpx.AsyncClient(timeout=30) as client:
            # NB: must be search_by_date — the relevance `search` index
            # rejects `points` in numericFilters (400).
            resp = await client.get(
                "https://hn.algolia.com/api/v1/search_by_date",
                params={
                    "query": query, "tags": "story",
                    "numericFilters": f"created_at_i>{since},points>{min_points}",
                    "hitsPerPage": max_items,
                })
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
        items = []
        for h in hits:
            story_url = h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}"
            items.append({
                "title": h.get("title", ""),
                "url": story_url,
                "source": "Hacker News",
                "published": h.get("created_at", ""),
                "context": f"{h.get('points', 0)} points, {h.get('num_comments', 0)} comments — "
                           f"discussion: https://news.ycombinator.com/item?id={h.get('objectID')}",
                "score": h.get("points", 0),
            })
        logger.info(f"HN Algolia '{query}': {len(items)} items")
        return items
    except Exception as e:
        logger.warning(f"HN Algolia failed for '{query}': {e}")
        return []


async def fetch_reddit_rss(subreddit: str, max_items: int = 6) -> list[dict]:
    """Top posts of the day via Reddit RSS (.rss is NOT IP-blocked, .json is)."""
    try:
        url = f"https://www.reddit.com/r/{subreddit}/top/.rss?t=day&limit={max_items}"
        async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "peterbot-digest/1.0"}) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        import feedparser
        feed = feedparser.parse(resp.text)
        items = []
        for e in feed.entries[:max_items]:
            items.append({
                "title": e.get("title", ""),
                "url": e.get("link", ""),
                "subreddit": f"r/{subreddit}",
                "source": f"r/{subreddit}",
                "published": e.get("updated", ""),
            })
        logger.info(f"Reddit RSS r/{subreddit}: {len(items)} items")
        return items
    except Exception as e:
        logger.warning(f"Reddit RSS r/{subreddit} failed: {e}")
        return []


async def fetch_reddit_all(subreddits: list[str]) -> list[list[dict]]:
    """Fetch several subreddits sequentially with a stagger.

    Reddit's RSS endpoints 429 when hit in parallel from one IP; ~2s gaps
    keep a 6-sub daily fetch comfortably under the limiter.
    """
    out = []
    for i, sub in enumerate(subreddits):
        if i:
            await asyncio.sleep(3)
        items = await fetch_reddit_rss(sub)
        if not items:
            # one retry after a longer pause — 429s are transient
            await asyncio.sleep(8)
            items = await fetch_reddit_rss(sub)
        out.append(items)
    return out


async def fetch_bluesky(query: str, max_items: int = 8, min_likes: int = 3) -> list[dict]:
    """Community posts via Bluesky's public search API (free, no auth)."""
    try:
        async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "peterbot-newsletter/1.0"}) as client:
            resp = await client.get(
                "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts",
                params={"q": query, "sort": "top", "limit": 25})
            resp.raise_for_status()
            posts = resp.json().get("posts", [])
        # createdAt is UTC ISO ("...Z"); compare on a matching UTC prefix
        cutoff = (datetime.now(ZoneInfo("UTC")) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S")
        items = []
        for p in posts:
            record = p.get("record", {}) or {}
            if (record.get("createdAt") or "")[:19] < cutoff:
                continue
            likes = p.get("likeCount", 0) or 0
            if likes < min_likes:
                continue
            handle = (p.get("author", {}) or {}).get("handle", "")
            rkey = (p.get("uri", "") or "").split("/")[-1]
            if not handle or not rkey:
                continue
            text = (record.get("text", "") or "").replace("\n", " ").strip()
            items.append({
                "title": text[:150],
                "url": f"https://bsky.app/profile/{handle}/post/{rkey}",
                "handle": f"@{handle}",
                "source": "Bluesky",
                "likes": likes,
            })
        items.sort(key=lambda i: i["likes"], reverse=True)
        logger.info(f"Bluesky '{query}': {len(items)} items")
        return items[:max_items]
    except Exception as e:
        logger.warning(f"Bluesky search failed for '{query}': {e}")
        return []


async def fetch_x_posts() -> tuple[list[dict], str]:
    """Attempt Grok x_search; degrade gracefully when credits are exhausted."""
    try:
        from config import GROK_API_KEY
        if not GROK_API_KEY:
            return [], "not configured"
        from jobs.morning_briefing import _search_x
        now = datetime.now(UK_TZ)
        posts = await _search_x(
            "Claude AI OR Anthropic OR Claude Code",
            (now - timedelta(days=2)).strftime("%Y-%m-%d"),
            now.strftime("%Y-%m-%d"),
        )
        if posts:
            return posts[:10], "ok"
        return [], "no results (likely xAI credits exhausted)"
    except Exception as e:
        logger.warning(f"Grok x_search unavailable: {e}")
        return [], f"unavailable ({str(e)[:60]})"


async def _is_uk_playable(video_id: str) -> bool:
    """Check a video actually plays from the UK (this host's region).

    Scrapes the watch page's playabilityStatus — catches region blocks like
    FRONTLINE PBS (US-only), private/removed videos, etc. Fails OPEN on
    network errors so a YouTube hiccup doesn't empty the section.
    """
    try:
        async with httpx.AsyncClient(timeout=25, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
            "Accept-Language": "en-GB,en;q=0.9",
        }) as client:
            resp = await client.get(f"https://www.youtube.com/watch?v={video_id}&hl=en-GB&gl=GB")
        m = re.search(r'"playabilityStatus":\{"status":"(\w+)"', resp.text)
        if not m:
            return True
        playable = m.group(1) in ("OK", "LIVE_STREAM_OFFLINE")
        if not playable:
            logger.info(f"YouTube {video_id} not playable in UK ({m.group(1)}) — skipped")
        return playable
    except Exception as e:
        logger.debug(f"UK playability check failed for {video_id}: {e}")
        return True


def _length_minutes(length_str: str) -> float:
    """Parse a SerpAPI video length like '1:23:45' or '12:34' into minutes."""
    try:
        parts = [int(p) for p in str(length_str).split(":")]
        if len(parts) == 3:
            return parts[0] * 60 + parts[1] + parts[2] / 60
        if len(parts) == 2:
            return parts[0] + parts[1] / 60
    except (ValueError, AttributeError):
        pass
    return 0.0


async def fetch_youtube_category(category_key: str, max_items: int = 6) -> list[dict]:
    """YouTube search via SerpAPI youtube engine, this-week uploads.

    Documentaries additionally require long-form length (>=25 min) so the
    daily documentary pick is a real film, not a trailer or listicle.
    """
    if not SERPAPI_KEY:
        return []
    cfg = YOUTUBE_CATEGORIES[category_key]
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get("https://serpapi.com/search.json", params={
                "engine": "youtube", "search_query": cfg["query"],
                "sp": "EgIIAw==",  # upload date: this week
                "api_key": SERPAPI_KEY,
            })
            resp.raise_for_status()
            data = resp.json()
        items = []
        for v in data.get("video_results", []):
            link = v.get("link", "")
            m = re.search(r"v=([a-zA-Z0-9_-]{11})", link)
            if not m:
                continue
            minutes = _length_minutes(v.get("length", ""))
            if category_key == "documentaries" and minutes < DOCUMENTARY_MIN_MINUTES:
                continue
            items.append({
                "video_id": m.group(1),
                "title": v.get("title", ""),
                "url": f"https://youtube.com/watch?v={m.group(1)}",
                "channel_name": (v.get("channel") or {}).get("name", ""),
                "published": v.get("published_date", ""),
                "views": v.get("views"),
                "length_minutes": round(minutes) if minutes else None,
            })
            if len(items) >= max_items * 2:
                break
        logger.info(f"SerpAPI youtube '{cfg['query']}': {len(items)} items")
        return items
    except Exception as e:
        logger.warning(f"SerpAPI youtube failed for {category_key}: {e}")
        return []


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------

async def get_newsletter_data() -> dict[str, Any]:
    """Aggregate all newsletter sections with URL-level dedup."""
    now = datetime.now(UK_TZ)
    posted = load_posted_urls(days=10)
    seen: set[str] = set()
    status: dict[str, str] = {}

    # RSS feeds reuse the existing news domain service
    from domains.news.services import fetch_feed

    # Documentaries run every day (daily highlighted pick); 2 more categories
    # rotate to stay inside SerpAPI quota (3 youtube + 2 news = 5 searches/day)
    rotating = [k for k in YOUTUBE_CATEGORIES if k != "documentaries"]
    day_idx = now.toordinal() * 2
    today_cats = ["documentaries",
                  rotating[day_idx % len(rotating)],
                  rotating[(day_idx + 1) % len(rotating)]]

    results = await asyncio.gather(
        fetch_serpapi_news('Anthropic OR "Claude AI" OR "Claude Code"'),
        fetch_serpapi_news('OpenAI OR "Google DeepMind" OR "artificial intelligence" latest'),
        fetch_hn("anthropic", min_points=30),
        fetch_hn("claude", min_points=30),
        fetch_hn('"claude code" OR "MCP"', min_points=10),
        fetch_reddit_all(REDDIT_SUBS),
        *[fetch_bluesky(q) for q in BLUESKY_QUERIES],
        fetch_x_posts(),
        fetch_feed("tech", limit=6),
        fetch_feed("uk", limit=5),
        fetch_feed("football", limit=5),
        fetch_feed("cricket", limit=4),
        fetch_feed("f1", limit=2),
        *[fetch_youtube_category(c) for c in today_cats],
        return_exceptions=True,
    )

    def safe(idx, default):
        r = results[idx]
        if isinstance(r, Exception):
            logger.warning(f"Newsletter source {idx} raised: {r}")
            return default
        return r

    serp_anthropic = safe(0, [])
    serp_industry = safe(1, [])
    hn_anthropic = safe(2, [])
    hn_claude = safe(3, [])
    hn_cc = safe(4, [])
    reddit_lists = safe(5, [])
    nb = len(BLUESKY_QUERIES)
    bsky_lists = [safe(6 + i, []) for i in range(nb)]
    x_posts, x_status = safe(6 + nb, ([], "error"))
    rss_tech = safe(7 + nb, {}).get("headlines", [])
    rss_uk = safe(8 + nb, {}).get("headlines", [])
    rss_football = safe(9 + nb, {}).get("headlines", [])
    rss_cricket = safe(10 + nb, {}).get("headlines", [])
    rss_f1 = safe(11 + nb, {}).get("headlines", [])
    yt_lists = [safe(12 + nb + i, []) for i in range(len(today_cats))]

    # SerpAPI news fallback -> free Google News RSS
    if not serp_anthropic and not serp_industry:
        status["google_news"] = "SerpAPI unavailable — using Google News RSS fallback"
        serp_anthropic, serp_industry = await asyncio.gather(
            fetch_google_news_rss('Anthropic OR "Claude AI" when:1d'),
            fetch_google_news_rss('"artificial intelligence" OR OpenAI when:1d'),
        )

    # --- AI news + Claude Code ---
    ai_news = _dedupe_filter(serp_anthropic + serp_industry + hn_anthropic, posted, seen)
    claude_code = _dedupe_filter(hn_cc + hn_claude, posted, seen)
    status["ai_news"] = "ok" if ai_news else "no fresh items"

    # --- Community (Reddit + Bluesky; Grok/X is an opportunistic bonus) ---
    reddit_items = _dedupe_filter([i for lst in reddit_lists for i in lst], posted, seen)
    bluesky_items = _dedupe_filter([i for lst in bsky_lists for i in lst], posted, seen)
    x_items = _dedupe_filter(x_posts, posted, seen) if x_posts else []
    status["reddit"] = "ok" if reddit_items else "no fresh items"
    status["bluesky"] = "ok" if bluesky_items else "no fresh items"
    # X is only a failure worth reporting if the whole community section is dry
    if x_items:
        status["x"] = "ok"
    elif reddit_items or bluesky_items:
        status["x"] = "skipped (community covered by Reddit/Bluesky)"
    else:
        status["x"] = x_status

    # --- RSS sections (also deduped so day-old repeats vanish) ---
    def rss_items(headlines):
        return _dedupe_filter([
            {"title": h.get("title", ""), "url": h.get("url", ""),
             "source": h.get("source", ""), "published": h.get("published", "")}
            for h in headlines
        ], posted, seen)

    tech = rss_items(rss_tech)
    uk = rss_items(rss_uk)
    # Sport: cricket & football led, F1 only as a minor extra
    sport = rss_items(rss_football) + rss_items(rss_cricket) + rss_items(rss_f1)

    # --- YouTube (Supabase shown-video dedup + real titles) ---
    youtube: list[dict] = []
    try:
        from jobs.youtube_feed import get_shown_video_ids, mark_video_shown, _fetch_titles_for_videos
        shown = await get_shown_video_ids()
        for cat_key, vids in zip(today_cats, yt_lists):
            per_cat = 4 if cat_key == "documentaries" else 3
            candidates = [v for v in vids if v["video_id"] not in shown][:per_cat * 2]
            if not candidates:
                continue
            # Drop region-blocked videos (checked from this UK host)
            playable = await asyncio.gather(
                *[_is_uk_playable(v["video_id"]) for v in candidates])
            fresh = [v for v, ok in zip(candidates, playable) if ok][:per_cat]
            if not fresh:
                continue
            await _fetch_titles_for_videos(fresh)
            for v in fresh:
                await mark_video_shown(v, cat_key, v.get("title", ""))
            youtube.append({
                "category": YOUTUBE_CATEGORIES[cat_key]["name"],
                "videos": fresh,
            })
        status["youtube"] = "ok" if youtube else "no fresh videos today"
        if not any(y["category"] == "Documentaries" for y in youtube):
            status["documentary_pick"] = "no fresh long-form documentary found today"
    except Exception as e:
        logger.warning(f"YouTube section failed: {e}")
        status["youtube"] = f"error ({str(e)[:60]})"

    total = (len(ai_news) + len(claude_code) + len(reddit_items) + len(bluesky_items)
             + len(x_items) + len(tech) + len(uk) + len(sport)
             + sum(len(y["videos"]) for y in youtube))
    logger.info(
        f"Newsletter fetch: {len(ai_news)} AI, {len(claude_code)} CC, "
        f"{len(reddit_items)} reddit, {len(bluesky_items)} bsky, {len(x_items)} X, "
        f"{len(tech)} tech, {len(uk)} UK, {len(sport)} sport, "
        f"{sum(len(y['videos']) for y in youtube)} YT "
        f"({total} total after dedup vs {len(posted)} posted URLs)"
    )

    return {
        "ai_news": ai_news[:12],
        "claude_code": claude_code[:8],
        "community": {"reddit": reddit_items[:12], "bluesky": bluesky_items[:8], "x": x_items[:8]},
        "tech": tech[:6],
        "uk": uk[:5],
        "sport": sport[:10],
        "youtube": youtube,
        "source_status": status,
        "fetch_time": now.strftime("%Y-%m-%d %H:%M"),
    }
