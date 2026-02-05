"""Search Result Formatters - For Brave API search results.

Formats web, news, image, and local search results as Discord embeds.
Based on RESPONSE.md Sections 5.4-5.7 and 10.
"""

import re
from datetime import datetime
from typing import Optional, Any


# Discord embed colour palette (Appendix A)
COLORS = {
    'web_search': 0xFB542B,    # Brave Orange
    'news': 0x1DA1F2,          # Twitter Blue
    'images': 0x7C3AED,        # Purple
    'local': 0x34A853,         # Google Green
}


def truncate(text: str, max_length: int) -> str:
    """Truncate text to max length with ellipsis."""
    if not text or len(text) <= max_length:
        return text or ''
    return text[:max_length - 1] + '…'


def format_relative_time(timestamp: Any) -> str:
    """Format timestamp as relative time (e.g., '2 hours ago')."""
    if not timestamp:
        return ''

    try:
        if isinstance(timestamp, str):
            # Try parsing ISO format
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        elif isinstance(timestamp, datetime):
            dt = timestamp
        else:
            return str(timestamp)

        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        diff = now - dt

        seconds = diff.total_seconds()

        if seconds < 60:
            return 'just now'
        elif seconds < 3600:
            mins = int(seconds / 60)
            return f'{mins} minute{"s" if mins != 1 else ""} ago'
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f'{hours} hour{"s" if hours != 1 else ""} ago'
        elif seconds < 604800:
            days = int(seconds / 86400)
            return f'{days} day{"s" if days != 1 else ""} ago'
        else:
            return dt.strftime('%d %b %Y')
    except Exception:
        return str(timestamp)[:20] if timestamp else ''


def format_search_results(
    text: str,
    context: Optional[dict] = None
) -> dict:
    """Format web search results for Discord.

    Returns dict with 'content' (summary) and 'embed' (results).
    Based on Section 5.4.
    """
    # Try to extract natural language summary (first paragraph before results)
    lines = text.strip().split('\n')
    summary = ''
    results_start = 0

    for i, line in enumerate(lines):
        # Look for start of results (numbered list or URL pattern)
        if re.match(r'^\*?\*?\d+\.?\s*\[', line) or '🔍' in line:
            summary = '\n'.join(lines[:i]).strip()
            results_start = i
            break

    if not summary:
        # No clear summary, use first line
        summary = lines[0] if lines else ''

    # Parse results from text
    results = extract_search_results(text)

    # Build embed
    embed = {
        'color': COLORS['web_search'],
        'author': {'name': '🔍 Web Search'},
        'description': '\n\n'.join(
            f"**{i + 1}. [{r['title']}]({r['url']})**\n{truncate(r.get('snippet', ''), 100)}"
            for i, r in enumerate(results[:10])
        ) if results else text[results_start:],
        'footer': {'text': f"{len(results)} results found"} if results else None
    }

    return {
        'content': summary if summary else None,
        'embed': embed
    }


def format_news_results(
    text: str,
    context: Optional[dict] = None
) -> dict:
    """Format news search results for Discord.

    Based on Section 5.5.
    """
    results = extract_news_results(text)

    embed = {
        'color': COLORS['news'],
        'author': {'name': '📰 News'},
        'description': '\n\n'.join(
            f"**[{r['title']}]({r['url']})**\n"
            f"-# {r.get('source', 'Unknown')} • {format_relative_time(r.get('published_at'))}\n"
            f"{truncate(r.get('snippet', ''), 80)}"
            for r in results[:10]
        ) if results else text,
    }

    return {'embed': embed}


def format_image_results(
    text: str,
    context: Optional[dict] = None
) -> list[dict]:
    """Format image search results as multiple embeds.

    Returns list of embeds (max 3).
    Based on Section 5.6.
    """
    results = extract_image_results(text)

    embeds = []
    for r in results[:3]:
        embed = {
            'color': COLORS['images'],
            'image': {'url': r['url']},
            'footer': {'text': truncate(r.get('title', ''), 50)}
        }
        embeds.append(embed)

    return embeds


def format_local_results(
    text: str,
    context: Optional[dict] = None
) -> dict:
    """Format local/business search results for Discord.

    Based on Section 5.7.
    """
    results = extract_local_results(text)

    embed = {
        'color': COLORS['local'],
        'author': {'name': '📍 Local Results'},
        'description': '\n\n'.join(
            f"**{r['name']}** {'⭐' * round(r.get('rating', 0))}\n"
            f"{r.get('address', '')}\n"
            + (f"📞 {r['phone']}" if r.get('phone') else '')
            for r in results[:10]
        ) if results else text,
    }

    return {'embed': embed}


