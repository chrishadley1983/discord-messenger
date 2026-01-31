"""Test the complete morning briefing pipeline."""

import asyncio
import sys
sys.path.insert(0, '.')

from jobs.morning_briefing import (
    _search_x,
    _search_reddit,
    _search_web,
    _fetch_raw_data_from_grok,
    _curate_with_sonnet
)
from datetime import datetime, timedelta


async def test_x_search():
    """Test X search independently."""
    print("\n" + "=" * 60)
    print("TEST 1: X SEARCH")
    print("=" * 60)

    today = datetime.utcnow()
    from_date = (today - timedelta(days=2)).strftime("%Y-%m-%d")
    to_date = today.strftime("%Y-%m-%d")

    items = await _search_x("Claude Code MCP", from_date, to_date)

    print(f"\nResults: {len(items)} items")
    for i, item in enumerate(items[:5]):
        print(f"\n  [{i+1}] {item.get('text', 'No title')[:60]}...")
        print(f"      URL: {item.get('url', '')[:70]}...")
        print(f"      Source: {item.get('source', '')}")

    return len(items) > 0


async def test_reddit_search():
    """Test Reddit search independently."""
    print("\n" + "=" * 60)
    print("TEST 2: REDDIT SEARCH")
    print("=" * 60)

    items = await _search_reddit("Claude Code Claude AI Anthropic")

    print(f"\nResults: {len(items)} items")
    for i, item in enumerate(items[:5]):
        print(f"\n  [{i+1}] {item.get('text', 'No title')[:60]}...")
        print(f"      URL: {item.get('url', '')[:70]}...")
        print(f"      Subreddit: {item.get('subreddit', '')}")

    return len(items) > 0


async def test_web_search():
    """Test Web search independently."""
    print("\n" + "=" * 60)
    print("TEST 3: WEB SEARCH")
    print("=" * 60)

    items = await _search_web("Anthropic Claude AI announcements news")

    print(f"\nResults: {len(items)} items")
    for i, item in enumerate(items[:5]):
        print(f"\n  [{i+1}] {item.get('text', 'No title')[:60]}...")
        print(f"      URL: {item.get('url', '')[:70]}...")

    return len(items) > 0


async def test_full_pipeline():
    """Test the complete pipeline."""
    print("\n" + "=" * 60)
    print("TEST 4: FULL PIPELINE")
    print("=" * 60)

    print("\nFetching raw data from Grok...")
    raw_data = await _fetch_raw_data_from_grok()

    if raw_data.startswith("Error"):
        print(f"FAILED: {raw_data}")
        return False

    print(f"\nRaw data length: {len(raw_data)} chars")
    print("\nRaw data preview:")
    print("-" * 40)
    # Encode to handle unicode issues on Windows
    preview = raw_data[:1500].encode('ascii', 'replace').decode('ascii')
    print(preview)
    print("-" * 40)

    # Check for source diversity
    has_x = "### X (Twitter) Posts" in raw_data
    has_reddit = "### Reddit Discussions" in raw_data
    has_web = "### Web Articles" in raw_data

    print(f"\nSource diversity check:")
    print(f"  X posts: {'YES' if has_x else 'NO'}")
    print(f"  Reddit: {'YES' if has_reddit else 'NO'}")
    print(f"  Web: {'YES' if has_web else 'NO'}")

    # Count URLs
    import re
    x_urls = len(re.findall(r'https?://(?:x\.com|twitter\.com)', raw_data))
    reddit_urls = len(re.findall(r'https?://(?:www\.)?reddit\.com', raw_data))
    web_urls = len(re.findall(r'URL: https?://', raw_data)) - x_urls - reddit_urls

    print(f"\nURL counts:")
    print(f"  X URLs: {x_urls}")
    print(f"  Reddit URLs: {reddit_urls}")
    print(f"  Web URLs: {web_urls}")

    return has_x or has_reddit or has_web


async def test_sonnet_curation():
    """Test Sonnet curation with real data."""
    print("\n" + "=" * 60)
    print("TEST 5: SONNET CURATION")
    print("=" * 60)

    print("\nFetching raw data first...")
    raw_data = await _fetch_raw_data_from_grok()

    if raw_data.startswith("Error"):
        print(f"FAILED: Cannot test curation without raw data")
        return False

    print("\nCurating with Sonnet...")
    date_str = datetime.utcnow().strftime("%a %d %b %Y")
    briefing = await _curate_with_sonnet(raw_data, date_str)

    print(f"\nBriefing length: {len(briefing)} chars")
    print("\nFinal briefing:")
    print("=" * 40)
    # Encode to handle unicode issues on Windows
    briefing_safe = briefing.encode('ascii', 'replace').decode('ascii')
    print(briefing_safe)
    print("=" * 40)

    # Check sections
    has_news = "NEWS HEADLINES" in briefing
    has_claude = "CLAUDE CODE CORNER" in briefing
    has_buzz = "COMMUNITY BUZZ" in briefing
    has_reddit = "REDDIT ROUNDUP" in briefing
    has_moltbot = "MOLTBOT CORNER" in briefing

    print(f"\nSection check:")
    print(f"  News Headlines: {'YES' if has_news else 'NO'}")
    print(f"  Claude Code Corner: {'YES' if has_claude else 'NO'}")
    print(f"  Community Buzz: {'YES' if has_buzz else 'NO'}")
    print(f"  Reddit Roundup: {'YES' if has_reddit else 'NO'}")
    print(f"  Moltbot Corner: {'YES' if has_moltbot else 'NO'}")

    # Check for URLs in output (both <url> and plain url formats)
    import re
    urls_bracketed = re.findall(r'<(https?://[^>]+)>', briefing)
    urls_plain = re.findall(r'(?<!<)(https?://[^\s>]+)', briefing)
    all_urls = urls_bracketed + urls_plain

    print(f"\nURLs in output: {len(all_urls)} ({len(urls_bracketed)} bracketed, {len(urls_plain)} plain)")
    for url in all_urls[:8]:
        print(f"  - {url[:70]}...")

    # Check source diversity in URLs
    x_urls = [u for u in all_urls if 'x.com' in u or 'twitter.com' in u]
    reddit_urls = [u for u in all_urls if 'reddit.com' in u]
    web_urls = [u for u in all_urls if 'x.com' not in u and 'reddit.com' not in u]

    print(f"\nURL source diversity:")
    print(f"  X/Twitter: {len(x_urls)}")
    print(f"  Reddit: {len(reddit_urls)}")
    print(f"  Web: {len(web_urls)}")

    return len(all_urls) > 5 and len(x_urls) > 0 and len(reddit_urls) > 0


async def main():
    print("Morning Briefing Pipeline Tests")
    print("=" * 60)

    results = {}

    # Test 1: X Search
    results['x_search'] = await test_x_search()

    # Test 2: Reddit Search
    results['reddit_search'] = await test_reddit_search()

    # Test 3: Web Search
    results['web_search'] = await test_web_search()

    # Test 4: Full Pipeline
    results['full_pipeline'] = await test_full_pipeline()

    # Test 5: Sonnet Curation
    results['sonnet_curation'] = await test_sonnet_curation()

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    all_passed = True
    for test, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {test}: {status}")
        if not passed:
            all_passed = False

    print("\n" + ("ALL TESTS PASSED!" if all_passed else "SOME TESTS FAILED"))
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
