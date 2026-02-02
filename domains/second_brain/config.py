"""Configuration constants for Second Brain."""

import os
from typing import Final

# Chunking configuration
CHUNK_SIZE: Final[int] = 300           # ~300 words per chunk
CHUNK_OVERLAP: Final[int] = 50         # 50-word overlap between chunks
MAX_CHUNKS_PER_ITEM: Final[int] = 40   # Max chunks (covers ~12,000 words)
MIN_CONTENT_WORDS: Final[int] = 10     # Reject trivially short content
MAX_CONTENT_WORDS: Final[int] = 10_000 # Truncate with note

# Embedding configuration
# Using Supabase's built-in gte-small model (via pg_embedding extension)
# Zero API cost, no external key needed
EMBEDDING_MODEL: Final[str] = "gte-small"
EMBEDDING_DIMENSIONS: Final[int] = 384  # gte-small produces 384-dim vectors

# Similarity thresholds
SIMILARITY_THRESHOLD: Final[float] = 0.75      # Min for contextual surfacing
CONNECTION_THRESHOLD: Final[float] = 0.80       # Min for connection discovery
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

# API Keys (from environment)
def get_claude_api_key() -> str | None:
    """Get Claude API key from environment (for summarisation/tagging)."""
    return os.getenv("DISCORD_BOT_CLAUDE_KEY")
