"""YouTube Daily Digest scheduled job.

Posts daily at 6:00 AM UK time to #ai-briefings channel with:
- Lego Investing videos
- Bricklink store videos
- Claude Code tutorials
- AI News
- Interesting documentaries

Uses Grok's web_search tool to find YouTube videos, tracks shown videos
in Supabase to avoid duplicates, and uses Claude to generate summaries.
"""

import asyncio
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from config import GROK_API_KEY, ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_KEY
from logger import logger

# Channel ID for #ai-briefings
AI_BRIEFINGS_CHANNEL_ID = 1465277483866788037

# Models
GROK_MODEL = "grok-4-1-fast"
SONNET_MODEL = "claude-sonnet-4-20250514"

# Category configuration
YOUTUBE_CATEGORIES = {
    "lego_investing": {
        "name": "Lego Investing",
        "emoji": "🧱💰",
        "search_query": "site:youtube.com lego investing OR lego investment value OR lego sets appreciation"
    },
    "bricklink": {
        "name": "Bricklink Stores",
        "emoji": "🏪",
        "search_query": "site:youtube.com bricklink store OR bricklink selling OR bricklink business tips"
    },
    "claude_code": {
        "name": "Claude Code",
        "emoji": "🤖",
        "search_query": "site:youtube.com claude code OR anthropic claude coding OR claude AI programming tutorial"
    },
    "ai_news": {
        "name": "AI News",
        "emoji": "📰",
        "search_query": "site:youtube.com AI news OR artificial intelligence news OR machine learning news"
    },
    "documentaries": {
        "name": "Interesting Documentaries",
        "emoji": "🎬",
        "search_query": "site:youtube.com interesting documentary OR best documentary OR documentary film"
    }
}


def _get_supabase_headers():
    """Get headers for Supabase API calls."""
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }


async def _fetch_youtube_title(video_id: str) -> str:
    """Fetch actual video title from YouTube oEmbed API (no API key needed)."""
    url = f"https://www.youtube.com/oembed?url=https://youtube.com/watch?v={video_id}&format=json"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("title", "")
    except Exception as e:
        logger.warning(f"Failed to fetch YouTube title for {video_id}: {e}")
    return ""


async def _fetch_titles_for_videos(videos: list[dict]) -> None:
    """Fetch real titles for all videos in parallel using YouTube oEmbed API."""
    if not videos:
        return

    async def fetch_single(video: dict):
        title = await _fetch_youtube_title(video["video_id"])
        if title:
            video["title"] = title
            logger.debug(f"Fetched title for {video['video_id']}: {title[:50]}")

    await asyncio.gather(*[fetch_single(v) for v in videos], return_exceptions=True)


def _extract_youtube_urls(text: str) -> list[dict]:
    """Extract YouTube video URLs and surrounding context from text."""
    items = []

    # Pattern for YouTube URLs - captures video ID
    youtube_pattern = r'https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})[^\s\)\]"]*'

    for match in re.finditer(youtube_pattern, text):
        full_url = match.group(0)
        video_id = match.group(1)

        # Clean URL - strip trailing punctuation
        full_url = re.sub(r'[\[\]\(\)\.,;:\'"]+$', '', full_url)

        # Normalize to standard format
        clean_url = f"https://youtube.com/watch?v={video_id}"

        # Get surrounding context (200 chars before, 100 after)
        start = max(0, match.start() - 200)
        end = min(len(text), match.end() + 100)
        context = text[start:end].strip()

        # Clean up context
        context = re.sub(r'\[\[\d+\]\]', '', context)
        context = re.sub(r'\s+', ' ', context).strip()

        # Skip if we already have this video
        if any(item["video_id"] == video_id for item in items):
            continue

        # Use placeholder title - real title will be fetched from YouTube oEmbed API
        items.append({
            "video_id": video_id,
            "url": clean_url,
            "title": f"Video {video_id}",  # Placeholder, replaced by _fetch_titles_for_videos()
            "context": context[:300]
        })

    return items


