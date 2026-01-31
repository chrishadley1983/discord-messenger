"""Test the full morning briefing pipeline."""

import asyncio
import sys

# Add project root to path
sys.path.insert(0, '.')

from jobs.morning_briefing import _fetch_raw_data_from_grok


async def main():
    print("Testing full Grok search pipeline...")
    print("This will take 30-60 seconds...\n")

    result = await _fetch_raw_data_from_grok()

    print("\n" + "="*60)
    print("RAW DATA RESULT")
    print("="*60)

    if result.startswith("Error"):
        print(f"FAILED: {result}")
    else:
        # Show first 2000 chars
        print(result[:2000])
        print(f"\n... ({len(result)} total chars)")

        # Count URLs
        import re
        urls = re.findall(r'https?://[^\s\)]+', result)
        print(f"\nFound {len(urls)} URLs in the result")

        # Show some URLs
        x_urls = [u for u in urls if 'x.com' in u or 'twitter.com' in u]
        other_urls = [u for u in urls if 'x.com' not in u and 'twitter.com' not in u]

        print(f"\nX/Twitter URLs: {len(x_urls)}")
        for url in x_urls[:5]:
            print(f"  - {url}")

        print(f"\nWeb URLs: {len(other_urls)}")
        for url in other_urls[:5]:
            print(f"  - {url}")


if __name__ == "__main__":
    asyncio.run(main())
