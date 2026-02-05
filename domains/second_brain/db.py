"""Database operations for Second Brain using Supabase.

Uses Supabase's built-in gte-small embedding model via pg_embedding extension.
"""

import json
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

import httpx

from config import SUPABASE_URL, SUPABASE_KEY
from logger import logger
from .config import (
    EMBEDDING_DIMENSIONS,
    MAX_SEARCH_RESULTS,
    MAX_CHUNKS_PER_SEARCH,
    SEARCH_MIN_DECAY,
    CONNECTION_THRESHOLD,
)
from .types import (
    KnowledgeItem,
    KnowledgeChunk,
    KnowledgeConnection,
    CaptureType,
    ContentType,
    ConnectionType,
    ItemStatus,
    SearchResult,
)


def _get_headers() -> dict[str, str]:
    """Get headers for Supabase API calls."""
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _get_rest_url() -> str:
    """Get the REST API URL."""
    return f"{SUPABASE_URL}/rest/v1"


# =============================================================================
# EMBEDDING GENERATION
# =============================================================================
# Embeddings are handled by the embed module which has multiple fallbacks:
# 1. Supabase Edge Function
# 2. Supabase RPC
# 3. HuggingFace Inference API (free)
# 4. Zero vector (last resort)

from .embed import generate_embedding, generate_embeddings_batch


# =============================================================================
# KNOWLEDGE ITEMS CRUD
# =============================================================================

