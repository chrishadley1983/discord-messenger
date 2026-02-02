"""Type definitions for Second Brain knowledge system."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID


class CaptureType(str, Enum):
    """How the knowledge item was captured."""
    EXPLICIT = "explicit"   # User !save command (base_priority 1.0)
    PASSIVE = "passive"     # Auto-detected URL/idea (base_priority 0.3)
    SEED = "seed"           # Bulk import during bootstrap (base_priority 0.8)


class ContentType(str, Enum):
    """Type of content stored."""
    ARTICLE = "article"
    NOTE = "note"
    IDEA = "idea"
    VOICE_MEMO = "voice_memo"
    URL = "url"
    DOCUMENT = "document"
    CONVERSATION_EXTRACT = "conversation_extract"
    BOOKMARK = "bookmark"
    TRAINING_DATA = "training_data"
    SOCIAL_SAVE = "social_save"
    CALENDAR_EVENT = "calendar_event"
    CALENDAR_PATTERN = "calendar_pattern"
    KEY_DATE = "key_date"
    VIDEO = "video"
    DISCUSSION = "discussion"
    PDF = "pdf"
    CODE = "code"
    SOCIAL = "social"
    RECIPE = "recipe"
    FITNESS = "fitness"


class ConnectionType(str, Enum):
    """Type of connection between knowledge items."""
    SEMANTIC = "semantic"           # High embedding similarity between chunks
    TOPIC_OVERLAP = "topic_overlap" # Shared tags/topics
    CROSS_DOMAIN = "cross_domain"   # Different domains but related (most valuable)


class ItemStatus(str, Enum):
    """Status of a knowledge item."""
    PENDING = "pending"    # Passive capture awaiting full processing
    ACTIVE = "active"      # Fully processed and searchable
    ARCHIVED = "archived"  # Soft-deleted


@dataclass
class KnowledgeItem:
    """A knowledge item in the Second Brain."""
    id: str  # UUID as string for flexibility
    content_type: ContentType
    capture_type: CaptureType
    title: Optional[str]
    source: str  # URL or 'direct_input'
    full_text: Optional[str]
    summary: Optional[str]
    topics: list[str]
    priority: float  # base_priority
    decay_score: float
    access_count: int
    last_accessed: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    status: ItemStatus
    # Optional fields
    user_note: Optional[str] = None
    site_name: Optional[str] = None
    word_count: int = 0
    source_message_id: Optional[str] = None
    source_system: Optional[str] = None
    promoted_at: Optional[datetime] = None

    # Alias for backwards compatibility
    @property
    def base_priority(self) -> float:
        return self.priority

    @property
    def source_url(self) -> Optional[str]:
        if self.source.startswith('http'):
            return self.source
        return None

    @property
    def last_accessed_at(self) -> Optional[datetime]:
        return self.last_accessed

    @classmethod
    def from_db_row(cls, row: dict) -> "KnowledgeItem":
        """Create KnowledgeItem from database row."""
        # Handle both old and new field names
        source = row.get("source_url") or row.get("source") or "direct_input"
        priority = row.get("base_priority") or row.get("priority", 1.0)
        last_accessed = row.get("last_accessed_at") or row.get("last_accessed")
        created_at = row.get("created_at")
        updated_at = row.get("updated_at") or created_at

        return cls(
            id=str(row["id"]) if row.get("id") else "",
            content_type=ContentType(row["content_type"]),
            capture_type=CaptureType(row["capture_type"]),
            title=row.get("title"),
            source=source,
            full_text=row.get("full_text"),
            summary=row.get("summary"),
            topics=row.get("topics") or [],
            priority=priority,
            decay_score=row.get("decay_score", 1.0),
            access_count=row.get("access_count", 0),
            last_accessed=last_accessed,
            created_at=created_at,
            updated_at=updated_at,
            status=ItemStatus(row.get("status", "active")),
            user_note=row.get("user_note"),
            site_name=row.get("site_name"),
            word_count=row.get("word_count", 0),
            source_message_id=row.get("source_message_id"),
            source_system=row.get("source_system"),
            promoted_at=row.get("promoted_at"),
        )


@dataclass
class KnowledgeChunk:
    """A searchable chunk of a knowledge item."""
    id: UUID
    parent_id: UUID
    chunk_index: int
    content: str
    embedding: Optional[list[float]]
    created_at: datetime

    @classmethod
    def from_db_row(cls, row: dict) -> "KnowledgeChunk":
        """Create KnowledgeChunk from database row."""
        return cls(
            id=UUID(row["id"]) if isinstance(row["id"], str) else row["id"],
            parent_id=UUID(row["parent_id"]) if isinstance(row["parent_id"], str) else row["parent_id"],
            chunk_index=row["chunk_index"],
            content=row["content"],
            embedding=row.get("embedding"),
            created_at=row["created_at"],
        )


@dataclass
class KnowledgeConnection:
    """A discovered connection between two knowledge items."""
    id: UUID
    item_a_id: UUID
    item_b_id: UUID
    connection_type: ConnectionType
    description: Optional[str]
    similarity_score: Optional[float]
    surfaced: bool
    surfaced_at: Optional[datetime]
    created_at: datetime

    @classmethod
    def from_db_row(cls, row: dict) -> "KnowledgeConnection":
        """Create KnowledgeConnection from database row."""
        return cls(
            id=UUID(row["id"]) if isinstance(row["id"], str) else row["id"],
            item_a_id=UUID(row["item_a_id"]) if isinstance(row["item_a_id"], str) else row["item_a_id"],
            item_b_id=UUID(row["item_b_id"]) if isinstance(row["item_b_id"], str) else row["item_b_id"],
            connection_type=ConnectionType(row["connection_type"]),
            description=row.get("description"),
            similarity_score=row.get("similarity_score"),
            surfaced=row.get("surfaced", False),
            surfaced_at=row.get("surfaced_at"),
            created_at=row["created_at"],
        )


@dataclass
class ExtractedContent:
    """Content extracted from a URL or text input."""
    title: str
    text: str
    source: str
    excerpt: Optional[str] = None
    site_name: Optional[str] = None
    word_count: int = 0


@dataclass
class SearchResult:
    """A search result from semantic search."""
    item: KnowledgeItem
    chunks: list[KnowledgeChunk]
    best_similarity: float
    relevant_excerpts: list[str] = field(default_factory=list)

    @property
    def weighted_score(self) -> float:
        """Combined score: similarity × decay × priority."""
        return self.best_similarity * self.item.decay_score * self.item.base_priority


@dataclass
class PassiveCaptureMatch:
    """A detected passive capture from a message."""
    url: Optional[str] = None
    idea_text: Optional[str] = None
    signal_phrase: Optional[str] = None


@dataclass
class DigestData:
    """Data for weekly knowledge digest."""
    new_items: list[KnowledgeItem]
    new_connections: list[KnowledgeConnection]
    fading_items: list[KnowledgeItem]
    total_items: int
    total_connections: int
    most_accessed_item: Optional[KnowledgeItem] = None
