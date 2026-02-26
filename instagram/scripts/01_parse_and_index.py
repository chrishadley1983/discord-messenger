"""
01_parse_and_index.py — Parse Instagram export JSONs into a master index.

Reads saved_posts.json and saved_collections.json, extracts shortcodes,
maps each post to its collection(s), and writes:
  - data/master_index.json   (all posts with metadata)
  - data/progress.json       (pipeline state tracker)
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

# Paths
INSTAGRAM_DIR = Path(__file__).resolve().parent.parent
SAVED_DIR = INSTAGRAM_DIR / "your_instagram_activity" / "saved"
DATA_DIR = INSTAGRAM_DIR / "data"

SAVED_POSTS_PATH = SAVED_DIR / "saved_posts.json"
SAVED_COLLECTIONS_PATH = SAVED_DIR / "saved_collections.json"
MASTER_INDEX_PATH = DATA_DIR / "master_index.json"
PROGRESS_PATH = DATA_DIR / "progress.json"

SHORTCODE_RE = re.compile(r"/(?:p|reel)/([A-Za-z0-9_-]+)")


def extract_shortcode(url: str) -> str | None:
    """Extract shortcode from an Instagram URL."""
    m = SHORTCODE_RE.search(url)
    return m.group(1) if m else None


def parse_saved_posts(path: Path) -> list[dict]:
    """Parse saved_posts.json → list of post dicts."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    posts = []
    for item in raw.get("saved_saved_media", []):
        smd = item.get("string_map_data", {})
        saved_on = smd.get("Saved on", {})
        url = saved_on.get("href", "")
        shortcode = extract_shortcode(url)
        if not shortcode:
            print(f"  WARN: no shortcode in URL '{url}' — skipping")
            continue
        posts.append({
            "shortcode": shortcode,
            "url": url,
            "username": item.get("title", ""),
            "saved_timestamp": saved_on.get("timestamp"),
            "media_type": "reel" if "/reel/" in url else "post",
        })
    return posts


def parse_collections(path: Path) -> dict[str, list[str]]:
    """
    Parse saved_collections.json → {collection_name: [url, url, ...]}.

    The file is a flat array. Collection headers have title="Collection" and
    a Name.value field. Posts that follow (no title) belong to that collection
    until the next header.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    collections: dict[str, list[str]] = {}
    current_collection = None

    for item in raw.get("saved_saved_collections", []):
        if item.get("title") == "Collection":
            # This is a collection header
            name = item["string_map_data"]["Name"]["value"]
            current_collection = name
            collections[current_collection] = []
        elif current_collection is not None:
            # This is a post within the current collection
            smd = item.get("string_map_data", {})
            href = smd.get("Name", {}).get("href", "")
            if href:
                collections[current_collection].append(href)

    return collections


def build_master_index():
    """Main: build the master index and progress tracker."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Parse all saved posts
    print("Parsing saved_posts.json...")
    posts = parse_saved_posts(SAVED_POSTS_PATH)
    print(f"  Found {len(posts)} posts")

    # 2. Parse collections
    print("Parsing saved_collections.json...")
    collections = parse_collections(SAVED_COLLECTIONS_PATH)
    for name, urls in collections.items():
        print(f"  Collection '{name}': {len(urls)} posts")

    # 3. Build URL → collection mapping (a post can be in multiple collections)
    url_to_collections: dict[str, list[str]] = {}
    for coll_name, urls in collections.items():
        for url in urls:
            sc = extract_shortcode(url)
            if sc:
                url_to_collections.setdefault(sc, []).append(coll_name)

    # 4. Assign collections to posts
    multi_collection_count = 0
    uncollected_count = 0
    for post in posts:
        colls = url_to_collections.get(post["shortcode"], [])
        post["collections"] = colls
        if len(colls) > 1:
            multi_collection_count += 1
        if len(colls) == 0:
            uncollected_count += 1

    print(f"\n  Multi-collection posts: {multi_collection_count}")
    print(f"  Uncollected posts: {uncollected_count}")

    # 5. Check for collection posts not in saved_posts (shouldn't happen, but log it)
    saved_shortcodes = {p["shortcode"] for p in posts}
    for coll_name, urls in collections.items():
        for url in urls:
            sc = extract_shortcode(url)
            if sc and sc not in saved_shortcodes:
                print(f"  WARN: '{sc}' in collection '{coll_name}' but not in saved_posts")

    # 6. Build master index
    master_index = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_posts": len(posts),
        "collections": {name: len(urls) for name, urls in collections.items()},
        "uncollected_count": uncollected_count,
        "multi_collection_count": multi_collection_count,
        "posts": posts,
    }

    # 7. Write master index
    MASTER_INDEX_PATH.write_text(
        json.dumps(master_index, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nWrote {MASTER_INDEX_PATH}")

    # 8. Build progress tracker (only if it doesn't exist — preserve resume state)
    if PROGRESS_PATH.exists():
        print(f"Progress file already exists at {PROGRESS_PATH} — not overwriting")
        # Merge: add any new posts not already tracked
        progress = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
        existing = {sc for sc in progress.get("posts", {})}
        added = 0
        for post in posts:
            if post["shortcode"] not in existing:
                progress["posts"][post["shortcode"]] = {
                    "downloaded": False,
                    "frames_extracted": False,
                    "transcribed": False,
                    "analysed": False,
                }
                added += 1
        if added:
            PROGRESS_PATH.write_text(
                json.dumps(progress, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"  Added {added} new posts to progress tracker")
    else:
        progress = {
            "posts": {
                post["shortcode"]: {
                    "downloaded": False,
                    "frames_extracted": False,
                    "transcribed": False,
                    "analysed": False,
                }
                for post in posts
            }
        }
        PROGRESS_PATH.write_text(
            json.dumps(progress, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Wrote {PROGRESS_PATH}")

    # Summary
    print("\n=== Summary ===")
    print(f"Total posts: {len(posts)}")
    for name, count in master_index["collections"].items():
        print(f"  {name}: {count}")
    print(f"  Uncollected: {uncollected_count}")
    if multi_collection_count:
        print(f"  Multi-collection: {multi_collection_count}")


if __name__ == "__main__":
    build_master_index()