# =============================================================================
# RESULT EXTRACTION HELPERS
# =============================================================================

def extract_search_results(text: str) -> list[dict]:
    """Extract web search results from text."""
    results = []

    # Pattern 1: **N. [Title](URL)** format
    pattern1 = re.compile(
        r'\*?\*?(\d+)\.\s*\[([^\]]+)\]\(([^)]+)\)\*?\*?'
        r'(?:\n([^\n*]+))?',  # Optional snippet on next line
        re.MULTILINE
    )

    for match in pattern1.finditer(text):
        results.append({
            'title': match.group(2).strip(),
            'url': match.group(3).strip(),
            'snippet': match.group(4).strip() if match.group(4) else ''
        })

    # Pattern 2: Title with URL on same line
    if not results:
        pattern2 = re.compile(
            r'(?:^|\n)([^\n]+?)\s*[-–]\s*(https?://[^\s]+)',
            re.MULTILINE
        )
        for match in pattern2.finditer(text):
            results.append({
                'title': match.group(1).strip(),
                'url': match.group(2).strip(),
                'snippet': ''
            })

    return results


def extract_news_results(text: str) -> list[dict]:
    """Extract news results from text."""
    results = extract_search_results(text)

    # Try to extract source and timestamp
    for r in results:
        # Look for source after title
        source_match = re.search(
            rf'{re.escape(r["title"])}.*?[-–]\s*([A-Za-z][\w\s]+)',
            text
        )
        if source_match:
            r['source'] = source_match.group(1).strip()

        # Look for time indicators
        time_match = re.search(
            rf'{re.escape(r["title"])}.*?(\d+\s*(?:hours?|mins?|days?)\s*ago)',
            text, re.IGNORECASE
        )
        if time_match:
            r['published_at'] = time_match.group(1)

    return results


def extract_image_results(text: str) -> list[dict]:
    """Extract image URLs from text."""
    results = []

    # Find image URLs
    image_pattern = re.compile(
        r'(https?://[^\s<>\])"\']+\.(?:jpg|jpeg|png|gif|webp))',
        re.IGNORECASE
    )

    for match in image_pattern.finditer(text):
        url = match.group(1)
        # Try to find a title near this URL
        title_match = re.search(
            rf'([^\n]+?)\s*{re.escape(url)}',
            text
        )
        results.append({
            'url': url,
            'title': title_match.group(1).strip() if title_match else ''
        })

    return results


def extract_local_results(text: str) -> list[dict]:
    """Extract local business results from text."""
    results = []

    # Pattern: **Name** ⭐⭐⭐\nAddress\n📞 Phone
    pattern = re.compile(
        r'\*\*([^*]+)\*\*\s*(⭐+)?\s*\n'
        r'([^\n]+)\n'
        r'(?:📞\s*([^\n]+))?',
        re.MULTILINE
    )

    for match in pattern.finditer(text):
        rating = len(match.group(2)) if match.group(2) else 0
        results.append({
            'name': match.group(1).strip(),
            'rating': rating,
            'address': match.group(3).strip(),
            'phone': match.group(4).strip() if match.group(4) else None
        })

    return results


# =============================================================================
# TESTING
# =============================================================================

def test_search_formatters():
    """Run basic search formatter tests."""
    # Test web search
    web_text = """Based on my search, here are the results:

**1. [LEGO Technic 42100](https://ebay.co.uk/123)**
Great set for collectors

**2. [Liebherr Excavator](https://amazon.co.uk/456)**
Available with free shipping"""

    result = format_search_results(web_text)

    if 'embed' in result and result['embed']['color'] == COLORS['web_search']:
        print("✓ PASS - Web search format")
    else:
        print("✗ FAIL - Web search format")

    # Test news
    news_text = """📰 News results:

**[LEGO announces new set](https://news.com/1)** - TechNews - 2 hours ago
Big announcement today"""

    result = format_news_results(news_text)

    if 'embed' in result and result['embed']['color'] == COLORS['news']:
        print("✓ PASS - News search format")
    else:
        print("✗ FAIL - News search format")

    # Test relative time
    if format_relative_time(None) == '':
        print("✓ PASS - Relative time handles None")
    else:
        print("✗ FAIL - Relative time handles None")

    print("\nSearch formatter tests complete")


if __name__ == '__main__':
    test_search_formatters()
