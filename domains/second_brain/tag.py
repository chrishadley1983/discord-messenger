"""AI topic extraction/tagging for Second Brain using Claude API.

Extracts 3-8 topic tags, preferring known domain tags from SECOND-BRAIN.md Section 11.2.
"""

import json
import re

import httpx

from logger import logger
from .config import get_claude_api_key, KNOWN_DOMAIN_TAGS


# Tagging prompt from SECOND-BRAIN.md Section 11.2
TAG_PROMPT = """Extract 3-8 topic tags for this content. Use lowercase, hyphenated tags.
Prefer these known domains when applicable:
- hadley-bricks, ebay, bricklink, brick-owl, amazon
- lego, lego-investing, retired-sets, minifigures
- running, marathon, training, nutrition, garmin
- family, max, emmie, abby, japan-trip
- tech, development, peterbot, familyfuel
- finance, tax, self-employment

Content: {text}

Return as JSON array: ["tag1", "tag2", ...]"""


async def extract_topics(text: str, title: str | None = None) -> list[str]:
    """Extract topic tags from content.

    Args:
        text: Full content text
        title: Optional title for context

    Returns:
        List of 3-8 topic tags
    """
    api_key = get_claude_api_key()
    if not api_key:
        logger.warning("Claude API key not configured, using keyword extraction")
        return _fallback_topics(text, title)

    # Truncate text for API call
    truncated_text = text[:4000] if len(text) > 4000 else text

    prompt = TAG_PROMPT.format(text=truncated_text)
    if title:
        prompt = f"Title: {title}\n\n{prompt}"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-3-5-haiku-latest",
                    "max_tokens": 100,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                },
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()

        response_text = data["content"][0]["text"].strip()

        # Parse JSON array from response
        tags = _parse_tags_response(response_text)
        logger.debug(f"Extracted tags: {tags}")
        return tags

    except Exception as e:
        logger.error(f"Claude tagging failed: {e}")
        return _fallback_topics(text, title)


def _parse_tags_response(response: str) -> list[str]:
    """Parse tags from Claude response."""
    # Try to parse as JSON
    try:
        # Find JSON array in response
        match = re.search(r'\[.*?\]', response, re.DOTALL)
        if match:
            tags = json.loads(match.group())
            if isinstance(tags, list):
                # Normalize tags
                return [_normalize_tag(t) for t in tags if isinstance(t, str)][:8]
    except json.JSONDecodeError:
        pass

    # Fall back to extracting words that look like tags
    tags = []
    words = response.lower().split()
    for word in words:
        # Clean up word
        clean = re.sub(r'[^\w-]', '', word)
        if clean and len(clean) > 2 and clean not in ['the', 'and', 'for', 'tag']:
            tags.append(_normalize_tag(clean))
            if len(tags) >= 8:
                break

    return tags if tags else ['untagged']


def _normalize_tag(tag: str) -> str:
    """Normalize a tag to lowercase with hyphens."""
    tag = tag.lower().strip()
    # Replace spaces and underscores with hyphens
    tag = re.sub(r'[\s_]+', '-', tag)
    # Remove non-alphanumeric except hyphens
    tag = re.sub(r'[^a-z0-9-]', '', tag)
    # Remove leading/trailing hyphens
    tag = tag.strip('-')
    return tag


def _fallback_topics(text: str, title: str | None = None) -> list[str]:
    """Extract topics using keyword matching (no API)."""
    tags = set()
    combined = (title or '') + ' ' + text[:2000]
    combined_lower = combined.lower()

    # Check for known domain tags
    for domain_tag in KNOWN_DOMAIN_TAGS:
        # Convert tag to searchable forms
        variants = [
            domain_tag,
            domain_tag.replace('-', ' '),
            domain_tag.replace('-', ''),
        ]
        for variant in variants:
            if variant in combined_lower:
                tags.add(domain_tag)
                break

    # Add some generic topic detection
    topic_patterns = {
        'article': r'\barticle\b|\bblog\b|\bpost\b',
        'video': r'\bvideo\b|\byoutube\b',
        'tutorial': r'\bhow to\b|\btutorial\b|\bguide\b',
        'news': r'\bnews\b|\bannouncement\b|\bupdate\b',
        'review': r'\breview\b|\brating\b',
        'research': r'\bresearch\b|\bstudy\b|\banalysis\b',
    }

    for tag, pattern in topic_patterns.items():
        if re.search(pattern, combined_lower):
            tags.add(tag)

    result = list(tags)[:8]
    return result if result else ['general']


async def suggest_related_tags(existing_tags: list[str]) -> list[str]:
    """Suggest related tags based on existing tags.

    Useful for connection discovery.
    """
    # Simple relatedness based on known domain groupings
    related = set()

    tag_groups = {
        'business': ['hadley-bricks', 'ebay', 'bricklink', 'brick-owl', 'amazon', 'finance', 'tax'],
        'lego': ['lego', 'lego-investing', 'retired-sets', 'minifigures', 'hadley-bricks'],
        'fitness': ['running', 'marathon', 'training', 'nutrition', 'garmin'],
        'family': ['family', 'max', 'emmie', 'abby', 'japan-trip'],
        'tech': ['tech', 'development', 'peterbot', 'familyfuel'],
    }

    for tag in existing_tags:
        for group_name, group_tags in tag_groups.items():
            if tag in group_tags:
                related.update(group_tags)

    # Remove existing tags
    related -= set(existing_tags)
    return list(related)
