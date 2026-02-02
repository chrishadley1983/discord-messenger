"""Seed import runner.

Orchestrates the import process for seed adapters.
"""

from typing import Type

from logger import logger
from ..types import CaptureType
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
) -> SeedResult:
    """Run a seed import using the given adapter.

    Args:
        adapter: Configured adapter instance
        limit: Maximum items to import
        dry_run: If True, fetch but don't save

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

    # Validate adapter
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
            # Check for duplicates
            if item.source_url:
                existing = await get_item_by_source(item.source_url)
                if existing:
                    result.items_skipped += 1
                    continue

            # Merge default topics with item topics
            all_topics = list(set(adapter.get_default_topics() + item.topics))

            # Import via pipeline
            created = await process_capture(
                source=item.source_url or item.content,
                capture_type=CaptureType.SEED,
                user_tags=all_topics,
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
