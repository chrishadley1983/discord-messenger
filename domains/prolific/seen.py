"""SQLite store of study IDs we've already alerted on."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .config import SEEN_DB_PATH


def _conn() -> sqlite3.Connection:
    SEEN_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SEEN_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_studies (
            study_id   TEXT PRIMARY KEY,
            first_seen TEXT NOT NULL
        )
        """
    )
    return conn


def is_new(study_id: str) -> bool:
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM seen_studies WHERE study_id = ?", (study_id,)
        ).fetchone()
    return row is None


def mark_seen(study_id: str) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO seen_studies (study_id, first_seen) VALUES (?, ?)",
            (study_id, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
