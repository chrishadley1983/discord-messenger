"""Processing pipeline for Second Brain.

Orchestrates the full capture workflow:
1. Extract content from URL/text
2. Generate summary
3. Extract topic tags
4. Chunk content
5. Generate embeddings
6. Store in database
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from logger import logger
from .types import CaptureType, ContentType, ExtractedContent, ItemStatus, KnowledgeItem
from .config import PRIORITY_EXPLICIT, PRIORITY_SEED, PRIORITY_PASSIVE
from .extract import extract_content
from .summarise import generate_summary, extract_title
from .tag import extract_topics
from .extract_structured import extract_structured
from .chunk import chunk_text, chunk_for_embedding
from .embed import generate_embedding, generate_embeddings_batch, EmbeddingError
from .db import (
    boost_access,
    create_knowledge_item,
    create_knowledge_chunks,
    get_item_by_source,
)


async def process_capture(
    source: str,
    capture_type: CaptureType = CaptureType.EXPLICIT,
    user_note: str | None = None,
    user_tags: list[str] | None = None,
    content_type_override: ContentType | None = None,
    source_message_id: str | None = None,
    source_system: str | None = None,
    text: str | None = None,
    title_override: str | None = None,
    facts_override: list | None = None,
    concepts_override: list | None = None,
    created_at_override: datetime | None = None,
) -> KnowledgeItem | None:
    """Process a new knowledge capture through the full pipeline.

    Args:
        source: URL or plain text content (also used as source identifier)
        capture_type: How content was captured (explicit/passive/seed)
        user_note: Optional user annotation
        user_tags: Optional user-provided tags (merged with extracted)
        content_type_override: Force a specific content type (e.g. CONVERSATION_EXTRACT)
        source_message_id: Discord message ID for conversation captures
        source_system: Source system identifier (e.g. 'discord')
        text: Pre-extracted text content (skips extraction step if provided)
        title_override: Force a specific title (skips title generation)
        facts_override: Pre-extracted facts (skips structured extraction)
        concepts_override: Pre-extracted concepts (skips structured extraction)
        created_at_override: Override creation timestamp (for migrations)

    Returns:
        Created KnowledgeItem or None if failed
    """
    logger.info(f"Processing {capture_type.value} capture: {source[:100]}...")

    # Check for duplicates — boost access if re-saved
    # Match any URL scheme (http, https, gcal, gmail, etc.) by checking
    # for :// near the start — avoids false positives on plain-text content.
    if '://' in source[:30]:
        existing = await get_item_by_source(source)
        if existing:
            logger.info(f"Duplicate source found, boosting access: {source}")
            await boost_access(existing.id)
            return existing

    # Step 1: Extract content (or use pre-provided text)
    if text:
        extracted = ExtractedContent(
            title=title_override or "",
            text=text,
            source=source,
            excerpt=text[:200],
            site_name="",
            word_count=len(text.split()),
        )
        logger.debug(f"Using pre-provided text ({extracted.word_count} words)")
    else:
        try:
            extracted = await extract_content(source)
            logger.debug(f"Extracted: {extracted.title} ({extracted.word_count} words)")
        except Exception as e:
            logger.error(f"Extraction failed for {source}: {e}")
            return None

    # Validate extraction
    if extracted.word_count < 5:
        logger.warning(f"Content too short ({extracted.word_count} words), skipping")
        return None

    # Step 2: Generate or use title
    title = title_override or extracted.title
    if not title or len(title) < 5:
        try:
            title = await extract_title(extracted.text)
        except Exception as e:
            logger.warning(f"Title extraction failed: {e}")
            title = source[:100] if source.startswith('http') else source.split('\n')[0][:100]

    # Determine content type (needed before concurrent calls)
    content_type = content_type_override or _detect_content_type(extracted.source, extracted.text)

    # Steps 3-4b: Run summary, topics, and structured extraction concurrently (PR-003)
    # Run structured extraction for all content types except media logs
    needs_structured = (
        not facts_override and not concepts_override
        and content_type not in {ContentType.LISTENING_HISTORY, ContentType.VIEWING_HISTORY}
    )

    async def _safe_summary():
        try:
            return await generate_summary(extracted.text, title)
        except Exception as e:
            logger.warning(f"Summary generation failed: {e}")
            return extracted.excerpt or extracted.text[:200]

    async def _safe_topics():
        try:
            return await extract_topics(extracted.text, title, content_type=content_type.value)
        except Exception as e:
            logger.warning(f"Topic extraction failed: {e}")
            return ['untagged']

    async def _safe_structured():
        if not needs_structured:
            return {}
        try:
            return await extract_structured(extracted.text, title, content_type=content_type.value)
        except Exception as e:
            logger.warning(f"Structured extraction failed: {e}")
            return {}

    summary, topics, structured = await asyncio.gather(
        _safe_summary(), _safe_topics(), _safe_structured()
    )

    # Merge user tags if provided
    if user_tags:
        topics = list(set(topics + user_tags))[:8]

    # Unpack structured extraction results
    facts = facts_override or structured.get("facts", [])
    concepts = concepts_override or structured.get("concepts", [])
    if facts or concepts:
        logger.debug(f"Extracted {len(facts)} facts, {len(concepts)} concepts")

    # Step 5: Chunk content
    chunks = chunk_text(extracted.text)
    logger.debug(f"Created {len(chunks)} chunks")

    # Step 6: Generate embeddings for chunks
    chunk_texts = chunk_for_embedding(extracted.text, title)
    try:
        embeddings = await generate_embeddings_batch(chunk_texts)
    except EmbeddingError as e:
        logger.error(
            f"Embedding generation failed for {len(chunk_texts)} chunks "
            f"(title: {title[:60]}): {e}"
        )
        # Store item without embeddings — will be picked up by reprocess_pending_items
        embeddings = None

    # Determine priority based on capture type
    priority = {
        CaptureType.EXPLICIT: PRIORITY_EXPLICIT,
        CaptureType.SEED: PRIORITY_SEED,
        CaptureType.PASSIVE: PRIORITY_PASSIVE,
    }.get(capture_type, PRIORITY_PASSIVE)

    # Step 7: Store in database
    now = created_at_override or datetime.now(timezone.utc)

    item = KnowledgeItem(
        id='',  # Will be assigned by database
        title=title,
        source=extracted.source,
        content_type=content_type,
        capture_type=capture_type,
        status=ItemStatus.ACTIVE,
        summary=summary,
        full_text=extracted.text,
        topics=topics,
        priority=priority,
        decay_score=1.0,  # Fresh content starts at 1.0
        access_count=1,
        last_accessed=now,
        created_at=now,
        updated_at=now,
        user_note=user_note,
        site_name=extracted.site_name,
        word_count=extracted.word_count,
        source_message_id=source_message_id,
        source_system=source_system,
        facts=facts,
        concepts=concepts,
    )

    try:
        created_item = await create_knowledge_item(item)
        if not created_item:
            logger.error("Failed to create knowledge item in database")
            return None

        logger.info(f"Created knowledge item: {created_item.id}")

        # Store chunks with embeddings (skip if embedding generation failed)
        if embeddings is not None:
            chunk_data = []
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                chunk_data.append({
                    'index': i,
                    'text': chunk.text,
                    'embedding': embedding,
                    'start_word': chunk.start_word,
                    'end_word': chunk.end_word,
                })

            await create_knowledge_chunks(created_item.id, chunk_data)
            logger.info(f"Created {len(chunk_data)} chunks for item {created_item.id}")
        else:
            logger.warning(
                f"Skipping chunk storage for {created_item.id} — embeddings failed. "
                f"Item saved as pending for reprocessing."
            )
            from .db import update_item_status
            await update_item_status(created_item.id, ItemStatus.PENDING)

        # Step 8: Discover connections for all capture types
        try:
            from .connections import discover_connections_for_item
            connections = await discover_connections_for_item(created_item)
            if connections:
                logger.info(f"Discovered {len(connections)} connections for {created_item.id}")
        except Exception as e:
            logger.warning(f"Connection discovery failed: {e}")
            # Non-fatal - item is still saved

        return created_item

    except Exception as e:
        logger.error(f"Database storage failed: {e}")
        return None


async def process_passive_capture(
    source: str,
    context: str | None = None,
) -> KnowledgeItem | None:
    """Lightweight passive capture - minimal processing.

    Passive captures:
    - Don't generate embeddings immediately
    - Lower priority (0.3)
    - Processed in background/batch later

    Args:
        source: URL or text
        context: Optional context about why this was captured

    Returns:
        Created KnowledgeItem or None
    """
    logger.info(f"Passive capture: {source[:100]}...")

    # Check for duplicates
    if '://' in source[:30]:
        existing = await get_item_by_source(source)
        if existing:
            logger.debug(f"Duplicate passive capture, skipping: {source}")
            return existing

    # Extract content
    try:
        extracted = await extract_content(source)
    except Exception as e:
        logger.warning(f"Passive extraction failed: {e}")
        return None

    if extracted.word_count < 10:
        logger.debug("Passive content too short, skipping")
        return None

    # Use extracted title or generate simple one
    title = extracted.title or source[:100]

    # Quick topic extraction (fallback only, no API call for passive)
    from .tag import _fallback_topics
    topics = _fallback_topics(extracted.text, title)

    # Detect content type
    content_type = _detect_content_type(extracted.source, extracted.text)

    now = datetime.now(timezone.utc)

    item = KnowledgeItem(
        id='',
        title=title,
        source=extracted.source,
        content_type=content_type,
        capture_type=CaptureType.PASSIVE,
        status=ItemStatus.PENDING,  # Needs full processing later
        summary=extracted.excerpt or extracted.text[:200],
        full_text=extracted.text,
        topics=topics,
        priority=PRIORITY_PASSIVE,
        decay_score=1.0,
        access_count=0,
        last_accessed=now,
        created_at=now,
        updated_at=now,
        user_note=context,
        site_name=extracted.site_name,
        word_count=extracted.word_count,
    )

    try:
        created_item = await create_knowledge_item(item)
        if created_item:
            logger.info(f"Created passive item: {created_item.id}")
        return created_item
    except Exception as e:
        logger.error(f"Passive capture storage failed: {e}")
        return None


def _detect_content_type(source: str, text: str) -> ContentType:
    """Detect the type of content based on source and text."""
    source_lower = source.lower()

    # URL-based detection
    if 'youtube.com' in source_lower or 'youtu.be' in source_lower:
        return ContentType.VIDEO
    if 'reddit.com' in source_lower:
        return ContentType.DISCUSSION
    if source_lower.endswith('.pdf'):
        return ContentType.PDF
    if 'github.com' in source_lower:
        return ContentType.CODE
    if 'twitter.com' in source_lower or 'x.com' in source_lower:
        return ContentType.SOCIAL

    # Text-based detection
    text_lower = text.lower()
    if any(w in text_lower for w in ['recipe', 'ingredients', 'cook', 'bake']):
        return ContentType.RECIPE
    if any(w in text_lower for w in ['workout', 'exercise', 'training plan', 'marathon']):
        return ContentType.FITNESS

    # Default to article for URLs, note for direct input
    if source.startswith(('http://', 'https://')):
        return ContentType.ARTICLE
    return ContentType.NOTE


async def reprocess_pending_items(limit: int = 10) -> int:
    """Process pending items that need full pipeline.

    Called periodically to upgrade passive captures.

    Returns:
        Number of items processed
    """
    from .db import get_pending_items, update_item_status

    pending = await get_pending_items(limit)
    processed = 0

    for item in pending:
        logger.info(f"Reprocessing pending item: {item.id}")

        try:
            # Generate summary if missing/placeholder
            if not item.summary or len(item.summary) < 50:
                item.summary = await generate_summary(item.full_text, item.title)

            # Generate proper topics
            item.topics = await extract_topics(item.full_text, item.title)

            # Chunk and embed
            chunks = chunk_text(item.full_text)
            chunk_texts = chunk_for_embedding(item.full_text, item.title)
            embeddings = await generate_embeddings_batch(chunk_texts)

            # Store chunks
            chunk_data = []
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                chunk_data.append({
                    'index': i,
                    'text': chunk.text,
                    'embedding': embedding,
                    'start_word': chunk.start_word,
                    'end_word': chunk.end_word,
                })

            await create_knowledge_chunks(item.id, chunk_data)

            # Update status to active
            await update_item_status(item.id, ItemStatus.ACTIVE)
            processed += 1

        except Exception as e:
            logger.error(f"Failed to reprocess item {item.id}: {e}")
            continue

    logger.info(f"Reprocessed {processed}/{len(pending)} pending items")
    return processed


# =============================================================================
# BATCH PIPELINE SUPPORT
# =============================================================================

from dataclasses import dataclass, field
from .chunk import TextChunk


@dataclass
class PreparedItem:
    """An item that has been through extract/summarize/tag/chunk but NOT embedded."""
    item: KnowledgeItem
    chunks: list[TextChunk]
    chunk_texts_for_embedding: list[str]


async def prepare_capture(
    source: str,
    capture_type: CaptureType = CaptureType.SEED,
    user_tags: list[str] | None = None,
    content_type_override: ContentType | None = None,
    source_system: str | None = None,
    text: str | None = None,
    title_override: str | None = None,
    facts_override: list | None = None,
    concepts_override: list | None = None,
    created_at_override: datetime | None = None,
) -> PreparedItem | None:
    """Run the pipeline up to (but not including) embedding.

    Returns a PreparedItem with chunk texts ready for batch embedding,
    or None if the item should be skipped (duplicate, too short, etc.).
    """
    # Duplicate check
    if '://' in source[:30]:
        existing = await get_item_by_source(source)
        if existing:
            await boost_access(existing.id)
            return None

    # Extract content
    if text:
        extracted = ExtractedContent(
            title=title_override or "",
            text=text,
            source=source,
            excerpt=text[:200],
            site_name="",
            word_count=len(text.split()),
        )
    else:
        try:
            extracted = await extract_content(source)
        except Exception as e:
            logger.error(f"Extraction failed for {source}: {e}")
            return None

    if extracted.word_count < 5:
        return None

    # Title
    title = title_override or extracted.title
    if not title or len(title) < 5:
        try:
            title = await extract_title(extracted.text)
        except Exception:
            title = source[:100]

    content_type = content_type_override or _detect_content_type(extracted.source, extracted.text)

    # Concurrent: summary, topics, structured
    needs_structured = (
        not facts_override and not concepts_override
        and content_type not in {ContentType.LISTENING_HISTORY, ContentType.VIEWING_HISTORY}
    )

    async def _safe_summary():
        try:
            return await generate_summary(extracted.text, title)
        except Exception:
            return extracted.excerpt or extracted.text[:200]

    async def _safe_topics():
        try:
            return await extract_topics(extracted.text, title, content_type=content_type.value)
        except Exception:
            return ['untagged']

    async def _safe_structured():
        if not needs_structured:
            return {}
        try:
            return await extract_structured(extracted.text, title, content_type=content_type.value)
        except Exception:
            return {}

    summary, topics, structured = await asyncio.gather(
        _safe_summary(), _safe_topics(), _safe_structured()
    )

    if user_tags:
        topics = list(set(topics + user_tags))[:8]

    facts = facts_override or structured.get("facts", [])
    concepts = concepts_override or structured.get("concepts", [])

    # Chunk
    chunks = chunk_text(extracted.text)
    chunk_texts = chunk_for_embedding(extracted.text, title)

    # Build item
    priority = {
        CaptureType.EXPLICIT: PRIORITY_EXPLICIT,
        CaptureType.SEED: PRIORITY_SEED,
        CaptureType.PASSIVE: PRIORITY_PASSIVE,
    }.get(capture_type, PRIORITY_PASSIVE)

    now = created_at_override or datetime.now(timezone.utc)

    item = KnowledgeItem(
        id='',
        title=title,
        source=extracted.source,
        content_type=content_type,
        capture_type=capture_type,
        status=ItemStatus.ACTIVE,
        summary=summary,
        full_text=extracted.text,
        topics=topics,
        priority=priority,
        decay_score=1.0,
        access_count=1,
        last_accessed=now,
        created_at=now,
        updated_at=now,
        site_name=extracted.site_name,
        word_count=extracted.word_count,
        source_system=source_system,
        facts=facts,
        concepts=concepts,
    )

    return PreparedItem(
        item=item,
        chunks=chunks,
        chunk_texts_for_embedding=chunk_texts,
    )
