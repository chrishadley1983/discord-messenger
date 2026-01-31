"""AI Morning Briefing scheduled job.

Posts daily at 6:30 AM UTC to #ai-briefings channel with:
- News headlines (Claude/Anthropic + broader AI)
- Claude Code inspiration (use cases, skills, MCPs)
- Community buzz (X/Reddit via xAI Grok live search)

Two-stage approach:
1. Grok fetches raw data with live X/Web/Reddit search using Responses API
2. Sonnet curates and formats into polished briefing

Uses xAI's /v1/responses endpoint with x_search and web_search tools for REAL URLs.
Based on: https://github.com/mvanhorn/last30days-skill
"""

import asyncio
import json
import re
from datetime import datetime, timedelta

import httpx

from config import GROK_API_KEY, ANTHROPIC_API_KEY
from logger import logger

# Channel ID for #ai-briefings
AI_BRIEFINGS_CHANNEL_ID = 1465277483866788037

# Models
GROK_MODEL = "grok-4-1-fast"
SONNET_MODEL = "claude-sonnet-4-20250514"


def _extract_urls_with_context(text: str, url_pattern: str) -> list[dict]:
    """Extract URLs from text along with surrounding context."""
    items = []

    # Find all URLs matching the pattern
    for match in re.finditer(url_pattern, text):
        url = match.group(0)
        # Clean URL - strip trailing punctuation and citation markers
        url = re.sub(r'[\[\]\(\)\.,;:\'"]+$', '', url)  # Strip trailing punctuation
        url = re.sub(r'\[\[\d+$', '', url)  # Strip trailing [[1 citation markers

        # Get surrounding context (100 chars before, 50 after)
        start = max(0, match.start() - 150)
        end = min(len(text), match.end() + 50)
        context = text[start:end].strip()

        # Clean up context - remove citation markers
        context = re.sub(r'\[\[\d+\]\]', '', context)
        context = re.sub(r'\s+', ' ', context).strip()

        # Try to extract a title/description from before the URL
        pre_url = text[max(0, match.start() - 200):match.start()]
        # Look for bold text **title** or numbered items
        title_match = re.search(r'\*\*([^*]+)\*\*', pre_url)
        if title_match:
            title = title_match.group(1)
        else:
            # Use first sentence of context
            title = context.split('.')[0][:100] if context else ""

        items.append({
            "url": url,
            "title": title,
            "context": context[:200]
        })

    return items


def _parse_x_response(response_data: dict) -> list[dict]:
    """Parse xAI x_search response to extract X/Twitter posts with context."""
    items = []

    for item in response_data.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    text = content.get("text", "")
                    if not text:
                        continue

                    # Extract X URLs with citation format [[N]](URL) or plain URLs
                    x_pattern = r'https?://(?:x\.com|twitter\.com)/[^\s\)\]"]+'
                    extracted = _extract_urls_with_context(text, x_pattern)

                    for ext in extracted:
                        if ext["url"] and not any(i["url"] == ext["url"] for i in items):
                            items.append({
                                "url": ext["url"],
                                "text": ext["title"],
                                "context": ext["context"],
                                "source": "x"
                            })

    logger.info(f"X search parsed {len(items)} items")
    return items


def _parse_reddit_response(response_data: dict) -> list[dict]:
    """Parse xAI web_search response for Reddit posts."""
    items = []

    for item in response_data.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    text = content.get("text", "")
                    if not text:
                        continue

                    # Extract Reddit URLs
                    reddit_pattern = r'https?://(?:www\.)?reddit\.com/r/\w+/comments/[^\s\)\]"]+'
                    extracted = _extract_urls_with_context(text, reddit_pattern)

                    for ext in extracted:
                        if ext["url"] and not any(i["url"] == ext["url"] for i in items):
                            # Extract subreddit from URL
                            sub_match = re.search(r'/r/(\w+)/', ext["url"])
                            subreddit = f"r/{sub_match.group(1)}" if sub_match else ""

                            items.append({
                                "url": ext["url"],
                                "text": ext["title"],
                                "subreddit": subreddit,
                                "context": ext["context"],
                                "source": "reddit"
                            })

    logger.info(f"Reddit search parsed {len(items)} items")
    return items


