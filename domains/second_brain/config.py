"""Configuration constants for Second Brain."""

import os
from typing import Final

# Hadley API base URL (used by seed adapters for Calendar, Gmail)
HADLEY_API_BASE: Final[str] = os.getenv("HADLEY_API_BASE", "http://172.19.64.1:8100")

# Chunking configuration
CHUNK_SIZE: Final[int] = 300           # ~300 words per chunk
CHUNK_OVERLAP: Final[int] = 50         # 50-word overlap between chunks
MAX_CHUNKS_PER_ITEM: Final[int] = 40   # Max chunks (covers ~12,000 words)
MIN_CONTENT_WORDS: Final[int] = 10     # Reject trivially short content
MAX_CONTENT_WORDS: Final[int] = 10_000 # Truncate with note

# Embedding configuration
EMBEDDING_MODEL: Final[str] = "gte-small"
EMBEDDING_DIMENSIONS: Final[int] = 384  # gte-small produces 384-dim vectors
EMBEDDING_TEXT_LIMIT: Final[int] = 8000  # Max chars before truncation
EMBEDDING_SINGLE_TIMEOUT: Final[int] = 60  # Seconds for single embedding request
EMBEDDING_BATCH_TIMEOUT: Final[int] = 120  # Seconds for batch embedding request
EMBEDDING_MAX_RETRIES: Final[int] = 3  # Max retry attempts
EMBEDDING_RETRY_BASE_DELAY: Final[float] = 2.0  # Base delay (seconds) for exponential backoff
EMBEDDING_MAX_CONCURRENT: Final[int] = 5  # Max concurrent requests in sequential fallback

# Similarity thresholds
SIMILARITY_THRESHOLD: Final[float] = 0.75      # Min for contextual surfacing
CONNECTION_THRESHOLD: Final[float] = 0.72       # Min for connection discovery (lowered from 0.80)
SEARCH_MIN_DECAY: Final[float] = 0.2           # Skip heavily decayed items

# Decay model
DECAY_HALF_LIFE_DAYS: Final[int] = 90          # Decay halves every 90 days
ACCESS_BOOST_FACTOR: Final[float] = 0.2        # log2(access_count+1) multiplier

# Priority levels
PRIORITY_EXPLICIT: Final[float] = 1.0          # User !save command
PRIORITY_SEED: Final[float] = 0.8              # Bulk import
PRIORITY_PASSIVE: Final[float] = 0.3           # Auto-detected

# Search limits
MAX_SEARCH_RESULTS: Final[int] = 10
MAX_CHUNKS_PER_SEARCH: Final[int] = 20
MAX_CONTEXT_ITEMS: Final[int] = 3              # Max items injected per response

# Passive capture signals
IDEA_SIGNAL_PHRASES: Final[list[str]] = [
    "what if",
    "i think we should",
    "idea:",
    "thought:",
    "we could",
    "maybe we should",
    "note to self",
    "don't forget",
    "reminder:",
    "remember to",
]

# Exclude patterns (questions/commands to Peter)
EXCLUDE_PATTERNS: Final[list[str]] = [
    "what is",
    "what are",
    "what's",
    "can you",
    "could you",
    "how do i",
    "how does",
    "why is",
    "why does",
    "where is",
    "when is",
    "who is",
    "tell me",
    "show me",
    "help me",
    "?",  # Questions
]

# Known domain tags for tagging prompt
KNOWN_DOMAIN_TAGS: Final[list[str]] = [
    # Business
    "hadley-bricks", "ebay", "bricklink", "brick-owl", "amazon",
    # LEGO
    "lego", "lego-investing", "retired-sets", "minifigures",
    # Running/Fitness
    "running", "marathon", "training", "nutrition", "garmin",
    # Family
    "family", "max", "emmie", "abby", "japan-trip",
    # Tech
    "tech", "development", "peterbot", "familyfuel",
    # Finance
    "finance", "tax", "self-employment",
]

# Source systems for seed imports
SOURCE_DISCORD: Final[str] = "discord"
SOURCE_GITHUB: Final[str] = "seed:github"
SOURCE_CLAUDE: Final[str] = "seed:claude"
SOURCE_GEMINI: Final[str] = "seed:gemini"
SOURCE_GDRIVE: Final[str] = "seed:gdrive"
SOURCE_GCAL: Final[str] = "seed:gcal"
SOURCE_EMAIL: Final[str] = "seed:email"
SOURCE_BOOKMARKS: Final[str] = "seed:bookmarks"
SOURCE_GARMIN: Final[str] = "seed:garmin"
SOURCE_INSTAGRAM: Final[str] = "seed:instagram"

# Structured extraction limits
STRUCTURED_EXTRACTION_TIMEOUT: Final[int] = 30  # seconds
MAX_FACTS_PER_ITEM: Final[int] = 8
MAX_CONCEPTS_PER_ITEM: Final[int] = 5

# Claude API configuration
CLAUDE_API_URL: Final[str] = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL: Final[str] = "claude-3-5-haiku-latest"
CLAUDE_API_VERSION: Final[str] = "2023-06-01"


# API Keys (from environment)
def get_claude_api_key() -> str | None:
    """Get Claude API key from environment (for summarisation/tagging)."""
    return os.getenv("DISCORD_BOT_CLAUDE_KEY")


async def call_claude(prompt: str, max_tokens: int = 200, timeout: int = 30) -> str | None:
    """Shared Claude API call used by summarise, tag, and extract_structured.

    Returns the text response, or None on failure.
    """
    import httpx

    api_key = get_claude_api_key()
    if not api_key:
        return None

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                CLAUDE_API_URL,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": CLAUDE_API_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": CLAUDE_MODEL,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json()["content"][0]["text"].strip()
    except Exception as e:
        from logger import logger
        logger.warning(f"Claude API call failed: {e}")
        return None
