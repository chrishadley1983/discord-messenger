"""Persistent capture store for reliable memory capture.

Stores conversation captures in local SQLite before sending to worker.
Also manages context cache for graceful degradation during outages.
Survives bot restarts, handles worker outages gracefully.
"""

import hashlib
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from logger import logger
from . import config


@dataclass
class PendingCapture:
    """A capture waiting to be sent to the worker."""
    id: int
    session_id: str
    user_message: str
    assistant_response: str
    channel: str
    created_at: int
    status: str
    retries: int
    last_error: Optional[str]
    sent_at: Optional[int]


@dataclass
class CachedContext:
    """A cached memory context response."""
    query_hash: str
    context: str
    fetched_at: int


# Module-level connection (reused for performance)
_connection: Optional[sqlite3.Connection] = None


def _get_connection() -> sqlite3.Connection:
    """Get or create database connection with WAL mode."""
    global _connection

    if _connection is not None:
        return _connection

    # Ensure data directory exists
    db_path = Path(config.CAPTURE_STORE_DB)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Create connection with WAL mode for concurrent access
    _connection = sqlite3.connect(
        config.CAPTURE_STORE_DB,
        check_same_thread=False,  # Allow multi-threaded access
        timeout=10.0
    )
    _connection.row_factory = sqlite3.Row

    # Enable WAL mode for better concurrent performance
    _connection.execute("PRAGMA journal_mode=WAL")
    _connection.execute("PRAGMA busy_timeout=5000")

    # Initialize schema
    _init_schema(_connection)

    logger.info(f"Capture store initialized: {config.CAPTURE_STORE_DB}")
    return _connection


