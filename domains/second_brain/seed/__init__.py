"""Seed import framework for Second Brain.

Bulk imports knowledge from external sources with 0.8 priority.
Each adapter handles a specific source type.
"""

from .base import SeedAdapter, SeedItem, SeedResult
from .runner import run_seed_import, run_all_adapters, get_available_adapters

# Import adapters to trigger registration
from . import adapters  # noqa: F401

__all__ = [
    "SeedAdapter",
    "SeedItem",
    "SeedResult",
    "run_seed_import",
    "run_all_adapters",
    "get_available_adapters",
]
