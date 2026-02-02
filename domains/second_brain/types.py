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


class ConnectionType(str, Enum):
    """Type of connection between knowledge items."""
    SEMANTIC = "semantic"           # High embedding similarity between chunks
    TOPIC_OVERLAP = "topic_overlap" # Shared tags/topics
    CROSS_DOMAIN = "cross_domain"   # Different domains but related (most valuable)


class ItemStatus(str, Enum):
    """Status of a knowledge item."""
    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass
class KnowledgeItem:
    """A knowledge item in the Second Brain."""
    id: UUID
    content_type: ContentType
    capture_type: CaptureType
    title: Optional[str]
    source_url: Optional[str]
    source_message_id: Optional[str]
    source_system: Optional[str]
    full_text: Optional[str]
    summary: Optional[str]
    topics: list[str]
    base_priority: float
    last_accessed_at: Optional[datetime]
    access_count: int
    decay_score: float
    created_at: datetime
    promoted_at: Optional[datetime]
    status: ItemStatus

    @classmethod
    def from_db_row(cls, row: dict) -> "KnowledgeItem":
        """Create KnowledgeItem from database row."""
        return cls(
            id=UUID(row["id"]) if isinstance(row["id"], str) else row["id"],
            content_type=ContentType(row["content_type"]),
            capture_type=CaptureType(row["capture_type"]),
            title=row.get("title"),
            source_url=row.get("source_url"),
            source_message_id=row.get("source_message_id"),
            source_system=row.get("source_system"),
            full_text=row.get("full_text"),
            summary=row.get("summary"),
            topics=row.get("topics") or [],
            base_priority=row.get("base_priority", 1.0),
            last_accessed_at=row.get("last_accessed_at"),
            access_count=row.get("access_count", 0),
            decay_score=row.get("decay_score", 1.0),
            created_at=row["created_at"],
            promoted_at=row.get("promoted_at"),
            status=ItemStatus(row.get("status", "active")),
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
