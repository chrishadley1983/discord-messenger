"""Processing pipeline for Second Brain.

Orchestrates the full capture workflow:
1. Extract content from URL/text
2. Generate summary
3. Extract topic tags
4. Chunk content
5. Generate embeddings
6. Store in database
"""

from datetime import datetime, timezone
from typing import Optional

from logger import logger
from .types import CaptureType, ContentType, ItemStatus, KnowledgeItem
from .config import PRIORITY_EXPLICIT, PRIORITY_SEED, PRIORITY_PASSIVE
from .extract import extract_content
from .summarise import generate_summary, extract_title
from .tag import extract_topics
from .chunk import chunk_text, chunk_for_embedding
from .embed import generate_embedding, generate_embeddings_batch
from .db import (
    create_knowledge_item,
    create_knowledge_chunks,
    get_item_by_source,
)


async def process_capture(
    source: str,
    capture_type: CaptureType = CaptureType.EXPLICIT,
    user_note: str | None = None,
    user_tags: list[str] | None = None,
) -> KnowledgeItem | None:
    """Process a new knowledge capture through the full pipeline.

    Args:
        source: URL or plain text content
        capture_type: How content was captured (explicit/passive/seed)
        user_note: Optional user annotation
        user_tags: Optional user-provided tags (merged with extracted)

    Returns:
        Created KnowledgeItem or None if failed
    """
    logger.info(f"Processing {capture_type.value} capture: {source[:100]}...")

    # Check for duplicates
    if source.startswith(('http://', 'https://')):
        existing = await get_item_by_source(source)
        if existing:
            logger.info(f"Duplicate source found: {source}")
            # TODO: Consider updating access_count/last_accessed
            return existing

    # Step 1: Extract content
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
    title = extracted.title
    if not title or len(title) < 5:
        try:
            title = await extract_title(extracted.text)
        except Exception as e:
            logger.warning(f"Title extraction failed: {e}")
            title = source[:100] if source.startswith('http') else source.split('\n')[0][:100]

    # Step 3: Generate summary
    try:
        summary = await generate_summary(extracted.text, title)
    except Exception as e:
        logger.warning(f"Summary generation failed: {e}")
        summary = extracted.excerpt or extracted.text[:200]

    # Step 4: Extract topics
    try:
        topics = await extract_topics(extracted.text, title)
    except Exception as e:
        logger.warning(f"Topic extraction failed: {e}")
        topics = ['untagged']

    # Merge user tags if provided
    if user_tags:
        topics = list(set(topics + user_tags))[:8]

    # Step 5: Chunk content
    chunks = chunk_text(extracted.text)
    logger.debug(f"Created {len(chunks)} chunks")

    # Step 6: Generate embeddings for chunks
    chunk_texts = chunk_for_embedding(extracted.text, title)
    try:
        embeddings = await generate_embeddings_batch(chunk_texts)
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        # Continue without embeddings - search will be degraded
        embeddings = [[0.0] * 384 for _ in chunks]

    # Determine content type
    content_type = _detect_content_type(extracted.source, extracted.text)

    # Determine priority based on capture type
    priority = {
        CaptureType.EXPLICIT: PRIORITY_EXPLICIT,
        CaptureType.SEED: PRIORITY_SEED,
        CaptureType.PASSIVE: PRIORITY_PASSIVE,
    }.get(capture_type, PRIORITY_PASSIVE)

    # Step 7: Store in database
    now = datetime.now(timezone.utc)

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
    )

    try:
        created_item = await create_knowledge_item(item)
        if not created_item:
            logger.error("Failed to create knowledge item in database")
            return None

        logger.info(f"Created knowledge item: {created_item.id}")

        # Store chunks with embeddings
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
    if source.startswith(('http://', 'https://')):
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
