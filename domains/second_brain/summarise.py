"""AI summarisation for Second Brain using Claude API.

Generates 2-3 sentence summaries focused on key insights and actionable information.
"""

from logger import logger
from .config import call_claude


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
    truncated_text = text[:6000] if len(text) > 6000 else text
    prompt = SUMMARISE_PROMPT.format(text=truncated_text)
    if title:
        prompt = f"Title: {title}\n\n{prompt}"

    result = await call_claude(prompt, max_tokens=200, timeout=30)
    if result:
        logger.debug(f"Generated summary: {result[:100]}...")
        return result

    logger.warning("Summary generation failed, using fallback")
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
    truncated_text = text[:2000] if len(text) > 2000 else text
    prompt = f"Generate a short, descriptive title (5-10 words) for this content:\n\n{truncated_text}"

    result = await call_claude(prompt, max_tokens=50, timeout=15)
    if result:
        title = result.strip('"\'')
        logger.debug(f"Generated title: {title}")
        return title

    # Fallback: use first line or first N words
    first_line = text.split('\n')[0].strip()
    if len(first_line) > 10 and len(first_line) < 100:
        return first_line
    words = text.split()[:10]
    return ' '.join(words) + ('...' if len(text.split()) > 10 else '')
