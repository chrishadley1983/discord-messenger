"""Seed import runner.

Orchestrates the import process for seed adapters.
"""

from typing import Type

from logger import logger
from ..types import CaptureType, ContentType
from ..pipeline import process_capture
from ..db import get_item_by_source
from .base import SeedAdapter, SeedItem, SeedResult


# Registry of available adapters
_adapters: dict[str, Type[SeedAdapter]] = {}


def register_adapter(adapter_class: Type[SeedAdapter]) -> Type[SeedAdapter]:
    """Decorator to register a seed adapter.

    Usage:
        @register_adapter
        class MyAdapter(SeedAdapter):
            name = "my-adapter"
            ...
    """
    _adapters[adapter_class.name] = adapter_class
    return adapter_class


def get_available_adapters() -> dict[str, Type[SeedAdapter]]:
    """Get all registered adapters."""
    return _adapters.copy()


async def run_seed_import(
    adapter: SeedAdapter,
    limit: int = 100,
    dry_run: bool = False,
    skip_validate: bool = False,
) -> SeedResult:
    """Run a seed import using the given adapter.

    Args:
        adapter: Configured adapter instance
        limit: Maximum items to import
        dry_run: If True, fetch but don't save
        skip_validate: If True, skip validation (caller already validated)

    Returns:
        SeedResult with import statistics
    """
    result = SeedResult(
        adapter_name=adapter.name,
        items_found=0,
        items_imported=0,
        items_skipped=0,
        items_failed=0,
    )

    # Validate adapter (unless caller already did)
    if not skip_validate:
        is_valid, error = await adapter.validate()
        if not is_valid:
            result.errors.append(f"Validation failed: {error}")
            return result

    # Fetch items
    logger.info(f"Fetching items from {adapter.name}...")
    try:
        items = await adapter.fetch(limit=limit)
        result.items_found = len(items)
        logger.info(f"Found {len(items)} items from {adapter.name}")
    except Exception as e:
        logger.error(f"Fetch failed for {adapter.name}: {e}")
        result.errors.append(f"Fetch error: {str(e)}")
        return result

    if dry_run:
        logger.info(f"Dry run - would import {len(items)} items")
        return result

    # Import each item
    for item in items:
        try:
            # Check for duplicates via source_url
            if item.source_url:
                existing = await get_item_by_source(item.source_url)
                if existing:
                    result.items_skipped += 1
                    continue

            # Merge default topics with item topics
            all_topics = list(set(adapter.get_default_topics() + item.topics))

            # Resolve content_type override from SeedItem
            content_type_override = None
            if item.content_type:
                try:
                    content_type_override = ContentType(item.content_type)
                except ValueError:
                    logger.warning(f"Unknown content_type '{item.content_type}', using auto-detect")

            # Import via pipeline — pass all SeedItem fields through
            created = await process_capture(
                source=item.source_url or item.content,
                capture_type=CaptureType.SEED,
                user_tags=all_topics,
                content_type_override=content_type_override,
                text=item.content if item.source_url else None,
                title_override=item.title,
                created_at_override=item.created_at,
                source_system=adapter.source_system,
            )

            if created:
                result.items_imported += 1
                logger.debug(f"Imported: {item.title[:50]}")
            else:
                result.items_failed += 1
                result.errors.append(f"Failed to import: {item.title[:50]}")

        except Exception as e:
            result.items_failed += 1
            result.errors.append(f"Error importing {item.title[:30]}: {str(e)}")

    logger.info(
        f"Seed import complete: {result.items_imported} imported, "
        f"{result.items_skipped} skipped, {result.items_failed} failed"
    )

    return result


async def run_all_adapters(
    limit_per_adapter: int = 50,
    dry_run: bool = False,
) -> list[SeedResult]:
    """Run all registered adapters.

    Args:
        limit_per_adapter: Max items per adapter
        dry_run: If True, fetch but don't save

    Returns:
        List of SeedResults
    """
    results = []

    for name, adapter_class in _adapters.items():
        logger.info(f"Running adapter: {name}")
        try:
            adapter = adapter_class()
            result = await run_seed_import(
                adapter,
                limit=limit_per_adapter,
                dry_run=dry_run,
            )
            results.append(result)
        except Exception as e:
            logger.error(f"Adapter {name} failed: {e}")
            results.append(SeedResult(
                adapter_name=name,
                items_found=0,
                items_imported=0,
                items_skipped=0,
                items_failed=0,
                errors=[str(e)],
            ))

    return results


