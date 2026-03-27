"""Claude-based place extraction from scraped content. Token-efficient batched processing."""

import json
import os
import re
from pathlib import Path
from dotenv import load_dotenv

from .config import (
    OUTPUT_DIR,
    JAPAN_PLACE_KEYWORDS,
    CLAUDE_MODEL,
    CLAUDE_BATCH_SIZE_REDDIT,
    CLAUDE_BATCH_SIZE_YOUTUBE,
)

load_dotenv()

EXTRACTION_PROMPT = """Extract every specific place recommendation from the content below.
Return a JSON array only. Each item must have these fields:
- name: the place name (as specific as possible)
- type: one of: restaurant, cafe, bar, shrine, temple, park, market, shop, activity, hotel, onsen, ryokan
- neighbourhood: area/ward/station if mentioned (e.g. "Shinjuku", "Gion", "Dotonbori")
- city: city name (Tokyo, Kyoto, Osaka, Yokohama, Nara, Hakone, Kamakura, etc.)
- context: 1 sentence about why it was recommended or what to get there
- source_url: the source URL provided

Rules:
- Only include places with a SPECIFIC NAME. Skip vague references like "a great ramen shop"
- If a chain is mentioned generically (e.g. "Ichiran"), include it but set neighbourhood to ""
- Deduplicate within this batch (if same place mentioned twice, keep the richer entry)
- Return [] if no specific places are found
- Return ONLY the JSON array, no other text"""


def _keyword_relevant(text: str) -> bool:
    """Check if text contains any Japan place keywords."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in [k.lower() for k in JAPAN_PLACE_KEYWORDS])


def _prepare_reddit_batches(posts_path: Path) -> list[list[dict]]:
    """Load Reddit posts, filter by keyword relevance, batch for Claude."""
    with open(posts_path, "r", encoding="utf-8") as f:
        posts = json.load(f)

    # Filter to relevant posts
    relevant = []
    for post in posts:
        text = f"{post['title']} {post['selftext']}"
        comments_text = " ".join(
            c["body"] for c in post.get("top_comments", [])
        )
        if _keyword_relevant(text) or _keyword_relevant(comments_text):
            relevant.append(post)

    print(f"  Reddit: {len(relevant)}/{len(posts)} posts pass keyword filter")

    # Create batches
    batches = []
    for i in range(0, len(relevant), CLAUDE_BATCH_SIZE_REDDIT):
        batch = relevant[i:i + CLAUDE_BATCH_SIZE_REDDIT]
        batches.append(batch)

    return batches


def _prepare_youtube_batches(videos_path: Path) -> list[list[dict]]:
    """Load YouTube videos, extract relevant segments, batch for Claude."""
    with open(videos_path, "r", encoding="utf-8") as f:
        videos = json.load(f)

    # Collect all relevant content pieces
    pieces = []
    for video in videos:
        # Relevant transcript segments
        for seg in video.get("transcript_segments", []):
            pieces.append({
                "source": "youtube_transcript",
                "title": video["title"],
                "text": seg["text"],
                "url": seg["url"],
            })

        # Relevant descriptions
        desc = video.get("full_description", "")
        if desc and _keyword_relevant(desc):
            pieces.append({
                "source": "youtube_description",
                "title": video["title"],
                "text": desc,
                "url": video["url"],
            })

    print(f"  YouTube: {len(pieces)} relevant content pieces from {len(videos)} videos")

    # Create batches
    batches = []
    for i in range(0, len(pieces), CLAUDE_BATCH_SIZE_YOUTUBE):
        batch = pieces[i:i + CLAUDE_BATCH_SIZE_YOUTUBE]
        batches.append(batch)

    return batches


def _format_reddit_batch(batch: list[dict]) -> str:
    """Format a batch of Reddit posts for the Claude prompt."""
    parts = []
    for post in batch:
        text = post["selftext"][:2000]  # Cap per post to save tokens
        part = f"[Source: {post['url']}]\nTitle: {post['title']}\n{text}"
        # Include top comments if available
        comments = post.get("top_comments", [])[:5]
        if comments:
            comment_text = "\n".join(f"- {c['body'][:300]}" for c in comments)
            part += f"\nTop comments:\n{comment_text}"
        parts.append(part)
    return "\n\n---\n\n".join(parts)


def _format_youtube_batch(batch: list[dict]) -> str:
    """Format a batch of YouTube content for the Claude prompt."""
    parts = []
    for piece in batch:
        text = piece["text"][:3000]  # Cap per piece
        parts.append(f"[Source: {piece['url']}]\nVideo: {piece['title']}\n{text}")
    return "\n\n---\n\n".join(parts)


def _call_claude(content: str) -> list[dict]:
    """Call Claude API for place extraction."""
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        messages=[
            {"role": "user", "content": f"{EXTRACTION_PROMPT}\n\n{content}"}
        ],
    )

    text = response.content[0].text.strip()

    # Extract JSON from response (handle markdown code blocks)
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)

    try:
        places = json.loads(text)
        if isinstance(places, list):
            return places
    except json.JSONDecodeError:
        print(f"  Warning: Failed to parse Claude response as JSON")
        # Try to find JSON array in the response
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

    return []


def extract_places() -> Path:
    """Extract place recommendations from scraped data using Claude. Returns output file path."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    all_places = []
    total_input_tokens = 0
    total_output_tokens = 0

    reddit_path = OUTPUT_DIR / "reddit_posts.json"
    youtube_path = OUTPUT_DIR / "youtube_videos.json"

    # Process Reddit
    if reddit_path.exists():
        print("\n=== Extracting from Reddit ===")
        batches = _prepare_reddit_batches(reddit_path)
        print(f"  {len(batches)} batches to process")

        for i, batch in enumerate(batches):
            print(f"  Batch [{i+1}/{len(batches)}]...")
            content = _format_reddit_batch(batch)
            places = _call_claude(content)
            # Tag source
            for p in places:
                p["source_platform"] = "reddit"
            all_places.extend(places)
            print(f"    → {len(places)} places extracted")
    else:
        print("No Reddit data found, skipping")

    # Process YouTube
    if youtube_path.exists():
        print("\n=== Extracting from YouTube ===")
        batches = _prepare_youtube_batches(youtube_path)
        print(f"  {len(batches)} batches to process")

        for i, batch in enumerate(batches):
            print(f"  Batch [{i+1}/{len(batches)}]...")
            content = _format_youtube_batch(batch)
            places = _call_claude(content)
            # Tag source
            for p in places:
                p["source_platform"] = "youtube"
            all_places.extend(places)
            print(f"    → {len(places)} places extracted")
    else:
        print("No YouTube data found, skipping")

    output_path = OUTPUT_DIR / "extracted_places.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_places, f, indent=2, ensure_ascii=False)

    print(f"\nDone! {len(all_places)} total places extracted to {output_path}")
    return output_path
