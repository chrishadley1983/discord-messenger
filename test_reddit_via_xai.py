"""Test if xAI web_search can find Reddit posts."""

import asyncio
import re
import httpx
from config import GROK_API_KEY

GROK_MODEL = "grok-4-1-fast"


async def test_reddit_via_xai():
    """Test xAI web_search specifically for Reddit content."""
    print("Testing xAI web_search for Reddit content...")

    prompt = """Search for recent Reddit discussions about Claude Code, Claude AI, or Anthropic.

Focus on finding posts from:
- r/ClaudeAI
- r/LocalLLaMA
- r/MachineLearning
- r/artificial

Find 10-15 relevant Reddit posts from the last week. Include the full reddit.com URLs."""

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
            return

        data = response.json()
        print(f"\nOutput count: {len(data.get('output', []))}")

        for i, item in enumerate(data.get("output", [])):
            item_type = item.get("type", "")
            print(f"\n  output[{i}]: type={item_type}")

            if item_type == "message":
                content_list = item.get("content", [])
                for content in content_list:
                    if content.get("type") == "output_text":
                        text = content.get("text", "")
                        print(f"    Text length: {len(text)} chars")
                        print(f"    Preview: {text[:800]}...")

                        # Extract Reddit URLs
                        reddit_pattern = r'(https?://(?:www\.)?reddit\.com/r/\w+/comments/[^\s\)\]]+)'
                        matches = re.findall(reddit_pattern, text)
                        print(f"\n    Reddit URLs found: {len(matches)}")
                        for url in matches[:10]:
                            clean_url = url.rstrip(".,;:)")
                            print(f"      - {clean_url}")

                        # Also check for any reddit.com mentions
                        all_reddit = re.findall(r'reddit\.com[^\s\)]*', text)
                        print(f"\n    All reddit.com references: {len(all_reddit)}")


if __name__ == "__main__":
    asyncio.run(test_reddit_via_xai())
