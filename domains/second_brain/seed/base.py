"""Base adapter for seed imports.

All seed adapters inherit from SeedAdapter and implement
the fetch() method to retrieve items from their source.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class SeedItem:
    """A single item to import from a seed source."""
    title: str
    content: str
    source_url: Optional[str] = None
    source_id: Optional[str] = None  # ID in the original system
    topics: list[str] = field(default_factory=list)
    created_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SeedResult:
    """Result of a seed import operation."""
    adapter_name: str
    items_found: int
    items_imported: int
    items_skipped: int  # Duplicates
    items_failed: int
    errors: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.items_found == 0:
            return 0.0
        return self.items_imported / self.items_found


class SeedAdapter(ABC):
    """Base class for seed import adapters.

    Each adapter fetches items from a specific source and
    converts them to SeedItems for import.
    """

    # Adapter metadata - override in subclasses
    name: str = "base"
    description: str = "Base adapter"
    source_system: str = "seed:unknown"

    def __init__(self, config: dict[str, Any] = None):
        """Initialize adapter with optional config.

        Args:
            config: Adapter-specific configuration
        """
        self.config = config or {}

    @abstractmethod
    async def fetch(self, limit: int = 100) -> list[SeedItem]:
        """Fetch items from the source.

        Args:
            limit: Maximum items to fetch

        Returns:
            List of SeedItems to import
        """
        pass

    async def validate(self) -> tuple[bool, str]:
        """Validate adapter configuration.

        Returns:
            Tuple of (is_valid, error_message)
        """
        return True, ""

    def get_default_topics(self) -> list[str]:
        """Get default topics for items from this source.

        Override in subclasses to add source-specific tags.
        """
        return []
