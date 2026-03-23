"""AI topic extraction/tagging for Second Brain using Claude API.

Extracts 3-8 topic tags per item. Tags describe SUBJECT MATTER, not format.
Uses content_type context to guide tag extraction.
"""

import json
import re

from logger import logger
from .config import call_claude, KNOWN_DOMAIN_TAGS, KNOWN_DOMAIN_TAG_GROUPS


# Content-type-aware tagging prompt
TAG_PROMPT = """Extract 3-8 topic tags for this content. Use lowercase, hyphenated tags.
Content type: {content_type}

RULES:
- Tag the SUBJECT MATTER, not the format or source
- NEVER use these tags: email, general, calendar, untagged, claude-history, note, conversation
- Prefer known domain tags when they match the content

Known domain tags by category:
{tag_groups}

EXAMPLES of good tagging:
- An email about LEGO set 10305 price drop → ["lego-investing", "retired-sets", "hadley-bricks"]
- A calendar event for Max's parents evening → ["school", "stocks-green", "max", "parents-evening"]
- A Garmin activity from parkrun → ["running", "parkrun", "garmin", "fitness"]

Title: {title}
Content: {text}

Return as JSON array: ["tag1", "tag2", ...]"""


def _format_tag_groups() -> str:
    """Format tag groups for the prompt."""
    lines = []
    for group, tags in KNOWN_DOMAIN_TAG_GROUPS.items():
        lines.append(f"  {group}: {', '.join(tags)}")
    return "\n".join(lines)


async def extract_topics(
    text: str,
    title: str | None = None,
    content_type: str | None = None,
) -> list[str]:
    """Extract topic tags from content.

    Args:
        text: Full content text
        title: Optional title for context
        content_type: Content type string for context-aware tagging

    Returns:
        List of 3-8 topic tags
    """
    truncated_text = text[:4000] if len(text) > 4000 else text
    prompt = TAG_PROMPT.format(
        text=truncated_text,
        title=title or "Untitled",
        content_type=content_type or "unknown",
        tag_groups=_format_tag_groups(),
    )

    result = await call_claude(prompt, max_tokens=100, timeout=20)
    if result:
        tags = _parse_tags_response(result)
        # Filter out banned tags
        tags = _filter_noise_tags(tags)
        if tags:
            logger.debug(f"Extracted tags: {tags}")
            return tags

    logger.warning("Tag extraction failed, using keyword fallback")
    return _fallback_topics(text, title, content_type)


# Tags that describe format/source, not content — always filter out
_NOISE_TAGS = frozenset({
    "email", "general", "calendar", "untagged", "claude-history",
    "note", "conversation", "document", "bookmark", "url",
})


def _filter_noise_tags(tags: list[str]) -> list[str]:
    """Remove tags that describe format rather than content."""
    filtered = [t for t in tags if t not in _NOISE_TAGS]
    return filtered if filtered else tags  # Keep originals if all were noise


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


# Content-type to default topic mapping (used when fallback finds nothing)
_CONTENT_TYPE_DEFAULTS: dict[str, list[str]] = {
    "email": ["communication"],
    "calendar_event": ["scheduling"],
    "health_activity": ["fitness", "garmin"],
    "financial_report": ["finance"],
    "listening_history": ["music", "spotify"],
    "viewing_history": ["entertainment", "netflix"],
    "commit": ["development"],
    "code": ["development", "tech"],
    "recipe": ["cooking", "food"],
    "travel_booking": ["travel"],
    "conversation_extract": ["conversation"],
    "bookmark": ["reference"],
}


def _fallback_topics(
    text: str,
    title: str | None = None,
    content_type: str | None = None,
) -> list[str]:
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
    if result:
        return result

    # Use content-type-based defaults instead of "general"
    if content_type and content_type in _CONTENT_TYPE_DEFAULTS:
        return _CONTENT_TYPE_DEFAULTS[content_type]

    return ['unclassified']


async def suggest_related_tags(existing_tags: list[str]) -> list[str]:
    """Suggest related tags based on existing tags."""
    related = set()

    for tag in existing_tags:
        for group_name, group_tags in KNOWN_DOMAIN_TAG_GROUPS.items():
            if tag in group_tags:
                related.update(group_tags)

    # Remove existing tags
    related -= set(existing_tags)
    return list(related)
