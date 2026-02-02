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
    ItemStatus,
    ExtractedContent,
    SearchResult,
    PassiveCaptureMatch,
    DigestData,
)
from .config import (
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    SIMILARITY_THRESHOLD,
    DECAY_HALF_LIFE_DAYS,
    PRIORITY_EXPLICIT,
    PRIORITY_PASSIVE,
    PRIORITY_SEED,
    EMBEDDING_DIMENSIONS,
)

# Main pipeline functions
from .pipeline import (
    process_capture,
    process_passive_capture,
    reprocess_pending_items,
)

# Content extraction
from .extract import extract_content, extract_from_url

# Chunking
from .chunk import chunk_text, chunk_for_embedding

# Embedding
from .embed import generate_embedding, generate_embeddings_batch

# Database operations
from .db import (
    semantic_search,
    get_knowledge_item,
    create_knowledge_item,
    boost_access,
    get_recent_items,
    get_topics_with_counts,
    get_total_active_count,
    get_total_connection_count,
)

# Decay model
from .decay import (
    calculate_decay_score,
    is_fading,
)

# Commands
from .commands import (
    handle_save,
    handle_recall,
    handle_knowledge,
)

# Passive capture
from .passive import (
    should_capture_message,
    process_passive_message,
    detect_passive_captures,
)

# Connection discovery
from .connections import (
    discover_connections_for_item,
    batch_discover_connections,
    surface_new_connections,
    format_connection_for_discord,
)

# Contextual surfacing
from .surfacing import (
    get_context_for_message,
    get_relevant_context,
    format_context_for_claude,
)

__all__ = [
    # Types
    "KnowledgeItem",
    "KnowledgeChunk",
    "KnowledgeConnection",
    "CaptureType",
    "ContentType",
    "ConnectionType",
    "ItemStatus",
    "ExtractedContent",
    "SearchResult",
    "PassiveCaptureMatch",
    "DigestData",
    # Config
    "CHUNK_SIZE",
    "CHUNK_OVERLAP",
    "SIMILARITY_THRESHOLD",
    "DECAY_HALF_LIFE_DAYS",
    "PRIORITY_EXPLICIT",
    "PRIORITY_PASSIVE",
    "PRIORITY_SEED",
    "EMBEDDING_DIMENSIONS",
    # Pipeline
    "process_capture",
    "process_passive_capture",
    "reprocess_pending_items",
    # Extraction
    "extract_content",
    "extract_from_url",
    # Chunking
    "chunk_text",
    "chunk_for_embedding",
    # Embedding
    "generate_embedding",
    "generate_embeddings_batch",
    # Database
    "semantic_search",
    "get_knowledge_item",
    "create_knowledge_item",
    "boost_access",
    "get_recent_items",
    "get_topics_with_counts",
    "get_total_active_count",
    "get_total_connection_count",
    # Decay
    "calculate_decay_score",
    "is_fading",
    # Commands
    "handle_save",
    "handle_recall",
    "handle_knowledge",
]