def _parse_grok_response(response_data: dict) -> list[dict]:
    """Parse Grok web_search response to extract YouTube videos."""
    items = []

    for item in response_data.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    text = content.get("text", "")
                    if not text:
                        continue

                    extracted = _extract_youtube_urls(text)
                    for ext in extracted:
                        # Deduplicate by video_id
                        if not any(i["video_id"] == ext["video_id"] for i in items):
                            items.append(ext)

    return items


async def _search_youtube_grok(category: str, query: str) -> list[dict]:
    """Search for YouTube videos using Grok's web_search tool."""
    if not GROK_API_KEY:
        logger.error("GROK_API_KEY not configured")
        return []

    prompt = f"""Search for recent YouTube videos about: {query}

Find 5-10 relevant YouTube videos uploaded in the last 7 days.
For each video, provide:
- The full youtube.com URL
- The video title
- A brief description of what the video covers

Focus on quality content from established creators with good engagement."""

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.x.ai/v1/responses",
                headers={
                    "Authorization": f"Bearer {GROK_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": GROK_MODEL,
                    "tools": [{"type": "web_search"}],
                    "input": [{"role": "user", "content": prompt}]
                },
                timeout=120
            )

            if response.status_code == 200:
                data = response.json()
                videos = _parse_grok_response(data)

                # Fetch real titles from YouTube oEmbed API
                await _fetch_titles_for_videos(videos)

                logger.info(f"Grok search for {category}: found {len(videos)} videos")
                return videos
            else:
                logger.error(f"Grok search error {response.status_code}: {response.text[:200]}")
                return []

    except Exception as e:
        logger.error(f"Grok search exception for {category}: {e}")
        return []


async def get_shown_video_ids() -> set[str]:
    """Fetch all previously shown video IDs from Supabase."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.warning("Supabase not configured, skipping duplicate check")
        return set()

    try:
        url = f"{SUPABASE_URL}/rest/v1/youtube_shown_videos?select=video_id"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=_get_supabase_headers(),
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

        video_ids = {item["video_id"] for item in data}
        logger.info(f"Found {len(video_ids)} previously shown videos")
        return video_ids

    except Exception as e:
        logger.error(f"Failed to fetch shown video IDs: {e}")
        return set()


async def mark_video_shown(video: dict, category: str, summary: str) -> None:
    """Record a video as shown in Supabase."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.warning("Supabase not configured, skipping video tracking")
        return

    try:
        payload = {
            "video_id": video["video_id"],
            "title": video["title"][:500],
            "channel_name": video.get("channel_name", ""),
            "category": category,
            "video_url": video["url"],
            "summary": summary[:1000] if summary else None
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SUPABASE_URL}/rest/v1/youtube_shown_videos",
                headers=_get_supabase_headers(),
                json=payload,
                timeout=30
            )
            response.raise_for_status()

        logger.info(f"Marked video as shown: {video['video_id']}")

    except Exception as e:
        logger.error(f"Failed to mark video as shown: {e}")


async def _generate_summary(video: dict) -> str:
    """Generate a paragraph summary using Claude based on video title and context."""
    if not ANTHROPIC_API_KEY:
        return video.get("context", "")[:150] + "..."

    prompt = f"""Based on this YouTube video's title and context, write a concise 2-3 sentence summary
explaining what the video covers and why someone might want to watch it.

Title: {video['title']}
Context: {video.get('context', 'No additional context available')}

Write only the summary paragraph, no preamble or labels."""

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": SONNET_MODEL,
                    "max_tokens": 200,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                summary = data["content"][0]["text"]
                return summary.strip()
            else:
                logger.error(f"Claude summary error {response.status_code}: {response.text[:100]}")
                return video.get("context", "")[:150] + "..."

    except Exception as e:
        logger.error(f"Claude summary exception: {e}")
        return video.get("context", "")[:150] + "..."


