#!/usr/bin/env python
"""End-to-end test for morning briefing system.

Run with: python scripts/test_morning_briefing_e2e.py

Tests both the data fetcher and the skill context building.
Validates that output is Discord-ready with clickable URLs.
"""

import asyncio
import json
import sys
import io
from pathlib import Path

# Fix Windows console encoding for emoji output
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
from zoneinfo import ZoneInfo

UK_TZ = ZoneInfo("Europe/London")


def print_header(title: str):
    """Print formatted header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_result(label: str, success: bool, detail: str = ""):
    """Print test result."""
    icon = "✅" if success else "❌"
    print(f"  {icon} {label}")
    if detail:
        print(f"      {detail}")


async def test_data_fetcher():
    """Test that data fetcher returns expected structure."""
    print_header("Testing Data Fetcher")

    from domains.peterbot.data_fetchers import get_morning_briefing_data

    try:
        data = await get_morning_briefing_data()
    except Exception as e:
        print_result("Data fetcher call", False, f"Exception: {e}")
        return None

    # Check for error
    if "error" in data:
        print_result("Data fetcher result", False, f"Error: {data['error']}")
        return None

    # Check required keys
    required_keys = ["x_posts", "reddit_posts", "web_articles",
                     "has_x_data", "has_reddit_data", "has_web_data", "fetch_time"]

    for key in required_keys:
        if key in data:
            print_result(f"Key '{key}' present", True)
        else:
            print_result(f"Key '{key}' present", False, "Missing!")

    # Check data counts
    x_count = len(data.get("x_posts", []))
    reddit_count = len(data.get("reddit_posts", []))
    web_count = len(data.get("web_articles", []))

    print(f"\n  Data counts: X={x_count}, Reddit={reddit_count}, Web={web_count}")

    # Check item structure
    if x_count > 0:
        item = data["x_posts"][0]
        has_markdown = "markdown_link" in item
        has_handle = "handle" in item
        print_result("X posts have markdown_link", has_markdown)
        print_result("X posts have handle", has_handle)
        if has_markdown:
            print(f"      Sample: {item['markdown_link'][:80]}...")

    if reddit_count > 0:
        item = data["reddit_posts"][0]
        has_markdown = "markdown_link" in item
        has_subreddit = "subreddit" in item
        print_result("Reddit posts have markdown_link", has_markdown)
        print_result("Reddit posts have subreddit", has_subreddit)

    if web_count > 0:
        item = data["web_articles"][0]
        has_markdown = "markdown_link" in item
        print_result("Web articles have markdown_link", has_markdown)

    return data


def test_skill_context(data: dict):
    """Test building skill context like scheduler does."""
    print_header("Testing Skill Context Building")

    # Load skill
    skill_path = Path(__file__).parent.parent / "domains" / "peterbot" / "wsl_config" / "skills" / "morning-briefing" / "SKILL.md"

    if not skill_path.exists():
        print_result("Skill file exists", False, str(skill_path))
        return None

    skill_content = skill_path.read_text(encoding="utf-8")
    print_result("Skill file loaded", True, f"{len(skill_content)} chars")

    # Build context like scheduler does
    now = datetime.now(UK_TZ)

    context_parts = [
        f"# Scheduled Job: Morning Briefing",
        f"Time: {now.strftime('%A, %d %B %Y %H:%M')} UK",
        "",
        "## Skill Instructions",
        skill_content,
        "",
        "## Pre-fetched Data",
        "```json",
        json.dumps(data, indent=2, default=str),
        "```",
        "",
        "## CRITICAL OUTPUT RULES",
        "- ONLY output the formatted response as specified in the skill instructions above",
        "- Start your response DIRECTLY with the emoji/header",
    ]

    context = "\n".join(context_parts)

    print_result("Context built", True, f"{len(context)} chars total")

    # Check context has key elements
    has_json = "```json" in context
    has_skill = "## Curation Rules" in context or "Curation" in context
    has_markdown_link = "markdown_link" in context

    print_result("Context contains JSON data", has_json)
    print_result("Context contains skill rules", has_skill)
    print_result("Context mentions markdown_link", has_markdown_link)

    return context


def test_discord_format():
    """Test that expected output format is Discord-valid."""
    print_header("Testing Discord Format Requirements")

    # Sample expected output
    sample_output = '''**☀️ AI Morning Briefing — Wed 05 Feb 2026**

**📰 NEWS HEADLINES**
> **[Anthropic launches Claude 4](https://anthropic.com/news)** — Major model upgrade
> **[OpenAI releases GPT-5](https://openai.com/news)** — New capabilities announced
> **[Google updates Gemini](https://google.com/ai)** — Enhanced reasoning

**🛠️ CLAUDE CODE CORNER**
> **[MCP server for databases](https://github.com/example)** — PostgreSQL integration
> **[Claude Code tips thread](https://x.com/user/status/1)** — Productivity hacks

**💬 COMMUNITY BUZZ**
> **@anthropic:** [New features coming](https://x.com/anthropic/status/1)
> **@ClawdBot:** [Weekend project](https://x.com/ClawdBot/status/2)

**📢 REDDIT ROUNDUP**
> **[Claude vs GPT comparison](https://reddit.com/r/ClaudeAI/comments/1)** (r/ClaudeAI)
> **[Local LLM setup guide](https://reddit.com/r/LocalLLaMA/comments/2)** (r/LocalLLaMA)'''

    # Check length
    length = len(sample_output)
    print(f"  Sample output length: {length} chars")
    print_result("Output under 2000 chars", length < 2000)

    # Check for angle brackets (bad)
    has_angle_brackets = "<http" in sample_output or ">" in sample_output and "<" in sample_output
    print_result("No angle bracket URLs", not has_angle_brackets)

    # Check for markdown links (good)
    import re
    markdown_links = re.findall(r'\[([^\]]+)\]\(https?://[^\)]+\)', sample_output)
    print_result(f"Contains markdown links", len(markdown_links) > 0, f"Found {len(markdown_links)} links")

    # Check sections present
    sections = ["NEWS HEADLINES", "CLAUDE CODE CORNER", "COMMUNITY BUZZ", "REDDIT ROUNDUP"]
    for section in sections:
        present = section in sample_output
        print_result(f"Section '{section}' present", present)

    return True


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("  MORNING BRIEFING END-TO-END TEST")
    print("="*60)

    # Test 1: Data fetcher
    data = await test_data_fetcher()

    # Test 2: Skill context (only if data available)
    if data:
        context = test_skill_context(data)
    else:
        # Use mock data for testing
        print_header("Using Mock Data (API unavailable)")
        data = {
            "x_posts": [
                {"url": "https://x.com/anthropic/status/1", "title": "Test post",
                 "context": "ctx", "handle": "@anthropic",
                 "markdown_link": "[Test post](https://x.com/anthropic/status/1)"}
            ],
            "reddit_posts": [
                {"url": "https://reddit.com/r/ClaudeAI/comments/1/test", "title": "Reddit post",
                 "context": "ctx", "subreddit": "r/ClaudeAI",
                 "markdown_link": "[Reddit post](https://reddit.com/r/ClaudeAI/comments/1/test)"}
            ],
            "web_articles": [
                {"url": "https://example.com/article", "title": "Web article",
                 "context": "ctx",
                 "markdown_link": "[Web article](https://example.com/article)"}
            ],
            "has_x_data": True,
            "has_reddit_data": True,
            "has_web_data": True,
            "fetch_time": datetime.now(UK_TZ).strftime("%Y-%m-%d %H:%M")
        }
        context = test_skill_context(data)

    # Test 3: Discord format
    test_discord_format()

    print_header("TEST COMPLETE")
    print("  Review output above for any ❌ failures")
    print("")


if __name__ == "__main__":
    asyncio.run(main())
