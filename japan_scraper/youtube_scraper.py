"""YouTube scraper for Japan travel recommendations via API + transcript extraction."""

import json
import os
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

from .config import (
    OUTPUT_DIR,
    YOUTUBE_SEARCH_QUERIES,
    YOUTUBE_MAX_RESULTS_PER_QUERY,
    YOUTUBE_MIN_DATE,
    JAPAN_PLACE_KEYWORDS,
)

load_dotenv()


def _get_api_key() -> str:
    """Get YouTube API key (falls back to Google Maps key)."""
    key = os.getenv("YOUTUBE_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY")
    if not key:
        raise RuntimeError("Set YOUTUBE_API_KEY or GOOGLE_MAPS_API_KEY in .env")
    return key


def _search_videos(query: str, api_key: str, max_results: int = 10) -> list[dict]:
    """Search YouTube for videos matching a query."""
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max_results,
        "order": "viewCount",
        "publishedAfter": YOUTUBE_MIN_DATE,
        "relevanceLanguage": "en",
        "key": api_key,
    }
    resp = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        params=params,
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"  YouTube API error: {resp.status_code}")
        return []

    data = resp.json()
    if "error" in data:
        print(f"  YouTube API error: {data['error'].get('message', '')}")
        return []

    videos = []
    for item in data.get("items", []):
        snippet = item.get("snippet", {})
        video_id = item.get("id", {}).get("videoId", "")
        if not video_id:
            continue
        videos.append({
            "video_id": video_id,
            "title": snippet.get("title", ""),
            "channel": snippet.get("channelTitle", ""),
            "description": snippet.get("description", ""),
            "published": snippet.get("publishedAt", ""),
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })
    return videos


def _get_video_details(video_ids: list[str], api_key: str) -> dict[str, dict]:
    """Get view counts and full descriptions for videos (cheap: 1 unit per call)."""
    if not video_ids:
        return {}

    details = {}
    # API accepts up to 50 IDs per call
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={
                "part": "snippet,statistics",
                "id": ",".join(batch),
                "key": api_key,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            continue

        for item in resp.json().get("items", []):
            vid = item["id"]
            stats = item.get("statistics", {})
            snippet = item.get("snippet", {})
            details[vid] = {
                "view_count": int(stats.get("viewCount", 0)),
                "like_count": int(stats.get("likeCount", 0)),
                "full_description": snippet.get("description", ""),
            }
    return details


def _extract_transcript(video_id: str) -> list[dict] | None:
    """Extract transcript with timestamps using youtube-transcript-api."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video_id, languages=["en", "en-US", "en-GB"])
        return [
            {
                "text": entry.text,
                "start": entry.start,
                "duration": entry.duration,
            }
            for entry in transcript.snippets
        ]
    except Exception as e:
        print(f"  No transcript for {video_id}: {e}")
        return None


def _filter_transcript_segments(
    transcript: list[dict], video_id: str, segment_duration: float = 300.0
) -> list[dict]:
    """Split transcript into segments and keep only those with relevant keywords."""
    if not transcript:
        return []

    keywords_lower = [k.lower() for k in JAPAN_PLACE_KEYWORDS]
    segments = []
    current_segment = {"start": 0.0, "texts": [], "end": segment_duration}

    for entry in transcript:
        if entry["start"] >= current_segment["end"]:
            # Close current segment and start new one
            if current_segment["texts"]:
                segments.append(current_segment)
            seg_start = entry["start"]
            current_segment = {
                "start": seg_start,
                "texts": [],
                "end": seg_start + segment_duration,
            }
        current_segment["texts"].append(entry["text"])

    if current_segment["texts"]:
        segments.append(current_segment)

    # Filter: keep only segments containing relevant keywords
    filtered = []
    for seg in segments:
        combined = " ".join(seg["texts"]).lower()
        if any(kw in combined for kw in keywords_lower):
            timestamp = int(seg["start"])
            filtered.append({
                "text": " ".join(seg["texts"]),
                "start_seconds": timestamp,
                "url": f"https://www.youtube.com/watch?v={video_id}&t={timestamp}s",
            })

    return filtered


def scrape_youtube() -> Path:
    """Scrape YouTube for Japan travel recommendations. Returns output file path."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    api_key = _get_api_key()

    seen_ids = set()
    all_videos = []

    # Phase 1: Discover videos
    print("=== YouTube Video Discovery ===")
    for query in YOUTUBE_SEARCH_QUERIES:
        print(f"  Searching: '{query}'...")
        videos = _search_videos(query, api_key, YOUTUBE_MAX_RESULTS_PER_QUERY)
        for v in videos:
            if v["video_id"] not in seen_ids:
                seen_ids.add(v["video_id"])
                all_videos.append(v)
        time.sleep(0.5)  # Be polite

    print(f"\nDiscovered {len(all_videos)} unique videos")

    # Phase 2: Get detailed stats (view counts, full descriptions)
    print("\n=== Fetching Video Details ===")
    video_ids = [v["video_id"] for v in all_videos]
    details = _get_video_details(video_ids, api_key)

    for video in all_videos:
        vid = video["video_id"]
        if vid in details:
            video.update(details[vid])

    # Sort by views descending, take top videos
    all_videos.sort(key=lambda v: v.get("view_count", 0), reverse=True)
    print(f"Top video: {all_videos[0]['title']} ({all_videos[0].get('view_count', 0):,} views)")

    # Phase 3: Extract and filter transcripts
    print(f"\n=== Extracting Transcripts ({len(all_videos)} videos) ===")
    for i, video in enumerate(all_videos):
        vid = video["video_id"]
        print(f"  [{i+1}/{len(all_videos)}] {video['title'][:60]}...")

        transcript = _extract_transcript(vid)
        if transcript:
            video["has_transcript"] = True
            video["transcript_segments"] = _filter_transcript_segments(transcript, vid)
            print(f"    → {len(video['transcript_segments'])} relevant segments")
        else:
            video["has_transcript"] = False
            video["transcript_segments"] = []

        time.sleep(0.3)

    # Also check descriptions for keyword relevance
    keywords_lower = [k.lower() for k in JAPAN_PLACE_KEYWORDS]
    for video in all_videos:
        desc = video.get("full_description", "").lower()
        video["description_relevant"] = any(kw in desc for kw in keywords_lower)

    output_path = OUTPUT_DIR / "youtube_videos.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_videos, f, indent=2, ensure_ascii=False)

    videos_with_data = sum(
        1 for v in all_videos
        if v.get("transcript_segments") or v.get("description_relevant")
    )
    print(f"\nDone! {len(all_videos)} videos saved ({videos_with_data} with relevant content)")
    return output_path
