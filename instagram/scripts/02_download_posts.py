"""
02_download_posts.py — Download Instagram saved posts via instaloader.

Reads data/master_index.json, downloads each post's media + caption + metadata
into downloads/{shortcode}/. Updates data/progress.json as it goes.

Usage:
    python scripts/02_download_posts.py                  # Download all pending
    python scripts/02_download_posts.py --retry-failed   # Retry only failures
    python scripts/02_download_posts.py --delay 5        # Custom delay (seconds)
"""

import argparse
import json
import shutil
import time
import sys
from pathlib import Path

try:
    import instaloader
except ImportError:
    print("ERROR: instaloader not installed. Run: pip install instaloader")
    sys.exit(1)

# Paths
INSTAGRAM_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = INSTAGRAM_DIR / "data"
DOWNLOADS_DIR = INSTAGRAM_DIR / "downloads"

MASTER_INDEX_PATH = DATA_DIR / "master_index.json"
PROGRESS_PATH = DATA_DIR / "progress.json"
FAILURES_PATH = DATA_DIR / "download_failures.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def setup_instaloader() -> instaloader.Instaloader:
    """Create and configure an Instaloader instance."""
    L = instaloader.Instaloader(
        download_videos=True,
        download_video_thumbnails=True,
        download_geotags=True,
        download_comments=False,
        save_metadata=True,
        compress_json=False,
        post_metadata_txt_pattern="",  # We write our own caption.txt
        dirname_pattern=str(DOWNLOADS_DIR / "{shortcode}"),
        filename_pattern="{shortcode}",
    )
    return L


def try_login(L: instaloader.Instaloader) -> bool:
    """Try to load a saved session. Return True if logged in."""
    import os
    username = os.environ.get("INSTAGRAM_USER", "")
    if not username:
        # Try to find any saved session
        session_dir = Path.home() / ".config" / "instaloader"
        if not session_dir.exists():
            # Windows alternative
            session_dir = Path.home() / "AppData" / "Local" / "instaloader"
        if session_dir.exists():
            sessions = list(session_dir.glob("session-*"))
            if sessions:
                username = sessions[0].name.replace("session-", "")

    if username:
        try:
            L.load_session_from_file(username)
            print(f"Loaded session for @{username}")
            return True
        except Exception as e:
            print(f"Failed to load session for @{username}: {e}")

    print("\n" + "=" * 60)
    print("NO INSTAGRAM SESSION FOUND")
    print("=" * 60)
    print("Run this command first to create a session:")
    print("  python -m instaloader --login YOUR_USERNAME")
    print("")
    print("Or set INSTAGRAM_USER environment variable:")
    print("  set INSTAGRAM_USER=your_username")
    print("=" * 60 + "\n")
    return False


def download_post(L: instaloader.Instaloader, shortcode: str, post_dir: Path) -> bool:
    """Download a single post by shortcode. Returns True on success."""
    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        L.download_post(post, target=post_dir)

        # Write caption.txt separately for easy access
        caption_path = post_dir / "caption.txt"
        caption = post.caption or "(no caption)"
        caption_path.write_text(caption, encoding="utf-8")

        # Write a compact meta.json
        meta = {
            "shortcode": shortcode,
            "owner_username": post.owner_username,
            "caption": post.caption,
            "is_video": post.is_video,
            "typename": post.typename,
            "likes": post.likes,
            "date_utc": post.date_utc.isoformat() if post.date_utc else None,
            "location": str(post.location) if post.location else None,
            "hashtags": list(post.caption_hashtags) if post.caption_hashtags else [],
            "mentions": list(post.caption_mentions) if post.caption_mentions else [],
        }
        meta_path = post_dir / "meta.json"
        meta_path.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return True
    except instaloader.exceptions.QueryReturnedNotFoundException:
        print(f"    Post {shortcode} not found (deleted?)")
        return False
    except instaloader.exceptions.ConnectionException as e:
        print(f"    Connection error for {shortcode}: {e}")
        return False
    except Exception as e:
        print(f"    Error downloading {shortcode}: {type(e).__name__}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Download Instagram saved posts")
    parser.add_argument("--retry-failed", action="store_true",
                        help="Only retry posts from download_failures.json")
    parser.add_argument("--delay", type=float, default=3.0,
                        help="Delay between downloads in seconds (default: 3)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max posts to download this run (0 = all)")
    args = parser.parse_args()

    # Load data
    master_index = load_json(MASTER_INDEX_PATH)
    progress = load_json(PROGRESS_PATH)
    posts = master_index["posts"]

    # Determine which posts to process
    if args.retry_failed:
        if not FAILURES_PATH.exists():
            print("No download_failures.json found — nothing to retry")
            return
        failures = load_json(FAILURES_PATH)
        shortcodes_to_process = set(failures.get("failures", {}).keys())
        print(f"Retrying {len(shortcodes_to_process)} failed downloads")
    else:
        shortcodes_to_process = {
            p["shortcode"] for p in posts
            if not progress["posts"].get(p["shortcode"], {}).get("downloaded", False)
        }
        print(f"{len(shortcodes_to_process)} posts pending download "
              f"(of {len(posts)} total)")

    if not shortcodes_to_process:
        print("Nothing to download!")
        return

    # Setup instaloader
    L = setup_instaloader()
    if not try_login(L):
        response = input("Continue without login? (y/N) ")
        if response.lower() != "y":
            return

    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

    # Track failures
    failures: dict[str, str] = {}
    downloaded = 0
    skipped = 0
    failed = 0

    posts_to_download = [p for p in posts if p["shortcode"] in shortcodes_to_process]
    if args.limit > 0:
        posts_to_download = posts_to_download[:args.limit]

    total = len(posts_to_download)
    print(f"\nDownloading {total} posts (delay: {args.delay}s)...\n")

    for i, post in enumerate(posts_to_download, 1):
        sc = post["shortcode"]
        post_dir = DOWNLOADS_DIR / sc

        # Skip if already has content (resume-safe)
        if post_dir.exists() and any(post_dir.iterdir()):
            progress["posts"].setdefault(sc, {})["downloaded"] = True
            save_json(PROGRESS_PATH, progress)
            skipped += 1
            print(f"[{i}/{total}] {sc} — already exists, skipping")
            continue

        post_dir.mkdir(parents=True, exist_ok=True)
        print(f"[{i}/{total}] {sc} (@{post['username']})...", end=" ", flush=True)

        success = download_post(L, sc, post_dir)
        if success:
            progress["posts"].setdefault(sc, {})["downloaded"] = True
            save_json(PROGRESS_PATH, progress)
            downloaded += 1
            print("OK")
        else:
            # Clean up empty dir on failure
            if post_dir.exists() and not any(post_dir.iterdir()):
                post_dir.rmdir()
            failures[sc] = "download_failed"
            failed += 1

        # Rate limiting (skip delay on last item)
        if i < total:
            time.sleep(args.delay)

    # Save failures log
    if failures:
        fail_data = {"failures": failures, "total": len(failures)}
        save_json(FAILURES_PATH, fail_data)
        print(f"\nFailures logged to {FAILURES_PATH}")

    print(f"\n=== Download Complete ===")
    print(f"  Downloaded: {downloaded}")
    print(f"  Skipped (existing): {skipped}")
    print(f"  Failed: {failed}")
    print(f"  Remaining: {len(shortcodes_to_process) - downloaded - skipped - failed}")


if __name__ == "__main__":
    main()