def _format_discord_message(videos_by_category: dict[str, list], date_str: str) -> list[str]:
    """Format videos into Discord messages, respecting 2000 char limit."""
    messages = []
    current_msg = f"**📺 YouTube Daily Digest — {date_str}**\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    for category_key, videos in videos_by_category.items():
        config = YOUTUBE_CATEGORIES.get(category_key, {})
        emoji = config.get("emoji", "📹")
        name = config.get("name", category_key)

        section = f"\n\n**{emoji} {name}**\n"

        if not videos:
            section += "> No new videos found today\n"
        else:
            for video in videos[:2]:  # Max 2 per category
                section += f"\n> **{video['title'][:80]}**\n"
                if video.get("summary"):
                    section += f"> {video['summary']}\n"
                section += f"> <{video['url']}>\n"

        # Check if adding this section would exceed limit
        if len(current_msg) + len(section) > 1900:
            messages.append(current_msg)
            current_msg = section.strip()
        else:
            current_msg += section

    if current_msg:
        messages.append(current_msg)

    return messages


async def youtube_feed(bot):
    """Post the YouTube daily digest."""
    channel = bot.get_channel(AI_BRIEFINGS_CHANNEL_ID)
    if not channel:
        try:
            channel = await bot.fetch_channel(AI_BRIEFINGS_CHANNEL_ID)
        except Exception as e:
            logger.error(f"Could not find ai-briefings channel {AI_BRIEFINGS_CHANNEL_ID}: {e}")
            return

    try:
        today = datetime.now(ZoneInfo("Europe/London"))
        date_str = today.strftime("%a %d %b %Y")

        # Get all previously shown video IDs
        shown_ids = await get_shown_video_ids()

        # Search each category
        videos_by_category = {}
        all_search_tasks = []

        for category_key, config in YOUTUBE_CATEGORIES.items():
            all_search_tasks.append(
                (category_key, _search_youtube_grok(category_key, config["search_query"]))
            )

        # Run all searches in parallel
        search_results = await asyncio.gather(
            *[task[1] for task in all_search_tasks],
            return_exceptions=True
        )

        # Process results
        for i, (category_key, _) in enumerate(all_search_tasks):
            result = search_results[i]
            if isinstance(result, Exception):
                logger.warning(f"Search failed for {category_key}: {result}")
                videos_by_category[category_key] = []
                continue

            # Filter out already shown videos
            new_videos = [v for v in result if v["video_id"] not in shown_ids]
            logger.info(f"{category_key}: {len(result)} found, {len(new_videos)} new")

            # Take top 2 new videos
            selected = new_videos[:2]

            # Generate summaries and mark as shown
            for video in selected:
                summary = await _generate_summary(video)
                video["summary"] = summary
                await mark_video_shown(video, category_key, summary)
                # Add to shown_ids to prevent duplicates across categories
                shown_ids.add(video["video_id"])

            videos_by_category[category_key] = selected

        # Format and post
        messages = _format_discord_message(videos_by_category, date_str)

        for msg in messages:
            await channel.send(msg)

        total_videos = sum(len(v) for v in videos_by_category.values())
        logger.info(f"Posted YouTube daily digest: {total_videos} videos")

    except Exception as e:
        logger.error(f"Failed to post YouTube digest: {e}")
        try:
            await channel.send(f"**📺 YouTube Daily Digest**\n\n> ⚠️ Error generating digest: {str(e)[:100]}")
        except Exception:
            pass


def register_youtube_feed(scheduler, bot):
    """Register the YouTube feed job with the scheduler."""
    scheduler.add_job(
        youtube_feed,
        'cron',
        args=[bot],
        hour=6,
        minute=0,
        timezone="Europe/London",
        id="youtube_daily_feed"
    )
    logger.info("Registered YouTube daily feed job (6:00 AM UK time)")