def _parse_web_response(response_data: dict) -> list[dict]:
    """Parse xAI web_search response for general web articles."""
    items = []

    for item in response_data.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    text = content.get("text", "")
                    if not text:
                        continue

                    # Extract non-X, non-Reddit URLs
                    url_pattern = r'https?://[^\s\)\]"]+'
                    extracted = _extract_urls_with_context(text, url_pattern)

                    for ext in extracted:
                        url = ext["url"]
                        # Skip X and Reddit URLs (handled separately)
                        if 'x.com' in url or 'twitter.com' in url or 'reddit.com' in url:
                            continue
                        # Skip common non-article URLs
                        if any(skip in url for skip in ['youtube.com/watch', 'github.com', 'arxiv.org/abs']):
                            continue

                        if url and not any(i["url"] == url for i in items):
                            items.append({
                                "url": url,
                                "text": ext["title"],
                                "context": ext["context"],
                                "source": "web"
                            })

    logger.info(f"Web search parsed {len(items)} items")
    return items


async def _search_x(topic: str, from_date: str, to_date: str) -> list[dict]:
    """Search X (Twitter) using xAI's x_search tool."""
    if not GROK_API_KEY:
        return []

    prompt = f"""Search X (Twitter) for posts about: {topic}

Date range: {from_date} to {to_date}

Find 15-20 relevant posts. Focus on:
- Posts mentioning @ClawdBot, @MoltBot, @OpenClaw (Claude Code community)
- Posts about Claude Code, MCP servers, AI coding tools
- AI researcher discussions and demos
- Viral AI coding content

Include the full x.com URL for each post."""

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
                    "tools": [{"type": "x_search"}],
                    "input": [{"role": "user", "content": prompt}]
                },
                timeout=120
            )

            if response.status_code == 200:
                data = response.json()
                return _parse_x_response(data)
            else:
                logger.error(f"X search error {response.status_code}: {response.text[:200]}")
                return []

    except Exception as e:
        logger.error(f"X search exception: {e}")
        return []


async def _search_reddit(topic: str) -> list[dict]:
    """Search Reddit using xAI's web_search tool."""
    if not GROK_API_KEY:
        return []

    prompt = f"""Search Reddit for recent discussions about: {topic}

Focus on finding posts from:
- r/ClaudeAI
- r/LocalLLaMA
- r/MachineLearning
- r/artificial
- r/singularity

Find 10-15 relevant Reddit posts from the last week.
Include the full reddit.com URL for each post."""

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
                return _parse_reddit_response(data)
            else:
                logger.error(f"Reddit search error {response.status_code}: {response.text[:200]}")
                return []

    except Exception as e:
        logger.error(f"Reddit search exception: {e}")
        return []


async def _search_web(topic: str) -> list[dict]:
    """Search the web using xAI's web_search tool."""
    if not GROK_API_KEY:
        return []

    prompt = f"""Search for recent news and articles about: {topic}

Find 10-15 relevant articles from the last 48 hours.
Focus on AI company announcements, product updates, and research.
Include the full URL for each article."""

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
                return _parse_web_response(data)
            else:
                logger.error(f"Web search error {response.status_code}: {response.text[:200]}")
                return []

    except Exception as e:
        logger.error(f"Web search exception: {e}")
        return []


