"""URL and content extraction for Second Brain.

Handles:
- Web articles (via readability-lxml)
- Reddit posts
- YouTube (title + description)
- PDFs
- Plain text

Respects size limits: 10k words max, 10 words min.
"""

import re
from typing import Optional
from urllib.parse import urlparse

import httpx
from readability import Document

from logger import logger
from .config import MIN_CONTENT_WORDS, MAX_CONTENT_WORDS
from .types import ExtractedContent


# Common URL patterns
YOUTUBE_PATTERN = re.compile(
    r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})'
)
REDDIT_PATTERN = re.compile(r'reddit\.com/r/\w+/comments/\w+')


async def extract_content(source: str) -> ExtractedContent:
    """Extract content from URL or plain text.

    Args:
        source: URL or plain text content

    Returns:
        ExtractedContent with title, text, source, etc.
    """
    # Check if it's a URL
    if source.startswith(('http://', 'https://')):
        return await extract_from_url(source)
    else:
        # Plain text - treat as note/idea
        return extract_from_text(source)


async def extract_from_url(url: str) -> ExtractedContent:
    """Extract content from a URL."""
    parsed = urlparse(url)

    # Special handling for different content types
    if YOUTUBE_PATTERN.search(url):
        return await _extract_youtube(url)
    elif REDDIT_PATTERN.search(url):
        return await _extract_reddit(url)
    elif url.lower().endswith('.pdf'):
        return await _extract_pdf(url)
    else:
        return await _extract_web_article(url)


def extract_from_text(text: str) -> ExtractedContent:
    """Extract content from plain text (note/idea)."""
    # Clean up whitespace
    text = text.strip()
    words = text.split()
    word_count = len(words)

    # Check minimum length
    if word_count < MIN_CONTENT_WORDS:
        logger.warning(f"Content too short: {word_count} words (min: {MIN_CONTENT_WORDS})")
        # Still allow it, but flag it
        pass

    # Truncate if too long
    if word_count > MAX_CONTENT_WORDS:
        logger.warning(f"Truncating content from {word_count} to {MAX_CONTENT_WORDS} words")
        words = words[:MAX_CONTENT_WORDS]
        text = ' '.join(words) + '\n\n[Content truncated]'
        word_count = MAX_CONTENT_WORDS

    # Generate title from first line or first N words
    first_line = text.split('\n')[0].strip()
    if len(first_line) > 100:
        title = first_line[:97] + '...'
    elif len(first_line) > 10:
        title = first_line
    else:
        title = ' '.join(words[:10]) + ('...' if word_count > 10 else '')

    return ExtractedContent(
        title=title,
        text=text,
        source='direct_input',
        excerpt=text[:200] if len(text) > 200 else text,
        word_count=word_count,
    )


async def _extract_web_article(url: str) -> ExtractedContent:
    """Extract content from a web article using readability."""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (compatible; PeterBot/1.0; +https://github.com/peterbot)',
                },
                timeout=30,
            )
            response.raise_for_status()
            html = response.text

        # Parse with readability
        doc = Document(html)
        title = doc.title()
        content = doc.summary()

        # Convert HTML to plain text
        text = _html_to_text(content)
        words = text.split()
        word_count = len(words)

        # Check size limits
        if word_count < MIN_CONTENT_WORDS:
            logger.warning(f"Extracted content too short: {word_count} words from {url}")

        if word_count > MAX_CONTENT_WORDS:
            logger.warning(f"Truncating content from {word_count} to {MAX_CONTENT_WORDS} words")
            words = words[:MAX_CONTENT_WORDS]
            text = ' '.join(words) + '\n\n[Content truncated]'
            word_count = MAX_CONTENT_WORDS

        # Get excerpt
        excerpt = text[:300] if len(text) > 300 else text

        # Try to get site name from URL
        parsed = urlparse(url)
        site_name = parsed.netloc.replace('www.', '')

        return ExtractedContent(
            title=title or url,
            text=text,
            source=url,
            excerpt=excerpt,
            site_name=site_name,
            word_count=word_count,
        )

    except Exception as e:
        logger.error(f"Failed to extract from {url}: {e}")
        # Return minimal content with the URL
        return ExtractedContent(
            title=url,
            text=f"[Failed to extract content from {url}]\nError: {str(e)}",
            source=url,
            word_count=0,
        )


