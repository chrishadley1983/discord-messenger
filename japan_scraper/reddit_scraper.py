"""Reddit scraper for Japan travel recommendations via .json API."""

import json
import time
import requests
from pathlib import Path

from .config import (
    OUTPUT_DIR,
    REDDIT_SUBREDDITS,
    REDDIT_SEARCH_QUERIES,
    REDDIT_MIN_SCORE,
    REDDIT_COMMENT_SCORE_THRESHOLD,
    REDDIT_REQUEST_DELAY,
    REDDIT_BACKOFF_DELAY,
)

HEADERS = {"User-Agent": "python:japan-trip-planner:v1.0 (by /u/hadley_family_travel)"}
BASE_URL = "https://www.reddit.com"


def _get_json(url: str, params: dict | None = None, max_retries: int = 5) -> dict | None:
    """Fetch JSON from Reddit with rate limiting and retry."""
    for attempt in range(max_retries):
        time.sleep(REDDIT_REQUEST_DELAY)
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=30)

            # Respect rate limit headers
            remaining = float(resp.headers.get("x-ratelimit-remaining", 10))
            reset_secs = float(resp.headers.get("x-ratelimit-reset", 0))
            if remaining < 3 and reset_secs > 0:
                wait = min(reset_secs + 2, 120)
                print(f"  Rate budget low ({remaining} left), waiting {wait:.0f}s for reset...")
                time.sleep(wait)

            if resp.status_code == 429:
                wait = max(reset_secs + 5, REDDIT_BACKOFF_DELAY)
                print(f"  429 rate limited, waiting {wait:.0f}s (attempt {attempt+1}/{max_retries})...")
                time.sleep(wait)
                continue
            if resp.status_code == 200:
                return resp.json()
            print(f"  HTTP {resp.status_code} for {url}")
            return None
        except requests.RequestException as e:
            print(f"  Request error: {e}")
            if attempt < max_retries - 1:
                time.sleep(10)
    return None


def _extract_posts(data: dict) -> list[dict]:
    """Extract post data from Reddit JSON response."""
    posts = []
    if not data or "data" not in data:
        return posts
    for child in data["data"].get("children", []):
        post = child.get("data", {})
        if post.get("score", 0) < REDDIT_MIN_SCORE:
            continue
        posts.append({
            "id": post.get("id"),
            "title": post.get("title", ""),
            "selftext": post.get("selftext", ""),
            "score": post.get("score", 0),
            "num_comments": post.get("num_comments", 0),
            "url": f"https://reddit.com{post.get('permalink', '')}",
            "created_utc": post.get("created_utc"),
            "subreddit": post.get("subreddit", ""),
        })
    return posts


def _fetch_top_comments(subreddit: str, post_id: str, limit: int = 20) -> list[dict]:
    """Fetch top comments for a post."""
    url = f"{BASE_URL}/r/{subreddit}/comments/{post_id}.json"
    data = _get_json(url, params={"sort": "top", "limit": limit})
    if not data or len(data) < 2:
        return []

    comments = []
    for child in data[1].get("data", {}).get("children", []):
        comment = child.get("data", {})
        body = comment.get("body", "")
        if body and comment.get("score", 0) > 5:
            comments.append({
                "body": body,
                "score": comment.get("score", 0),
            })
    return comments


def _fetch_listing(subreddit: str, path: str, params: dict, max_pages: int = 5) -> list[dict]:
    """Fetch a Reddit listing with pagination."""
    all_posts = []
    after = None

    for page in range(max_pages):
        p = {**params, "limit": 100}
        if after:
            p["after"] = after

        url = f"{BASE_URL}/r/{subreddit}/{path}.json"
        data = _get_json(url, params=p)
        if not data:
            break

        posts = _extract_posts(data)
        all_posts.extend(posts)

        after = data.get("data", {}).get("after")
        if not after:
            break

        print(f"    Page {page + 1}: {len(posts)} posts (total: {len(all_posts)})")

    return all_posts


def scrape_reddit() -> Path:
    """Scrape Reddit for Japan travel recommendations. Returns output file path."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    seen_ids = set()
    all_posts = []

    for subreddit in REDDIT_SUBREDDITS:
        print(f"\n=== r/{subreddit} ===")

        # Top posts - all time
        print(f"  Fetching top (all time)...")
        posts = _fetch_listing(subreddit, "top", {"t": "all"}, max_pages=2)
        for p in posts:
            if p["id"] not in seen_ids:
                seen_ids.add(p["id"])
                all_posts.append(p)
        print(f"  Got {len(posts)} posts")

        # Top posts - this year
        print(f"  Fetching top (year)...")
        posts = _fetch_listing(subreddit, "top", {"t": "year"}, max_pages=2)
        for p in posts:
            if p["id"] not in seen_ids:
                seen_ids.add(p["id"])
                all_posts.append(p)
        print(f"  Got {len(posts)} posts")

        # Search queries
        for query in REDDIT_SEARCH_QUERIES:
            print(f"  Searching: '{query}'...")
            posts = _fetch_listing(
                subreddit, "search",
                {"q": query, "restrict_sr": 1, "sort": "top", "t": "all"},
                max_pages=1,
            )
            for p in posts:
                if p["id"] not in seen_ids:
                    seen_ids.add(p["id"])
                    all_posts.append(p)

    # Fetch comments for high-scoring food/travel-relevant posts only
    food_keywords = {"restaurant", "ramen", "sushi", "food", "eat", "izakaya", "cafe",
                     "tempura", "yakiniku", "udon", "soba", "bakery", "bar", "drink",
                     "onsen", "ryokan", "hotel", "temple", "shrine", "hidden gem",
                     "recommendation", "trip report", "itinerary"}
    high_score_posts = [
        p for p in all_posts
        if p["score"] >= REDDIT_COMMENT_SCORE_THRESHOLD
        and any(kw in f"{p['title']} {p['selftext'][:500]}".lower() for kw in food_keywords)
    ]
    print(f"\nFetching comments for {len(high_score_posts)} high-scoring posts...")
    for i, post in enumerate(high_score_posts):
        print(f"  [{i+1}/{len(high_score_posts)}] {post['title'][:60]}...")
        comments = _fetch_top_comments(post["subreddit"], post["id"])
        post["top_comments"] = comments

    # Sort by score descending
    all_posts.sort(key=lambda p: p["score"], reverse=True)

    output_path = OUTPUT_DIR / "reddit_posts.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_posts, f, indent=2, ensure_ascii=False)

    print(f"\nDone! {len(all_posts)} unique posts saved to {output_path}")
    return output_path
