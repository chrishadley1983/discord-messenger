"""AI summarisation for Second Brain using Claude API.

Generates 2-3 sentence summaries focused on key insights and actionable information.
"""

import httpx

from logger import logger
from .config import get_claude_api_key


# Summarisation prompt from SECOND-BRAIN.md Section 11.1
SUMMARISE_PROMPT = """Summarise this content in 2-3 sentences. Focus on the key insight
or actionable information. Be specific — include numbers, names,
and dates where relevant.

Content: {text}"""


async def generate_summary(text: str, title: str | None = None) -> str:
    """Generate a 2-3 sentence summary of the content.

    Args:
        text: Full content text
        title: Optional title for context

    Returns:
        Summary string (2-3 sentences)
    """
    api_key = get_claude_api_key()
    if not api_key:
        logger.warning("Claude API key not configured, using first paragraph as summary")
        return _fallback_summary(text)

    # Truncate text for API call (keep costs low)
    truncated_text = text[:6000] if len(text) > 6000 else text

    prompt = SUMMARISE_PROMPT.format(text=truncated_text)
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
                    "max_tokens": 200,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

        summary = data["content"][0]["text"].strip()
        logger.debug(f"Generated summary: {summary[:100]}...")
        return summary

    except Exception as e:
        logger.error(f"Claude summarisation failed: {e}")
        return _fallback_summary(text)


def _fallback_summary(text: str) -> str:
    """Generate fallback summary from first paragraph."""
    # Split into paragraphs
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

    if not paragraphs:
        return text[:200] if len(text) > 200 else text

    # Get first meaningful paragraph
    for para in paragraphs:
        # Skip very short paragraphs (likely headers)
        if len(para) > 50:
            # Truncate to ~3 sentences
            sentences = para.replace('. ', '.|').split('|')[:3]
            return '. '.join(s.strip() for s in sentences if s.strip()) + '.'

    # Fallback to first paragraph
    return paragraphs[0][:200] + ('...' if len(paragraphs[0]) > 200 else '')


async def extract_title(text: str) -> str:
    """Extract or generate a title for content without one.

    Args:
        text: Full content text

    Returns:
        Generated title
    """
    api_key = get_claude_api_key()
    if not api_key:
        # Fallback: use first line or first N words
        first_line = text.split('\n')[0].strip()
        if len(first_line) > 10 and len(first_line) < 100:
            return first_line
        words = text.split()[:10]
        return ' '.join(words) + ('...' if len(text.split()) > 10 else '')

    # Truncate text for API call
    truncated_text = text[:2000] if len(text) > 2000 else text

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
                    "max_tokens": 50,
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Generate a short, descriptive title (5-10 words) for this content:\n\n{truncated_text}"
                        }
                    ],
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

        title = data["content"][0]["text"].strip()
        # Remove quotes if present
        title = title.strip('"\'')
        logger.debug(f"Generated title: {title}")
        return title

    except Exception as e:
        logger.error(f"Claude title generation failed: {e}")
        # Fallback
        first_line = text.split('\n')[0].strip()
        if len(first_line) > 10 and len(first_line) < 100:
            return first_line
        words = text.split()[:10]
        return ' '.join(words) + '...'