def _init_schema(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pending_captures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            user_message TEXT NOT NULL,
            assistant_response TEXT NOT NULL,
            channel TEXT DEFAULT 'peterbot',
            created_at INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            retries INTEGER DEFAULT 0,
            last_error TEXT,
            sent_at INTEGER
        );

        CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_captures(status);
        CREATE INDEX IF NOT EXISTS idx_pending_created ON pending_captures(created_at);
        CREATE INDEX IF NOT EXISTS idx_pending_sent ON pending_captures(sent_at);

        -- Context cache for graceful degradation during worker outages
        CREATE TABLE IF NOT EXISTS context_cache (
            query_hash TEXT PRIMARY KEY,
            context TEXT NOT NULL,
            fetched_at INTEGER NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_context_fetched ON context_cache(fetched_at);
    """)
    conn.commit()


@contextmanager
def _transaction():
    """Context manager for database transactions."""
    conn = _get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def add_capture(
    session_id: str,
    user_message: str,
    assistant_response: str,
    channel: str = "peterbot"
) -> int:
    """Add a capture to the pending queue.

    Args:
        session_id: Session identifier (e.g., discord-123)
        user_message: The user's message
        assistant_response: The bot's response
        channel: Channel name for categorization

    Returns:
        The capture ID
    """
    with _transaction() as conn:
        cursor = conn.execute(
            """
            INSERT INTO pending_captures
            (session_id, user_message, assistant_response, channel, created_at, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
            """,
            (session_id, user_message, assistant_response, channel, int(time.time()))
        )
        capture_id = cursor.lastrowid
        logger.debug(f"Capture {capture_id} added to pending queue")
        return capture_id


def get_pending(limit: int = 1) -> list[PendingCapture]:
    """Get pending captures, oldest first.

    Args:
        limit: Maximum number to return

    Returns:
        List of PendingCapture objects
    """
    conn = _get_connection()
    rows = conn.execute(
        """
        SELECT * FROM pending_captures
        WHERE status = 'pending'
        ORDER BY created_at ASC
        LIMIT ?
        """,
        (limit,)
    ).fetchall()

    return [PendingCapture(**dict(row)) for row in rows]


def get_by_id(capture_id: int) -> Optional[PendingCapture]:
    """Get a specific capture by ID."""
    conn = _get_connection()
    row = conn.execute(
        "SELECT * FROM pending_captures WHERE id = ?",
        (capture_id,)
    ).fetchone()

    return PendingCapture(**dict(row)) if row else None


def mark_sending(capture_id: int) -> None:
    """Mark a capture as currently being sent (prevents duplicate sends)."""
    with _transaction() as conn:
        conn.execute(
            "UPDATE pending_captures SET status = 'sending' WHERE id = ?",
            (capture_id,)
        )


def mark_sent(capture_id: int) -> None:
    """Mark a capture as successfully sent."""
    with _transaction() as conn:
        conn.execute(
            """
            UPDATE pending_captures
            SET status = 'sent', sent_at = ?
            WHERE id = ?
            """,
            (int(time.time()), capture_id)
        )
        logger.debug(f"Capture {capture_id} marked as sent")


def mark_failed(capture_id: int, error: str) -> None:
    """Record a send failure and increment retry count.

    If retries exceed CAPTURE_MAX_RETRIES, status becomes 'failed'.
    Otherwise, status returns to 'pending' for retry.
    """
    with _transaction() as conn:
        # Get current retry count
        row = conn.execute(
            "SELECT retries FROM pending_captures WHERE id = ?",
            (capture_id,)
        ).fetchone()

        if not row:
            return

        new_retries = row["retries"] + 1

        if new_retries >= config.CAPTURE_MAX_RETRIES:
            # Max retries exceeded, mark as permanently failed
            conn.execute(
                """
                UPDATE pending_captures
                SET status = 'failed', retries = ?, last_error = ?
                WHERE id = ?
                """,
                (new_retries, error, capture_id)
            )
            logger.warning(f"Capture {capture_id} marked as failed after {new_retries} retries: {error}")
        else:
            # Return to pending for retry
            conn.execute(
                """
                UPDATE pending_captures
                SET status = 'pending', retries = ?, last_error = ?
                WHERE id = ?
                """,
                (new_retries, error, capture_id)
            )
            logger.debug(f"Capture {capture_id} retry {new_retries}: {error}")


def get_queue_stats() -> dict:
    """Get statistics about the capture queue.

    Returns:
        Dict with pending_count, sending_count, sent_count, failed_count, oldest_pending_age
    """
    conn = _get_connection()
    now = int(time.time())

    # Count by status
    rows = conn.execute(
        """
        SELECT status, COUNT(*) as count
        FROM pending_captures
        GROUP BY status
        """
    ).fetchall()

    stats = {"pending": 0, "sending": 0, "sent": 0, "failed": 0}
    for row in rows:
        stats[row["status"]] = row["count"]

    # Oldest pending age
    oldest = conn.execute(
        """
        SELECT MIN(created_at) as oldest
        FROM pending_captures
        WHERE status IN ('pending', 'sending')
        """
    ).fetchone()

    oldest_age = 0
    if oldest and oldest["oldest"]:
        oldest_age = now - oldest["oldest"]

    return {
        "pending_count": stats["pending"],
        "sending_count": stats["sending"],
        "sent_count": stats["sent"],
        "failed_count": stats["failed"],
        "oldest_pending_age": oldest_age,
    }


def cleanup_old_captures() -> tuple[int, int]:
    """Delete old captures according to retention policy.

    Returns:
        Tuple of (sent_deleted, failed_deleted)
    """
    now = int(time.time())
    sent_cutoff = now - (config.CAPTURE_SENT_RETENTION_DAYS * 86400)
    failed_cutoff = now - (config.CAPTURE_FAILED_RETENTION_DAYS * 86400)

    with _transaction() as conn:
        # Delete old sent captures
        cursor = conn.execute(
            "DELETE FROM pending_captures WHERE status = 'sent' AND sent_at < ?",
            (sent_cutoff,)
        )
        sent_deleted = cursor.rowcount

        # Delete old failed captures
        cursor = conn.execute(
            "DELETE FROM pending_captures WHERE status = 'failed' AND created_at < ?",
            (failed_cutoff,)
        )
        failed_deleted = cursor.rowcount

    if sent_deleted or failed_deleted:
        logger.info(f"Capture cleanup: {sent_deleted} sent, {failed_deleted} failed deleted")

    return sent_deleted, failed_deleted


def reset_stale_sending(timeout_seconds: int = 300) -> int:
    """Reset captures stuck in 'sending' state back to 'pending'.

    This handles cases where the bot crashed mid-send.

    Args:
        timeout_seconds: Captures in 'sending' state longer than this are reset

    Returns:
        Number of captures reset
    """
    cutoff = int(time.time()) - timeout_seconds

    with _transaction() as conn:
        # Find stale sending captures (no sent_at, but old created_at or updated recently would need tracking)
        # For simplicity, reset any 'sending' that's been pending too long
        cursor = conn.execute(
            """
            UPDATE pending_captures
            SET status = 'pending'
            WHERE status = 'sending' AND created_at < ?
            """,
            (cutoff,)
        )
        reset_count = cursor.rowcount

    if reset_count:
        logger.info(f"Reset {reset_count} stale 'sending' captures to 'pending'")

    return reset_count


def close() -> None:
    """Close the database connection."""
    global _connection
    if _connection:
        _connection.close()
        _connection = None
        logger.debug("Capture store connection closed")


# ============================================================================
# Context Cache Functions
# ============================================================================

def _hash_query(query: str) -> str:
    """Create a hash of the query for cache key."""
    return hashlib.sha256(query.encode('utf-8')).hexdigest()[:32]


def get_cached_context(query: str) -> Optional[CachedContext]:
    """Get cached context for a query if it exists and is not expired.

    Args:
        query: The query string to look up

    Returns:
        CachedContext if found and not expired, None otherwise
    """
    conn = _get_connection()
    query_hash = _hash_query(query)
    now = int(time.time())
    ttl = config.CONTEXT_CACHE_TTL_SECONDS

    row = conn.execute(
        """
        SELECT query_hash, context, fetched_at
        FROM context_cache
        WHERE query_hash = ? AND fetched_at > ?
        """,
        (query_hash, now - ttl)
    ).fetchone()

    if row:
        logger.debug(f"Context cache HIT for query hash {query_hash[:8]}...")
        return CachedContext(**dict(row))

    logger.debug(f"Context cache MISS for query hash {query_hash[:8]}...")
    return None


def get_cached_context_stale(query: str) -> Optional[CachedContext]:
    """Get cached context for a query, even if expired.

    Used during worker outages when stale data is better than no data.

    Args:
        query: The query string to look up

    Returns:
        CachedContext if found (regardless of age), None otherwise
    """
    conn = _get_connection()
    query_hash = _hash_query(query)

    row = conn.execute(
        """
        SELECT query_hash, context, fetched_at
        FROM context_cache
        WHERE query_hash = ?
        """,
        (query_hash,)
    ).fetchone()

    if row:
        age = int(time.time()) - row["fetched_at"]
        logger.debug(f"Context cache STALE HIT for query hash {query_hash[:8]}... (age: {age}s)")
        return CachedContext(**dict(row))

    return None


def set_cached_context(query: str, context: str) -> None:
    """Store context in cache, enforcing max entries limit.

    Args:
        query: The query string (used to generate hash key)
        context: The context to cache
    """
    query_hash = _hash_query(query)
    now = int(time.time())

    with _transaction() as conn:
        # Upsert the context
        conn.execute(
            """
            INSERT OR REPLACE INTO context_cache (query_hash, context, fetched_at)
            VALUES (?, ?, ?)
            """,
            (query_hash, context, now)
        )

        # Enforce max entries limit by deleting oldest
        max_entries = config.CONTEXT_CACHE_MAX_ENTRIES
        conn.execute(
            """
            DELETE FROM context_cache
            WHERE query_hash NOT IN (
                SELECT query_hash FROM context_cache
                ORDER BY fetched_at DESC
                LIMIT ?
            )
            """,
            (max_entries,)
        )

    logger.debug(f"Context cached for query hash {query_hash[:8]}...")


def cleanup_expired_cache() -> int:
    """Delete expired cache entries.

    Returns:
        Number of entries deleted
    """
    now = int(time.time())
    ttl = config.CONTEXT_CACHE_TTL_SECONDS

    with _transaction() as conn:
        cursor = conn.execute(
            "DELETE FROM context_cache WHERE fetched_at < ?",
            (now - ttl,)
        )
        deleted = cursor.rowcount

    if deleted:
        logger.debug(f"Cleaned up {deleted} expired cache entries")

    return deleted


def get_cache_stats() -> dict:
    """Get statistics about the context cache.

    Returns:
        Dict with entry_count, oldest_entry_age, newest_entry_age
    """
    conn = _get_connection()
    now = int(time.time())

    # Count entries
    count_row = conn.execute("SELECT COUNT(*) as count FROM context_cache").fetchone()
    entry_count = count_row["count"] if count_row else 0

    # Get age range
    age_row = conn.execute(
        """
        SELECT
            MIN(fetched_at) as oldest,
            MAX(fetched_at) as newest
        FROM context_cache
        """
    ).fetchone()

    oldest_age = 0
    newest_age = 0
    if age_row and age_row["oldest"]:
        oldest_age = now - age_row["oldest"]
        newest_age = now - age_row["newest"]

    return {
        "entry_count": entry_count,
        "oldest_entry_age": oldest_age,
        "newest_entry_age": newest_age,
        "max_entries": config.CONTEXT_CACHE_MAX_ENTRIES,
        "ttl_seconds": config.CONTEXT_CACHE_TTL_SECONDS,
    }
