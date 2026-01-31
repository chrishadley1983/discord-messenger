"""Test script to verify X, Reddit, and Web search APIs."""

import asyncio
import json
import re
import httpx
from config import GROK_API_KEY, OPENAI_API_KEY

GROK_MODEL = "grok-4-1-fast"
OPENAI_MODEL = "gpt-4o"


async def test_x_search():
    """Test xAI x_search and examine response structure."""
    print("\n" + "=" * 60)
    print("TESTING X SEARCH (xAI)")
    print("=" * 60)

    prompt = """Search X (Twitter) for recent posts about Claude Code MCP.
Find 10-15 relevant posts from the last 48 hours."""

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

        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            print(response.text)
            return None, []

        data = response.json()
        print(f"\nResponse keys: {list(data.keys())}")
        print(f"Output count: {len(data.get('output', []))}")

        items = []
        full_text = ""

        for i, item in enumerate(data.get("output", [])):
            item_type = item.get("type", "")
            print(f"\n  output[{i}]: type={item_type}")

            if item_type == "message":
                content_list = item.get("content", [])
                for content in content_list:
                    if content.get("type") == "output_text":
                        text = content.get("text", "")
                        full_text = text
                        print(f"    output_text: {len(text)} chars")

                        # Show first 500 chars to understand format
                        print(f"    Preview: {text[:500]}...")

                        # Try to extract URLs with context
                        # Pattern 1: [[N]](URL) format
                        pattern1 = r'\[\[(\d+)\]\]\((https?://x\.com/[^\)]+)\)'
                        matches1 = re.findall(pattern1, text)
                        print(f"    Citation URLs found: {len(matches1)}")

                        # Pattern 2: Plain URLs
                        pattern2 = r'(https?://x\.com/\S+)'
                        matches2 = re.findall(pattern2, text)
                        print(f"    Plain X URLs found: {len(matches2)}")

                        # Extract URLs with surrounding context
                        for url in matches2[:5]:
                            # Find context around URL
                            url_pos = text.find(url)
                            start = max(0, url_pos - 100)
                            end = min(len(text), url_pos + len(url) + 50)
                            context = text[start:end].replace("\n", " ")
                            items.append({
                                "url": url.rstrip(".,;:)"),
                                "context": context,
                                "source": "x"
                            })

        return full_text, items


async def test_reddit_search():
    """Test OpenAI web_search with reddit.com filter."""
    print("\n" + "=" * 60)
    print("TESTING REDDIT SEARCH (OpenAI)")
    print("=" * 60)

    prompt = """Search Reddit for recent discussions about Claude Code, Anthropic Claude, or AI coding assistants.
Find 10-15 relevant posts from subreddits like r/ClaudeAI, r/LocalLLaMA, r/MachineLearning.
Return posts with their Reddit URLs."""

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": OPENAI_MODEL,
                "tools": [{
                    "type": "web_search",
                    "web_search": {
                        "search_context_size": "high"
                    }
                }],
                "input": [{"role": "user", "content": prompt}]
            },
            timeout=120
        )

        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            print(response.text[:500])
            return None, []

        data = response.json()
        print(f"\nResponse keys: {list(data.keys())}")
        print(f"Output count: {len(data.get('output', []))}")

        items = []
        full_text = ""

        for i, item in enumerate(data.get("output", [])):
            item_type = item.get("type", "")
            print(f"\n  output[{i}]: type={item_type}, keys={list(item.keys())}")

            if item_type == "message":
                content_list = item.get("content", [])
                for content in content_list:
                    if content.get("type") == "output_text":
                        text = content.get("text", "")
                        full_text = text
                        print(f"    output_text: {len(text)} chars")
                        print(f"    Preview: {text[:500]}...")

                        # Extract Reddit URLs
                        reddit_pattern = r'(https?://(?:www\.)?reddit\.com/r/\w+/comments/\w+[^\s\)]*)'
                        matches = re.findall(reddit_pattern, text)
                        print(f"    Reddit URLs found: {len(matches)}")

                        for url in matches[:10]:
                            items.append({
                                "url": url.rstrip(".,;:)"),
                                "source": "reddit"
                            })

            # Check for web_search_call with annotations
            if item_type == "web_search_call":
                action = item.get("action", {})
                print(f"    action keys: {list(action.keys())}")
                annotations = action.get("annotations", [])
                print(f"    annotations: {len(annotations)}")
                for ann in annotations[:3]:
                    print(f"      - {ann.get('url', 'no url')[:60]}...")

        return full_text, items


async def test_web_search():
    """Test xAI web_search for general AI news."""
    print("\n" + "=" * 60)
    print("TESTING WEB SEARCH (xAI)")
    print("=" * 60)

    prompt = """Search for recent Anthropic Claude AI news and announcements.
Find 10-15 relevant articles from the last 48 hours."""

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

        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            print(response.text)
            return None, []

        data = response.json()
        print(f"\nResponse keys: {list(data.keys())}")
        print(f"Output count: {len(data.get('output', []))}")

        items = []
        full_text = ""

        for i, item in enumerate(data.get("output", [])):
            item_type = item.get("type", "")
            print(f"\n  output[{i}]: type={item_type}")

            if item_type == "web_search_call":
                action = item.get("action", {})
                sources = action.get("sources", [])
                print(f"    sources: {len(sources)}")
                for src in sources[:3]:
                    print(f"      - {src.get('title', 'no title')[:50]}: {src.get('url', '')[:50]}...")
                    items.append({
                        "title": src.get("title", ""),
                        "url": src.get("url", ""),
                        "source": "web"
                    })

            if item_type == "message":
                content_list = item.get("content", [])
                for content in content_list:
                    if content.get("type") == "output_text":
                        text = content.get("text", "")
                        full_text = text
                        print(f"    output_text: {len(text)} chars")

                        # Extract URLs from text
                        url_pattern = r'(https?://[^\s\)]+)'
                        urls = re.findall(url_pattern, text)
                        print(f"    URLs in text: {len(urls)}")

        return full_text, items


async def main():
    print("Testing Search APIs for Morning Briefing")
    print("=" * 60)

    # Test X search
    x_text, x_items = await test_x_search()
    print(f"\nX Search Result: {len(x_items)} items extracted")

    # Test Reddit search
    reddit_text, reddit_items = await test_reddit_search()
    print(f"\nReddit Search Result: {len(reddit_items)} items extracted")

    # Test Web search
    web_text, web_items = await test_web_search()
    print(f"\nWeb Search Result: {len(web_items)} items extracted")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"X items: {len(x_items)}")
    for item in x_items[:3]:
        print(f"  - {item['url'][:60]}...")

    print(f"\nReddit items: {len(reddit_items)}")
    for item in reddit_items[:3]:
        print(f"  - {item['url'][:60]}...")

    print(f"\nWeb items: {len(web_items)}")
    for item in web_items[:3]:
        print(f"  - {item.get('title', '')[:40]}: {item['url'][:40]}...")


if __name__ == "__main__":
    asyncio.run(main())