async def _fetch_raw_data_from_grok() -> str:
    """Stage 1: Use Grok with live search tools to fetch real AI news data."""
    try:
        if not GROK_API_KEY:
            return "Error: Grok API key not configured"

        # Calculate date range
        today = datetime.utcnow()
        from_date = (today - timedelta(days=2)).strftime("%Y-%m-%d")
        to_date = today.strftime("%Y-%m-%d")

        # Define search topics
        x_topics = [
            "@ClawdBot OR @MoltBot OR @OpenClaw Claude Code",
            "Claude Code MCP server AI coding",
            "Anthropic Claude AI announcements"
        ]

        reddit_topics = [
            "Claude Code Claude AI Anthropic"
        ]

        web_topics = [
            "Anthropic Claude AI announcements news",
            "Claude Code MCP Model Context Protocol"
        ]

        # Create all search tasks
        x_tasks = [_search_x(topic, from_date, to_date) for topic in x_topics]
        reddit_tasks = [_search_reddit(topic) for topic in reddit_topics]
        web_tasks = [_search_web(topic) for topic in web_topics]

        # Run all searches in parallel
        results = await asyncio.gather(
            *x_tasks, *reddit_tasks, *web_tasks,
            return_exceptions=True
        )

        # Collect results
        x_items = []
        reddit_items = []
        web_items = []

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Search task {i} failed: {result}")
                continue
            if not isinstance(result, list):
                continue

            for item in result:
                source = item.get("source", "")
                # Deduplicate by URL
                if source == "x" and not any(i["url"] == item["url"] for i in x_items):
                    x_items.append(item)
                elif source == "reddit" and not any(i["url"] == item["url"] for i in reddit_items):
                    reddit_items.append(item)
                elif source == "web" and not any(i["url"] == item["url"] for i in web_items):
                    web_items.append(item)

        # Check if we have any results
        total = len(x_items) + len(reddit_items) + len(web_items)
        if total == 0:
            return "Error: No results found from search"

        # Format as structured data for Sonnet
        raw_data = "## SEARCH RESULTS WITH VERIFIED URLS\n\n"

        if x_items:
            raw_data += "### X (Twitter) Posts\n"
            for item in x_items[:15]:
                raw_data += f"- **{item.get('text', 'Post')}**\n"
                raw_data += f"  URL: {item.get('url', '')}\n"
                if item.get('context'):
                    raw_data += f"  Context: {item['context'][:150]}...\n"
                raw_data += "\n"

        if reddit_items:
            raw_data += "### Reddit Discussions\n"
            for item in reddit_items[:10]:
                raw_data += f"- **{item.get('text', 'Discussion')}** ({item.get('subreddit', '')})\n"
                raw_data += f"  URL: {item.get('url', '')}\n"
                if item.get('context'):
                    raw_data += f"  Context: {item['context'][:150]}...\n"
                raw_data += "\n"

        if web_items:
            raw_data += "### Web Articles\n"
            for item in web_items[:10]:
                raw_data += f"- **{item.get('text', 'Article')}**\n"
                raw_data += f"  URL: {item.get('url', '')}\n"
                raw_data += "\n"

        logger.info(f"Grok search complete: {len(x_items)} X, {len(reddit_items)} Reddit, {len(web_items)} Web")
        return raw_data

    except Exception as e:
        logger.error(f"Grok fetch error: {e}")
        return f"Error: {str(e)}"


