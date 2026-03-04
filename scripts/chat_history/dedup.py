"""Deduplication tracking for chat history imports.

Uses a local SQLite database to track which chunks have been imported,
preventing re-import on subsequent runs and supporting resume after crashes.
"""

import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


DEFAULT_DB_PATH = Path.home() / ".claude-history-imports.db"


class DedupTracker:
    """Track imported chunks using SHA-256 hashes in SQLite."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self._init_db()

    def _init_db(self):
        """Create tables if they don't exist."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS imported_chunks (
                content_hash TEXT PRIMARY KEY,
                conversation_id TEXT,
                chunk_index INTEGER,
                route TEXT,
                imported_at TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS import_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_file TEXT,
                started_at TEXT,
                completed_at TEXT,
                total_chunks INTEGER DEFAULT 0,
                imported INTEGER DEFAULT 0,
                skipped INTEGER DEFAULT 0,
                deduped INTEGER DEFAULT 0
            )
        """)
        self.conn.commit()

    @staticmethod
    def hash_content(text: str) -> str:
        """Generate SHA-256 hash of content."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def is_imported(self, content_hash: str) -> bool:
        """Check if a chunk has already been imported."""
        cursor = self.conn.execute(
            "SELECT 1 FROM imported_chunks WHERE content_hash = ?",
            (content_hash,)
        )
        return cursor.fetchone() is not None

    def mark_imported(self, content_hash: str, conversation_id: str,
                      chunk_index: int, route: str):
        """Mark a chunk as imported."""
        self.conn.execute(
            "INSERT OR IGNORE INTO imported_chunks (content_hash, conversation_id, chunk_index, route, imported_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (content_hash, conversation_id, chunk_index, route, datetime.utcnow().isoformat())
        )
        self.conn.commit()

    def start_run(self, source_file: str) -> int:
        """Start a new import run. Returns run ID."""
        cursor = self.conn.execute(
            "INSERT INTO import_runs (source_file, started_at) VALUES (?, ?)",
            (source_file, datetime.utcnow().isoformat())
        )
        self.conn.commit()
        return cursor.lastrowid

    def finish_run(self, run_id: int, total: int, imported: int,
                   skipped: int, deduped: int):
        """Finish an import run with stats."""
        self.conn.execute(
            "UPDATE import_runs SET completed_at = ?, total_chunks = ?, "
            "imported = ?, skipped = ?, deduped = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), total, imported, skipped, deduped, run_id)
        )
        self.conn.commit()

    def get_stats(self) -> dict:
        """Get overall import statistics."""
        cursor = self.conn.execute("SELECT COUNT(*) FROM imported_chunks")
        total = cursor.fetchone()[0]

        cursor = self.conn.execute(
            "SELECT route, COUNT(*) FROM imported_chunks GROUP BY route"
        )
        by_route = dict(cursor.fetchall())

        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM import_runs WHERE completed_at IS NOT NULL"
        )
        completed_runs = cursor.fetchone()[0]

        return {
            "total_imported": total,
            "by_route": by_route,
            "completed_runs": completed_runs,
        }

    def close(self):
        """Close the database connection."""
        self.conn.close()