async def insert_knowledge_item(
    content_type: ContentType,
    capture_type: CaptureType,
    title: Optional[str] = None,
    source_url: Optional[str] = None,
    source_message_id: Optional[str] = None,
    source_system: Optional[str] = None,
    full_text: Optional[str] = None,
    summary: Optional[str] = None,
    topics: Optional[list[str]] = None,
    base_priority: float = 1.0,
) -> KnowledgeItem:
    """Insert a new knowledge item."""
    payload = {
        "content_type": content_type.value,
        "capture_type": capture_type.value,
        "title": title,
        "source_url": source_url,
        "source_message_id": source_message_id,
        "source_system": source_system,
        "full_text": full_text,
        "summary": summary,
        "topics": topics or [],
        "base_priority": base_priority,
        "decay_score": base_priority,  # Start at base priority
        "status": "active",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{_get_rest_url()}/knowledge_items",
                headers=_get_headers(),
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

        logger.info(f"Inserted knowledge item: {title or 'untitled'}")
        return KnowledgeItem.from_db_row(data[0])
    except Exception as e:
        logger.error(f"Failed to insert knowledge item: {e}")
        raise


async def get_knowledge_item(item_id: UUID) -> Optional[KnowledgeItem]:
    """Get a knowledge item by ID."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{_get_rest_url()}/knowledge_items?id=eq.{item_id}",
                headers=_get_headers(),
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

        if not data:
            return None
        return KnowledgeItem.from_db_row(data[0])
    except Exception as e:
        logger.error(f"Failed to get knowledge item {item_id}: {e}")
        raise


async def update_knowledge_item(
    item_id: UUID,
    **updates,
) -> KnowledgeItem:
    """Update a knowledge item."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{_get_rest_url()}/knowledge_items?id=eq.{item_id}",
                headers=_get_headers(),
                json=updates,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

        logger.info(f"Updated knowledge item: {item_id}")
        return KnowledgeItem.from_db_row(data[0])
    except Exception as e:
        logger.error(f"Failed to update knowledge item {item_id}: {e}")
        raise


async def archive_knowledge_item(item_id: UUID) -> None:
    """Archive a knowledge item (soft delete)."""
    await update_knowledge_item(item_id, status="archived")
    logger.info(f"Archived knowledge item: {item_id}")


async def promote_passive_item(item_id: UUID) -> KnowledgeItem:
    """Promote a passive capture to explicit save."""
    return await update_knowledge_item(
        item_id,
        capture_type="explicit",
        base_priority=1.0,
        promoted_at=datetime.utcnow().isoformat(),
    )


async def boost_access(item_id: UUID) -> None:
    """Boost an item when accessed (update last_accessed_at and access_count)."""
    try:
        # First get current access count
        item = await get_knowledge_item(item_id)
        if not item:
            return

        new_count = item.access_count + 1

        # Calculate new decay score with access boost
        from .decay import calculate_decay_score
        new_decay = calculate_decay_score(
            created_at=item.created_at,
            last_accessed_at=datetime.utcnow(),
            access_count=new_count,
            base_priority=item.base_priority,
        )

        await update_knowledge_item(
            item_id,
            last_accessed_at=datetime.utcnow().isoformat(),
            access_count=new_count,
            decay_score=new_decay,
        )
    except Exception as e:
        logger.warning(f"Failed to boost access for {item_id}: {e}")


# =============================================================================
# KNOWLEDGE CHUNKS CRUD
# =============================================================================

async def insert_chunk(
    parent_id: UUID,
    chunk_index: int,
    content: str,
    embedding: list[float],
) -> KnowledgeChunk:
    """Insert a chunk with embedding."""
    payload = {
        "parent_id": str(parent_id),
        "chunk_index": chunk_index,
        "content": content,
        "embedding": embedding,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{_get_rest_url()}/knowledge_chunks",
                headers=_get_headers(),
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

        return KnowledgeChunk.from_db_row(data[0])
    except Exception as e:
        logger.error(f"Failed to insert chunk: {e}")
        raise


async def insert_chunks_batch(
    parent_id: UUID,
    chunks: list[tuple[int, str, list[float]]],  # (index, content, embedding)
) -> list[KnowledgeChunk]:
    """Insert multiple chunks in one request."""
    payloads = [
        {
            "parent_id": str(parent_id),
            "chunk_index": idx,
            "content": content,
            "embedding": embedding,
        }
        for idx, content, embedding in chunks
    ]

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{_get_rest_url()}/knowledge_chunks",
                headers=_get_headers(),
                json=payloads,
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

        logger.info(f"Inserted {len(data)} chunks for item {parent_id}")
        return [KnowledgeChunk.from_db_row(row) for row in data]
    except Exception as e:
        logger.error(f"Failed to insert chunks batch: {e}")
        raise


async def get_chunks_for_item(parent_id: UUID) -> list[KnowledgeChunk]:
    """Get all chunks for a knowledge item."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{_get_rest_url()}/knowledge_chunks?parent_id=eq.{parent_id}&order=chunk_index",
                headers=_get_headers(),
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

        return [KnowledgeChunk.from_db_row(row) for row in data]
    except Exception as e:
        logger.error(f"Failed to get chunks for {parent_id}: {e}")
        raise


# =============================================================================
# SEMANTIC SEARCH
# =============================================================================

async def semantic_search(
    query: str,
    min_similarity: float = 0.75,
    min_decay_score: float = SEARCH_MIN_DECAY,
    capture_types: Optional[list[CaptureType]] = None,
    exclude_parent_id: Optional[UUID] = None,
    limit: int = MAX_SEARCH_RESULTS,
) -> list[SearchResult]:
    """Perform semantic search against knowledge chunks.

    Returns SearchResult objects grouped by parent item.
    """
    # Generate query embedding
    query_embedding = await generate_embedding(query)

    # Build the RPC call for semantic search
    # This uses a custom Supabase function for cosine similarity search
    params = {
        "query_embedding": query_embedding,
        "match_threshold": min_similarity,
        "match_count": MAX_CHUNKS_PER_SEARCH,
        "min_decay": min_decay_score,
    }

    if capture_types:
        params["capture_types"] = [ct.value for ct in capture_types]
    if exclude_parent_id:
        params["exclude_parent"] = str(exclude_parent_id)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{_get_rest_url()}/rpc/search_knowledge",
                headers=_get_headers(),
                json=params,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

        # Group results by parent item
        results_by_parent: dict[UUID, SearchResult] = {}

        for row in data:
            parent_id = UUID(row["parent_id"])

            if parent_id not in results_by_parent:
                # Create the parent item
                item = KnowledgeItem.from_db_row({
                    "id": row["parent_id"],
                    "content_type": row["content_type"],
                    "capture_type": row["capture_type"],
                    "title": row.get("title"),
                    "source_url": row.get("source_url"),
                    "source_message_id": row.get("source_message_id"),
                    "source_system": row.get("source_system"),
                    "full_text": row.get("full_text"),
                    "summary": row.get("summary"),
                    "topics": row.get("topics", []),
                    "base_priority": row.get("base_priority", 1.0),
                    "last_accessed_at": row.get("last_accessed_at"),
                    "access_count": row.get("access_count", 0),
                    "decay_score": row.get("decay_score", 1.0),
                    "created_at": row["created_at"],
                    "promoted_at": row.get("promoted_at"),
                    "status": row.get("status", "active"),
                })
                results_by_parent[parent_id] = SearchResult(
                    item=item,
                    chunks=[],
                    best_similarity=0.0,
                    relevant_excerpts=[],
                )

            result = results_by_parent[parent_id]
            similarity = float(row.get("similarity", 0.0))  # Supabase returns string

            # Add chunk
            chunk = KnowledgeChunk.from_db_row({
                "id": row["chunk_id"],
                "parent_id": row["parent_id"],
                "chunk_index": row["chunk_index"],
                "content": row["chunk_content"],
                "embedding": None,  # Don't return embeddings
                "created_at": row["created_at"],
            })
            result.chunks.append(chunk)
            result.relevant_excerpts.append(row["chunk_content"][:200])

            if similarity > result.best_similarity:
                result.best_similarity = similarity

        # Sort by weighted score and limit
        sorted_results = sorted(
            results_by_parent.values(),
            key=lambda r: r.weighted_score,
            reverse=True,
        )[:limit]

        logger.info(f"Semantic search found {len(sorted_results)} items")
        return sorted_results

    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
        raise


# =============================================================================
# CONNECTIONS
# =============================================================================

async def insert_connection(
    item_a_id: UUID,
    item_b_id: UUID,
    connection_type: ConnectionType,
    description: Optional[str] = None,
    similarity_score: Optional[float] = None,
) -> KnowledgeConnection:
    """Insert a new connection between items."""
    payload = {
        "item_a_id": str(item_a_id),
        "item_b_id": str(item_b_id),
        "connection_type": connection_type.value,
        "description": description,
        "similarity_score": similarity_score,
        "surfaced": False,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{_get_rest_url()}/knowledge_connections",
                headers=_get_headers(),
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

        logger.info(f"Inserted connection: {item_a_id} <-> {item_b_id}")
        return KnowledgeConnection.from_db_row(data[0])
    except Exception as e:
        # Ignore duplicate key errors
        if "duplicate key" in str(e).lower():
            logger.debug(f"Connection already exists: {item_a_id} <-> {item_b_id}")
            return None
        logger.error(f"Failed to insert connection: {e}")
        raise


async def connection_exists(item_a_id: UUID, item_b_id: UUID) -> bool:
    """Check if a connection exists between two items (in either direction)."""
    try:
        async with httpx.AsyncClient() as client:
            # Check both directions
            filter_str = (
                f"or=(and(item_a_id.eq.{item_a_id},item_b_id.eq.{item_b_id}),"
                f"and(item_a_id.eq.{item_b_id},item_b_id.eq.{item_a_id}))"
            )
            response = await client.get(
                f"{_get_rest_url()}/knowledge_connections?{filter_str}&select=id",
                headers=_get_headers(),
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

        return len(data) > 0
    except Exception as e:
        logger.error(f"Failed to check connection existence: {e}")
        return False


async def get_connections_for_item(item_id: UUID) -> list[KnowledgeConnection]:
    """Get all connections involving an item."""
    try:
        async with httpx.AsyncClient() as client:
            filter_str = f"or=(item_a_id.eq.{item_id},item_b_id.eq.{item_id})"
            response = await client.get(
                f"{_get_rest_url()}/knowledge_connections?{filter_str}",
                headers=_get_headers(),
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

        return [KnowledgeConnection.from_db_row(row) for row in data]
    except Exception as e:
        logger.error(f"Failed to get connections for {item_id}: {e}")
        raise


async def get_unsurfaced_connections(since: Optional[datetime] = None) -> list[KnowledgeConnection]:
    """Get connections that haven't been shown to user yet."""
    try:
        async with httpx.AsyncClient() as client:
            url = f"{_get_rest_url()}/knowledge_connections?surfaced=eq.false&order=created_at.desc"
            if since:
                url += f"&created_at=gte.{since.isoformat()}"

            response = await client.get(url, headers=_get_headers(), timeout=30)
            response.raise_for_status()
            data = response.json()

        return [KnowledgeConnection.from_db_row(row) for row in data]
    except Exception as e:
        logger.error(f"Failed to get unsurfaced connections: {e}")
        raise


async def mark_connection_surfaced(connection_id: UUID) -> None:
    """Mark a connection as surfaced (shown to user)."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{_get_rest_url()}/knowledge_connections?id=eq.{connection_id}",
                headers=_get_headers(),
                json={
                    "surfaced": True,
                    "surfaced_at": datetime.utcnow().isoformat(),
                },
                timeout=30,
            )
            response.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to mark connection surfaced: {e}")


# =============================================================================
# STATS & QUERIES
# =============================================================================

async def get_total_active_count() -> int:
    """Get total count of active knowledge items."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{_get_rest_url()}/knowledge_items?status=eq.active&select=id",
                headers={**_get_headers(), "Prefer": "count=exact"},
                timeout=30,
            )
            response.raise_for_status()
            count = response.headers.get("content-range", "0-0/0").split("/")[-1]
            return int(count)
    except Exception as e:
        logger.error(f"Failed to get total count: {e}")
        return 0


async def get_total_connection_count() -> int:
    """Get total count of connections."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{_get_rest_url()}/knowledge_connections?select=id",
                headers={**_get_headers(), "Prefer": "count=exact"},
                timeout=30,
            )
            response.raise_for_status()
            count = response.headers.get("content-range", "0-0/0").split("/")[-1]
            return int(count)
    except Exception as e:
        logger.error(f"Failed to get connection count: {e}")
        return 0


async def get_items_since(since: datetime) -> list[KnowledgeItem]:
    """Get items created since a given datetime."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{_get_rest_url()}/knowledge_items?created_at=gte.{since.isoformat()}"
                f"&status=eq.active&order=created_at.desc",
                headers=_get_headers(),
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

        return [KnowledgeItem.from_db_row(row) for row in data]
    except Exception as e:
        logger.error(f"Failed to get items since {since}: {e}")
        raise


async def get_recent_items(limit: int = 10) -> list[KnowledgeItem]:
    """Get most recently created items."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{_get_rest_url()}/knowledge_items?status=eq.active&order=created_at.desc&limit={limit}",
                headers=_get_headers(),
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

        return [KnowledgeItem.from_db_row(row) for row in data]
    except Exception as e:
        logger.error(f"Failed to get recent items: {e}")
        raise


async def get_topics_with_counts() -> list[tuple[str, int]]:
    """Get all topics with their counts."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{_get_rest_url()}/rpc/get_topic_counts",
                headers=_get_headers(),
                json={},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

        return [(row["topic"], row["count"]) for row in data]
    except Exception as e:
        logger.error(f"Failed to get topic counts: {e}")
        return []


async def get_fading_but_relevant_items(limit: int = 5) -> list[KnowledgeItem]:
    """Get items with low decay but connected to active topics."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{_get_rest_url()}/rpc/get_fading_but_relevant",
                headers=_get_headers(),
                json={"item_limit": limit},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

        return [KnowledgeItem.from_db_row(row) for row in data]
    except Exception as e:
        logger.error(f"Failed to get fading items: {e}")
        return []


async def get_most_accessed_item_since(since: datetime) -> Optional[KnowledgeItem]:
    """Get the most accessed item since a given datetime."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{_get_rest_url()}/knowledge_items?"
                f"last_accessed_at=gte.{since.isoformat()}"
                f"&status=eq.active"
                f"&order=access_count.desc"
                f"&limit=1",
                headers=_get_headers(),
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

        if not data:
            return None
        return KnowledgeItem.from_db_row(data[0])
    except Exception as e:
        logger.error(f"Failed to get most accessed item: {e}")
        return None


# =============================================================================
# PIPELINE SUPPORT FUNCTIONS
# =============================================================================

async def create_knowledge_item(item: KnowledgeItem) -> Optional[KnowledgeItem]:
    """Create a knowledge item from a KnowledgeItem dataclass."""
    payload = {
        "content_type": item.content_type.value,
        "capture_type": item.capture_type.value,
        "title": item.title,
        "source_url": item.source if item.source.startswith('http') else None,
        "full_text": item.full_text,
        "summary": item.summary,
        "topics": item.topics or [],
        "base_priority": item.priority,
        "decay_score": item.decay_score,
        "status": item.status.value,
        "access_count": item.access_count,
    }

    # Add optional fields
    if item.user_note:
        payload["user_note"] = item.user_note
    if item.site_name:
        payload["site_name"] = item.site_name
    if item.word_count:
        payload["word_count"] = item.word_count

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{_get_rest_url()}/knowledge_items",
                headers=_get_headers(),
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

        logger.info(f"Created knowledge item: {item.title or 'untitled'}")
        return KnowledgeItem.from_db_row(data[0])
    except Exception as e:
        logger.error(f"Failed to create knowledge item: {e}")
        return None


async def create_knowledge_chunks(
    parent_id: str,
    chunks: list[dict],
) -> bool:
    """Create multiple chunks for a knowledge item.

    Args:
        parent_id: UUID of parent knowledge item
        chunks: List of dicts with: index, text, embedding, start_word, end_word
    """
    payloads = [
        {
            "parent_id": parent_id,
            "chunk_index": chunk["index"],
            "content": chunk["text"],
            "embedding": chunk["embedding"],
            "start_word": chunk.get("start_word"),
            "end_word": chunk.get("end_word"),
        }
        for chunk in chunks
    ]

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{_get_rest_url()}/knowledge_chunks",
                headers=_get_headers(),
                json=payloads,
                timeout=60,
            )
            response.raise_for_status()
        logger.info(f"Created {len(chunks)} chunks for item {parent_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to create chunks: {e}")
        return False


