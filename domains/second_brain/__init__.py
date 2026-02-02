"""Second Brain - Peter's external knowledge store.

Explicitly saved content and passively captured context,
retrievable via semantic search and surfaced proactively.

Storage: Supabase + pgvector
Input: Discord only
"""

from .types import (
    KnowledgeItem,
    KnowledgeChunk,
    KnowledgeConnection,
    CaptureType,
    ContentType,
    ConnectionType,
    ExtractedContent,
    SearchResult,
)
from .config import (
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    SIMILARITY_THRESHOLD,
    DECAY_HALF_LIFE_DAYS,
    PRIORITY_EXPLICIT,
    PRIORITY_PASSIVE,
    PRIORITY_SEED,
)

__all__ = [
    # Types
    "KnowledgeItem",
    "KnowledgeChunk",
    "KnowledgeConnection",
    "CaptureType",
    "ContentType",
    "ConnectionType",
    "ExtractedContent",
    "SearchResult",
    # Config
    "CHUNK_SIZE",
    "CHUNK_OVERLAP",
    "SIMILARITY_THRESHOLD",
    "DECAY_HALF_LIFE_DAYS",
    "PRIORITY_EXPLICIT",
    "PRIORITY_PASSIVE",
    "PRIORITY_SEED",
]