async def run_seed_import_batched(
    adapter: SeedAdapter,
    limit: int = 100,
    embedding_batch_size: int = 50,
    skip_validate: bool = False,
) -> SeedResult:
    """Run a seed import with batched embedding for efficiency.

    Instead of embedding each item individually (N API calls per item),
    this collects all chunk texts across all items, then batch-embeds
    them in groups of `embedding_batch_size`.

    Saves ~2.5 minutes per daily seed run (80 API calls → ~5).
    """
    from ..pipeline import prepare_capture, PreparedItem
    from ..embed import generate_embeddings_batch
    from ..db import create_knowledge_item, create_knowledge_chunks, update_item_status
    from ..types import ItemStatus

    result = SeedResult(
        adapter_name=adapter.name,
        items_found=0,
        items_imported=0,
        items_skipped=0,
        items_failed=0,
    )

    if not skip_validate:
        is_valid, error = await adapter.validate()
        if not is_valid:
            result.errors.append(f"Validation failed: {error}")
            return result

    # Fetch items
    logger.info(f"[batched] Fetching items from {adapter.name}...")
    try:
        items = await adapter.fetch(limit=limit)
        result.items_found = len(items)
    except Exception as e:
        logger.error(f"Fetch failed for {adapter.name}: {e}")
        result.errors.append(f"Fetch error: {str(e)}")
        return result

    # Phase 1: Prepare all items (extract/summarize/tag/chunk — no embedding)
    prepared: list[PreparedItem] = []
    for item in items:
        try:
            # Check for duplicates
            if item.source_url:
                from ..db import get_item_by_source
                existing = await get_item_by_source(item.source_url)
                if existing:
                    result.items_skipped += 1
                    continue

            all_topics = list(set(adapter.get_default_topics() + item.topics))

            content_type_override = None
            if item.content_type:
                try:
                    content_type_override = ContentType(item.content_type)
                except ValueError:
                    pass

            prep = await prepare_capture(
                source=item.source_url or item.content,
                capture_type=CaptureType.SEED,
                user_tags=all_topics,
                content_type_override=content_type_override,
                text=item.content if item.source_url else None,
                title_override=item.title,
                created_at_override=item.created_at,
                source_system=adapter.source_system,
            )
            if prep:
                prepared.append(prep)
            else:
                result.items_skipped += 1

        except Exception as e:
            result.items_failed += 1
            result.errors.append(f"Prepare error {item.title[:30]}: {str(e)}")

    if not prepared:
        return result

    # Phase 2: Batch embed all chunk texts
    all_chunk_texts = []
    chunk_mapping = []  # (prepared_index, local_chunk_index)
    chunk_offset_map: dict[tuple[int, int], int] = {}  # (pi, ci) → global index
    for pi, prep in enumerate(prepared):
        for ci, ct in enumerate(prep.chunk_texts_for_embedding):
            chunk_offset_map[(pi, ci)] = len(all_chunk_texts)
            all_chunk_texts.append(ct)
            chunk_mapping.append((pi, ci))

    logger.info(
        f"[batched] Batch embedding {len(all_chunk_texts)} chunks "
        f"from {len(prepared)} items in batches of {embedding_batch_size}"
    )

    all_embeddings: list[list[float] | None] = [None] * len(all_chunk_texts)
    for batch_start in range(0, len(all_chunk_texts), embedding_batch_size):
        batch_end = min(batch_start + embedding_batch_size, len(all_chunk_texts))
        batch_texts = all_chunk_texts[batch_start:batch_end]
        try:
            batch_embeddings = await generate_embeddings_batch(batch_texts)
            for i, emb in enumerate(batch_embeddings):
                all_embeddings[batch_start + i] = emb
        except Exception as e:
            logger.error(f"Batch embedding failed at offset {batch_start}: {e}")
            # Mark these as None — items will be saved without embeddings

    # Phase 3: Store items and chunks
    for pi, prep in enumerate(prepared):
        try:
            created_item = await create_knowledge_item(prep.item)
            if not created_item:
                result.items_failed += 1
                continue

            # Collect embeddings for this item's chunks
            chunk_data = []
            has_all_embeddings = True
            for ci, chunk in enumerate(prep.chunks):
                global_idx = chunk_offset_map[(pi, ci)]
                emb = all_embeddings[global_idx]
                if emb is None:
                    has_all_embeddings = False
                    break
                chunk_data.append({
                    'index': ci,
                    'text': chunk.text,
                    'embedding': emb,
                    'start_word': chunk.start_word,
                    'end_word': chunk.end_word,
                })

            if has_all_embeddings and chunk_data:
                await create_knowledge_chunks(created_item.id, chunk_data)
            else:
                await update_item_status(created_item.id, ItemStatus.PENDING)
                logger.warning(f"Item {created_item.id} saved as PENDING — missing embeddings")

            result.items_imported += 1

        except Exception as e:
            result.items_failed += 1
            result.errors.append(f"Store error: {str(e)[:50]}")

    logger.info(
        f"[batched] Import complete: {result.items_imported} imported, "
        f"{result.items_skipped} skipped, {result.items_failed} failed"
    )

    return result