async def get_item_by_source(source_url: str) -> Optional[KnowledgeItem]:
    """Get a knowledge item by its source URL."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{_get_rest_url()}/knowledge_items?source_url=eq.{source_url}",
                headers=_get_headers(),
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

        if not data:
            return None
        return KnowledgeItem.from_db_row(data[0])
    except Exception as e:
        logger.error(f"Failed to get item by source {source_url}: {e}")
        return None


async def get_pending_items(limit: int = 10) -> list[KnowledgeItem]:
    """Get items with pending status that need full processing."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{_get_rest_url()}/knowledge_items?status=eq.pending&order=created_at&limit={limit}",
                headers=_get_headers(),
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

        return [KnowledgeItem.from_db_row(row) for row in data]
    except Exception as e:
        logger.error(f"Failed to get pending items: {e}")
        return []


async def update_item_status(item_id: str, status: ItemStatus) -> bool:
    """Update the status of a knowledge item."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{_get_rest_url()}/knowledge_items?id=eq.{item_id}",
                headers=_get_headers(),
                json={"status": status.value},
                timeout=30,
            )
            response.raise_for_status()
        logger.info(f"Updated item {item_id} status to {status.value}")
        return True
    except Exception as e:
        logger.error(f"Failed to update item status: {e}")
        return False