async def _curate_with_sonnet(raw_data: str, date_str: str) -> str:
    """Stage 2: Use Sonnet to curate raw data into polished briefing."""
    try:
        if not ANTHROPIC_API_KEY:
            return raw_data  # Fallback to raw if no API key

        prompt = f"""You are curating an AI morning briefing for Discord. Here's VERIFIED search results with REAL URLs from X, Reddit, and web sources:

---
{raw_data}
---

Create a polished, engaging briefing. IMPORTANT:
1. ONLY use URLs that appear in the data above - DO NOT make up or modify URLs
2. Every link must come directly from the search results
3. You MUST include items from X, Reddit, AND Web sections if they exist in the data
4. Each item MUST have a 1-liner summary (one sentence max)
5. Include exactly 5 items per section (or all available if fewer than 5)

Format:

**☀️ AI Morning Briefing — {date_str}**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**📰 NEWS HEADLINES**
> 5 most significant AI stories from Web Articles
> Format: **One-liner summary** <exact-url-from-data>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**🛠️ CLAUDE CODE CORNER**
> 5 Claude Code related items from ANY source
> Format: **One-liner summary** <exact-url-from-data>
> If none found: "Nothing found today - submit your projects!"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**💬 COMMUNITY BUZZ**
> 5 interesting X posts from the X section
> Format: **@handle: One-liner summary** <exact-url-from-data>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**📢 REDDIT ROUNDUP**
> 5 interesting Reddit discussions
> Format: **One-liner summary** (r/subreddit) <exact-url-from-data>
> If none found: "No Reddit buzz today"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**🤖 MOLTBOT CORNER**
> 5 Moltbot/Clawdbot/OpenClaw mentions FROM THE DATA
> Format: **One-liner summary** <exact-url-from-data>
> If nothing found: "Quiet day in the Moltverse"

RULES:
- Use > blockquotes for each item
- Each item must be a single line with a brief summary (one sentence)
- CRITICAL: Only use URLs that appear EXACTLY in the search results above
- If a section has fewer than 5 items, include all available
- Do NOT invent or hallucinate any URLs"""

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
                    "max_tokens": 4000,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=60
            )

            if response.status_code == 200:
                data = response.json()
                content = data["content"][0]["text"]
                logger.info(f"Sonnet curation complete ({len(content)} chars)")
                return content
            else:
                logger.error(f"Sonnet API error {response.status_code}: {response.text}")
                return raw_data  # Fallback to raw

    except Exception as e:
        logger.error(f"Sonnet curation error: {e}")
        return raw_data


async def ai_morning_briefing(bot):
    """Post the AI morning briefing using Grok + Sonnet two-stage approach."""
    channel = bot.get_channel(AI_BRIEFINGS_CHANNEL_ID)
    if not channel:
        try:
            channel = await bot.fetch_channel(AI_BRIEFINGS_CHANNEL_ID)
        except Exception as e:
            logger.error(f"Could not find ai-briefings channel {AI_BRIEFINGS_CHANNEL_ID}: {e}")
            return

    try:
        today = datetime.utcnow()
        date_str = today.strftime("%a %d %b %Y")

        # Stage 1: Fetch raw data from Grok with live search
        logger.info("Stage 1: Fetching raw data from Grok...")
        raw_data = await _fetch_raw_data_from_grok()

        if raw_data.startswith("Error"):
            # Grok failed, post error message
            await channel.send(f"**☀️ AI Morning Briefing — {date_str}**\n\n> ⚠️ {raw_data}\n> Briefing unavailable today.")
            return

        # Stage 2: Curate with Sonnet
        logger.info("Stage 2: Curating with Sonnet...")
        briefing = await _curate_with_sonnet(raw_data, date_str)

        # Post to Discord - split into multiple messages if needed
        if len(briefing) <= 2000:
            await channel.send(briefing)
        else:
            # Split at section dividers to keep formatting clean
            sections = briefing.split("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            current_msg = ""
            divider = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

            for i, section in enumerate(sections):
                # Add divider back (except for first section)
                if i > 0:
                    section = divider + section

                if len(current_msg) + len(section) <= 1950:
                    current_msg += section
                else:
                    if current_msg:
                        await channel.send(current_msg)
                    current_msg = section

            if current_msg:
                await channel.send(current_msg)

        logger.info("Posted AI morning briefing successfully")

    except Exception as e:
        logger.error(f"Failed to post AI morning briefing: {e}")
        try:
            await channel.send(f"**☀️ AI Morning Briefing**\n\n> ⚠️ Error generating briefing: {str(e)[:100]}")
        except Exception:
            pass


def register_morning_briefing(scheduler, bot):
    """Register the morning briefing job with the scheduler."""
    scheduler.add_job(
        ai_morning_briefing,
        'cron',
        args=[bot],
        hour=6,
        minute=30,
        timezone="UTC",
        id="ai_morning_briefing"
    )
    logger.info("Registered AI morning briefing job (6:30 AM UTC)")
