"""Quick test script to debug xAI Responses API structure."""

import asyncio
import json
import re
import httpx
from config import GROK_API_KEY

def parse_search_response(response_data: dict, source: str) -> list[dict]:
    """Parse xAI Responses API output to extract items with URLs."""
    items = []

    output = response_data.get("output", [])

    for item in output:
        item_type = item.get("type", "")

        # Type: web_search_call - URLs are in action.sources
        if item_type == "web_search_call":
            action = item.get("action", {})
            sources = action.get("sources", [])
            print(f"  {source} web_search_call has {len(sources)} sources")
            for src in sources:
                url = src.get("url", "")
                if url:
                    title = src.get("title", src.get("snippet", ""))
                    items.append({
                        "text": title[:500] if title else "",
                        "url": url,
                        "author": src.get("domain", ""),
                        "source": source
                    })

        # Type: message - contains the response text with inline citations
        elif item_type == "message":
            content_list = item.get("content", [])
            for content in content_list:
                if content.get("type") == "output_text":
                    text = content.get("text", "")
                    if text:
                        print(f"  {source} message output_text: {len(text)} chars")
                        # Extract URLs from inline citations like [[1]](https://x.com/...)
                        url_pattern = r'\[\[\d+\]\]\((https?://[^\)]+)\)'
                        urls = re.findall(url_pattern, text)
                        print(f"  {source} found {len(urls)} inline citation URLs")
                        for url in urls:
                            if url and not any(i["url"] == url for i in items):
                                items.append({
                                    "text": "",
                                    "url": url,
                                    "author": "",
                                    "source": source
                                })
                        # Fallback: extract any URLs from text
                        if not urls:
                            all_urls = re.findall(r'https?://[^\s\)]+', text)
                            print(f"  {source} fallback found {len(all_urls)} URLs")
                            for url in all_urls[:20]:
                                if not any(i["url"] == url for i in items):
                                    items.append({
                                        "text": "",
                                        "url": url,
                                        "author": "",
                                        "source": source
                                    })

    return items

async def test_web_search():
    """Test web search and verify parsing."""
    print("\n" + "="*60)
    print("TESTING WEB SEARCH")
    print("="*60)

    prompt = "Search for recent Anthropic Claude AI news"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.x.ai/v1/responses",
            headers={
                "Authorization": f"Bearer {GROK_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "grok-4-1-fast",
                "tools": [{"type": "web_search"}],
                "input": [{"role": "user", "content": prompt}]
            },
            timeout=120
        )

        if response.status_code == 200:
            data = response.json()

            print(f"\nOutput array count: {len(data.get('output', []))}")
            for i, item in enumerate(data.get("output", [])):
                print(f"  output[{i}]: type={item.get('type')}")

            print("\nParsing response...")
            items = parse_search_response(data, "web")

            print(f"\n=== PARSED {len(items)} ITEMS ===")
            for i, item in enumerate(items[:10]):
                print(f"  [{i}] {item['url'][:60]}...")
                if item['text']:
                    print(f"       Title: {item['text'][:50]}...")

            return items
        else:
            print(f"Error: {response.status_code}")
            print(response.text)
            return []

async def test_x_search():
    """Test X search and verify parsing."""
    print("\n" + "="*60)
    print("TESTING X SEARCH")
    print("="*60)

    prompt = "Search X for posts about Claude Code MCP"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.x.ai/v1/responses",
            headers={
                "Authorization": f"Bearer {GROK_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "grok-4-1-fast",
                "tools": [{"type": "x_search"}],
                "input": [{"role": "user", "content": prompt}]
            },
            timeout=120
        )

        if response.status_code == 200:
            data = response.json()

            print(f"\nOutput array count: {len(data.get('output', []))}")
            for i, item in enumerate(data.get("output", [])):
                print(f"  output[{i}]: type={item.get('type')}")

            print("\nParsing response...")
            items = parse_search_response(data, "x")

            print(f"\n=== PARSED {len(items)} ITEMS ===")
            for i, item in enumerate(items[:10]):
                print(f"  [{i}] {item['url']}")

            return items
        else:
            print(f"Error: {response.status_code}")
            print(response.text)
            return []

if __name__ == "__main__":
    print("Testing xAI Responses API parsing...")

    web_items = asyncio.run(test_web_search())
    x_items = asyncio.run(test_x_search())

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Web search: {len(web_items)} items")
    print(f"X search: {len(x_items)} items")
    print(f"Total: {len(web_items) + len(x_items)} items")

    if web_items or x_items:
        print("\n✅ PARSING IS WORKING!")
    else:
        print("\n❌ NO ITEMS PARSED - NEEDS FIXING")