async def _extract_youtube(url: str) -> ExtractedContent:
    """Extract YouTube video info (title + description)."""
    match = YOUTUBE_PATTERN.search(url)
    if not match:
        return ExtractedContent(
            title="YouTube Video",
            text=f"YouTube video: {url}",
            source=url,
            word_count=3,
        )

    video_id = match.group(1)

    try:
        # Use oEmbed to get video info (no API key needed)
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"

        async with httpx.AsyncClient() as client:
            response = await client.get(oembed_url, timeout=10)
            response.raise_for_status()
            data = response.json()

        title = data.get('title', 'YouTube Video')
        author = data.get('author_name', 'Unknown')

        # Construct content
        text = f"YouTube Video: {title}\nChannel: {author}\nURL: {url}"

        return ExtractedContent(
            title=title,
            text=text,
            source=url,
            site_name='YouTube',
            word_count=len(text.split()),
        )

    except Exception as e:
        logger.warning(f"Failed to get YouTube info for {video_id}: {e}")
        return ExtractedContent(
            title="YouTube Video",
            text=f"YouTube video: {url}",
            source=url,
            site_name='YouTube',
            word_count=3,
        )


async def _extract_reddit(url: str) -> ExtractedContent:
    """Extract Reddit post content."""
    try:
        # Add .json to URL to get JSON response
        json_url = url.rstrip('/') + '.json'

        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                json_url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (compatible; PeterBot/1.0)',
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

        # Extract post data
        post = data[0]['data']['children'][0]['data']
        title = post.get('title', 'Reddit Post')
        selftext = post.get('selftext', '')
        author = post.get('author', 'unknown')
        subreddit = post.get('subreddit', 'unknown')

        # Get top comments
        comments_text = ""
        try:
            comments = data[1]['data']['children'][:5]  # Top 5 comments
            for comment in comments:
                if comment['kind'] == 't1':  # Comment
                    comment_data = comment['data']
                    comment_body = comment_data.get('body', '')[:500]
                    comment_author = comment_data.get('author', 'unknown')
                    comments_text += f"\n\n---\nComment by u/{comment_author}:\n{comment_body}"
        except (KeyError, IndexError):
            pass

        # Construct full text
        text = f"**{title}**\n\nPosted by u/{author} in r/{subreddit}\n\n{selftext}{comments_text}"
        words = text.split()
        word_count = len(words)

        # Truncate if needed
        if word_count > MAX_CONTENT_WORDS:
            words = words[:MAX_CONTENT_WORDS]
            text = ' '.join(words) + '\n\n[Content truncated]'
            word_count = MAX_CONTENT_WORDS

        return ExtractedContent(
            title=title,
            text=text,
            source=url,
            site_name=f"Reddit r/{subreddit}",
            word_count=word_count,
        )

    except Exception as e:
        logger.warning(f"Failed to extract Reddit post from {url}: {e}")
        return await _extract_web_article(url)  # Fall back to web extraction


async def _extract_pdf(url: str) -> ExtractedContent:
    """Extract text from PDF URL.

    Note: Requires pypdf2 or similar. Falls back to URL-only if not available.
    """
    try:
        import io
        from pypdf import PdfReader

        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(url, timeout=30)
            response.raise_for_status()
            pdf_bytes = response.content

        # Read PDF
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text_parts = []

        for page in reader.pages:
            text_parts.append(page.extract_text() or '')

        text = '\n\n'.join(text_parts)
        words = text.split()
        word_count = len(words)

        # Truncate if needed
        if word_count > MAX_CONTENT_WORDS:
            words = words[:MAX_CONTENT_WORDS]
            text = ' '.join(words) + '\n\n[Content truncated]'
            word_count = MAX_CONTENT_WORDS

        # Extract title from metadata or filename
        title = reader.metadata.get('/Title', '') if reader.metadata else ''
        if not title:
            title = url.split('/')[-1].replace('.pdf', '').replace('_', ' ')

        return ExtractedContent(
            title=title,
            text=text,
            source=url,
            site_name='PDF',
            word_count=word_count,
        )

    except ImportError:
        logger.warning("pypdf not available, storing PDF URL only")
        return ExtractedContent(
            title=url.split('/')[-1],
            text=f"PDF document: {url}\n\n[PDF text extraction not available]",
            source=url,
            site_name='PDF',
            word_count=5,
        )
    except Exception as e:
        logger.error(f"Failed to extract PDF from {url}: {e}")
        return ExtractedContent(
            title=url.split('/')[-1],
            text=f"PDF document: {url}\n\nError extracting: {str(e)}",
            source=url,
            site_name='PDF',
            word_count=5,
        )


def _html_to_text(html: str) -> str:
    """Convert HTML to plain text."""
    import re

    # Remove script and style elements
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)

    # Convert br and p tags to newlines
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</div>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</li>', '\n', text, flags=re.IGNORECASE)

    # Remove all other HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Decode HTML entities
    import html
    text = html.unescape(text)

    # Normalize whitespace
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = re.sub(r' +', ' ', text)

    return text.strip()
