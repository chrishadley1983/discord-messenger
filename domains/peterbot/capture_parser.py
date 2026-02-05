"""Parser Capture Store - For self-improving parser system.

Captures raw/parsed message pairs for parser improvement. This is separate from
capture_store.py which handles memory captures for claude-mem.

Based on SELF_IMPROVING_PARSER.md Phase 1.
"""

import json
import re
import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from logger import logger

# Database path
DB_PATH = Path("data/parser_fixtures.db")

# ANSI escape sequence pattern
ANSI_PATTERN = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')

# Module-level connection
_connection: Optional[sqlite3.Connection] = None


@dataclass
class ParserFixture:
    """A curated parser test fixture."""
    id: str
    created_at: str
    updated_at: Optional[str]
    raw_capture: str
    screen_before: Optional[str]
    expected_output: str
    category: str
    tags: list[str]
    difficulty: str
    source: str
    source_date: Optional[str]
    channel_id: Optional[str]
    notes: Optional[str]
    last_pass: Optional[bool]
    last_run_at: Optional[str]
    fail_count: int
    regression_at: Optional[str]


@dataclass
class ParserCapture:
    """A captured raw/parsed message pair."""
    id: str
    captured_at: str
    channel_id: str
    channel_name: Optional[str]
    is_scheduled: bool
    skill_name: Optional[str]
    screen_before: Optional[str]
    screen_after: str
    parser_output: Optional[str]
    pipeline_output: Optional[str]
    was_empty: bool
    had_ansi: bool
    had_echo: bool
    was_truncated: bool
    discord_msg_id: Optional[str]
    user_reacted: Optional[str]
    reviewed: bool
    promoted: bool
    fixture_id: Optional[str]
    quality_score: Optional[float]


def _get_connection() -> sqlite3.Connection:
    """Get or create database connection."""
    global _connection

    if _connection is not None:
        return _connection

    # Ensure data directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    _connection = sqlite3.connect(
        str(DB_PATH),
        check_same_thread=False,
        timeout=10.0
    )
    _connection.row_factory = sqlite3.Row

    # Enable WAL mode
    _connection.execute("PRAGMA journal_mode=WAL")
    _connection.execute("PRAGMA busy_timeout=5000")

    # Initialize schema
    _init_schema(_connection)

    logger.info(f"Parser capture store initialized: {DB_PATH}")
    return _connection


def _init_schema(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist."""
    conn.executescript("""
        -- Parser fixtures table (curated test cases)
        CREATE TABLE IF NOT EXISTS fixtures (
            id              TEXT PRIMARY KEY,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            -- Input: exactly what the parser receives
            raw_capture     TEXT NOT NULL,
            screen_before   TEXT,

            -- Expected output: what the parser should produce
            expected_output TEXT NOT NULL,

            -- Classification
            category        TEXT NOT NULL,
            tags            TEXT DEFAULT '[]',
            difficulty      TEXT DEFAULT 'normal',

            -- Provenance
            source          TEXT NOT NULL,
            source_date     TIMESTAMP,
            channel_id      TEXT,
            notes           TEXT,

            -- Quality tracking
            last_pass       BOOLEAN,
            last_run_at     TIMESTAMP,
            fail_count      INTEGER DEFAULT 0,
            regression_at   TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_fixtures_category ON fixtures(category);
        CREATE INDEX IF NOT EXISTS idx_fixtures_source ON fixtures(source);
        CREATE INDEX IF NOT EXISTS idx_fixtures_last_pass ON fixtures(last_pass);
        CREATE INDEX IF NOT EXISTS idx_fixtures_difficulty ON fixtures(difficulty);

        -- Captures table (raw/parsed pairs from live traffic)
        CREATE TABLE IF NOT EXISTS captures (
            id              TEXT PRIMARY KEY,
            captured_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            -- Context
            channel_id      TEXT NOT NULL,
            channel_name    TEXT,
            is_scheduled    BOOLEAN DEFAULT FALSE,
            skill_name      TEXT,

            -- Raw data at each stage
            screen_before   TEXT,
            screen_after    TEXT NOT NULL,
            parser_output   TEXT,
            pipeline_output TEXT,

            -- Quality signals
            was_empty       BOOLEAN DEFAULT FALSE,
            had_ansi        BOOLEAN DEFAULT FALSE,
            had_echo        BOOLEAN DEFAULT FALSE,
            was_truncated   BOOLEAN DEFAULT FALSE,
            discord_msg_id  TEXT,
            user_reacted    TEXT,

            -- Processing
            reviewed        BOOLEAN DEFAULT FALSE,
            promoted        BOOLEAN DEFAULT FALSE,
            fixture_id      TEXT,
            quality_score   REAL
        );

        CREATE INDEX IF NOT EXISTS idx_captures_date ON captures(captured_at);
        CREATE INDEX IF NOT EXISTS idx_captures_quality ON captures(quality_score);
        CREATE INDEX IF NOT EXISTS idx_captures_reviewed ON captures(reviewed);
        CREATE INDEX IF NOT EXISTS idx_captures_empty ON captures(was_empty);
        CREATE INDEX IF NOT EXISTS idx_captures_discord_msg ON captures(discord_msg_id);

        -- Scheduled output format specs (Phase 4)
        CREATE TABLE IF NOT EXISTS scheduled_output_specs (
            id              TEXT PRIMARY KEY,
            skill_name      TEXT NOT NULL UNIQUE,
            display_name    TEXT NOT NULL,
            schedule_ref    TEXT,

            required_sections   TEXT NOT NULL,
            section_order       TEXT,
            required_indicators TEXT DEFAULT '[]',
            min_length          INTEGER DEFAULT 100,
            max_length          INTEGER DEFAULT 3000,
            expected_patterns   TEXT DEFAULT '[]',
            forbidden_patterns  TEXT DEFAULT '[]',

            golden_examples     TEXT DEFAULT '[]',
            format_score_threshold REAL DEFAULT 0.85,

            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Scheduled output history (Phase 4)
        CREATE TABLE IF NOT EXISTS scheduled_output_history (
            id              TEXT PRIMARY KEY,
            skill_name      TEXT NOT NULL,
            captured_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            channel_id      TEXT,

            output_text     TEXT NOT NULL,

            format_score    REAL,
            section_scores  TEXT,
            drift_detected  BOOLEAN DEFAULT FALSE,
            drift_details   TEXT,

            reviewed        BOOLEAN DEFAULT FALSE,
            action_taken    TEXT,
            notes           TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_soh_skill ON scheduled_output_history(skill_name);
        CREATE INDEX IF NOT EXISTS idx_soh_date ON scheduled_output_history(captured_at);
        CREATE INDEX IF NOT EXISTS idx_soh_drift ON scheduled_output_history(drift_detected);

        -- Feedback table (Phase 6)
        CREATE TABLE IF NOT EXISTS feedback (
            id              TEXT PRIMARY KEY,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            input_method    TEXT NOT NULL,
            channel_id      TEXT,
            channel_name    TEXT,
            user_id         TEXT NOT NULL,

            discord_msg_id  TEXT,
            capture_id      TEXT,

            category        TEXT NOT NULL DEFAULT 'general',
            skill_name      TEXT,
            description     TEXT,
            reaction_emoji  TEXT,
            priority        TEXT DEFAULT 'normal',

            status          TEXT DEFAULT 'pending',
            consumed_by_cycle TEXT,
            resolution      TEXT,
            resolved_at     TIMESTAMP,

            promoted_to_fixture BOOLEAN DEFAULT FALSE,
            fixture_id      TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_feedback_status ON feedback(status);
        CREATE INDEX IF NOT EXISTS idx_feedback_date ON feedback(created_at);
        CREATE INDEX IF NOT EXISTS idx_feedback_category ON feedback(category);
        CREATE INDEX IF NOT EXISTS idx_feedback_skill ON feedback(skill_name);

        -- Improvement cycle history (Phase 3)
        CREATE TABLE IF NOT EXISTS improvement_cycles (
            id              TEXT PRIMARY KEY,
            started_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at    TIMESTAMP,

            target_stage    TEXT,
            target_file     TEXT,
            target_function TEXT,

            problem_statement TEXT,
            proposed_approach TEXT,
            affected_fixtures TEXT,

            regression_before TEXT,
            regression_after TEXT,

            committed       BOOLEAN DEFAULT FALSE,
            rollback_reason TEXT,
            commit_hash     TEXT,

            score_before    REAL,
            score_after     REAL,
            fixtures_improved INTEGER DEFAULT 0,
            regressions     INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_cycles_date ON improvement_cycles(started_at);
        CREATE INDEX IF NOT EXISTS idx_cycles_committed ON improvement_cycles(committed);
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


def _generate_id() -> str:
    """Generate a random hex ID."""
    return secrets.token_hex(8)


class ParserCaptureStore:
    """Captures raw/parsed message pairs for parser improvement."""

    def __init__(self, db_path: str = None):
        """Initialize the store."""
        if db_path:
            global DB_PATH
            DB_PATH = Path(db_path)
        self._ensure_connection()

    def _ensure_connection(self):
        """Ensure database connection exists."""
        _get_connection()

    def capture(
        self,
        channel_id: str,
        channel_name: str,
        screen_before: str | None,
        screen_after: str,
        parser_output: str | None,
        pipeline_output: str | None,
        is_scheduled: bool = False,
        skill_name: str | None = None,
        discord_msg_id: str | None = None,
    ) -> str:
        """Store a capture. Returns capture ID."""

        was_empty = not pipeline_output or not pipeline_output.strip()
        had_ansi = bool(ANSI_PATTERN.search(pipeline_output or ""))
        had_echo = self._detect_echo(screen_before, pipeline_output)
        was_truncated = len(pipeline_output or "") > 1900

        with _transaction() as conn:
            capture_id = _generate_id()
            conn.execute("""
                INSERT INTO captures
                (id, channel_id, channel_name, screen_before, screen_after,
                 parser_output, pipeline_output, is_scheduled, skill_name,
                 discord_msg_id, was_empty, had_ansi, had_echo, was_truncated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (capture_id, channel_id, channel_name, screen_before,
                  screen_after, parser_output, pipeline_output, is_scheduled,
                  skill_name, discord_msg_id, was_empty, had_ansi, had_echo,
                  was_truncated))

        logger.debug(f"Parser capture {capture_id[:8]}... stored")
        return capture_id

    def flag_reaction(self, discord_msg_id: str, reaction: str) -> bool:
        """Update capture with user reaction. Returns True if found."""
        with _transaction() as conn:
            cursor = conn.execute("""
                UPDATE captures SET user_reacted = ?
                WHERE discord_msg_id = ?
            """, (reaction, discord_msg_id))
            found = cursor.rowcount > 0

        if found:
            logger.debug(f"Flagged capture for msg {discord_msg_id} with {reaction}")
        return found

    def get_recent_failures(self, hours: int = 24) -> list[dict]:
        """Get captures with quality issues from the last N hours."""
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()

        conn = _get_connection()
        rows = conn.execute("""
            SELECT * FROM captures
            WHERE captured_at > ?
            AND (was_empty = 1 OR had_ansi = 1 OR had_echo = 1
                 OR quality_score < 0.8 OR user_reacted IS NOT NULL)
            AND reviewed = 0
            ORDER BY captured_at DESC
        """, (cutoff,)).fetchall()

        return [dict(r) for r in rows]

    def get_capture(self, capture_id: str) -> Optional[ParserCapture]:
        """Get a specific capture by ID."""
        conn = _get_connection()
        row = conn.execute(
            "SELECT * FROM captures WHERE id = ?", (capture_id,)
        ).fetchone()

        if row:
            data = dict(row)
            return ParserCapture(**data)
        return None

    def get_capture_by_discord_msg(self, discord_msg_id: str) -> Optional[ParserCapture]:
        """Get capture by Discord message ID."""
        conn = _get_connection()
        row = conn.execute(
            "SELECT * FROM captures WHERE discord_msg_id = ?", (discord_msg_id,)
        ).fetchone()

        if row:
            return ParserCapture(**dict(row))
        return None

    def promote_to_fixture(
        self,
        capture_id: str,
        expected_output: str,
        category: str,
        tags: list[str] | None = None,
        notes: str | None = None
    ) -> str:
        """Promote a capture to a permanent fixture."""
        conn = _get_connection()
        cap = conn.execute(
            "SELECT * FROM captures WHERE id = ?", (capture_id,)
        ).fetchone()

        if not cap:
            raise ValueError(f"Capture {capture_id} not found")

        with _transaction() as conn:
            fixture_id = _generate_id()
            conn.execute("""
                INSERT INTO fixtures
                (id, raw_capture, screen_before, expected_output, category,
                 tags, source, source_date, channel_id, notes)
                VALUES (?, ?, ?, ?, ?, ?, 'capture', ?, ?, ?)
            """, (fixture_id, cap['screen_after'], cap['screen_before'],
                  expected_output, category, json.dumps(tags or []),
                  cap['captured_at'], cap['channel_id'], notes))

            conn.execute("""
                UPDATE captures SET promoted = 1, fixture_id = ?
                WHERE id = ?
            """, (fixture_id, capture_id))

        logger.info(f"Promoted capture {capture_id[:8]} to fixture {fixture_id[:8]}")
        return fixture_id

    def add_fixture(
        self,
        raw_capture: str,
        expected_output: str,
        category: str,
        source: str = 'manual',
        screen_before: str | None = None,
        tags: list[str] | None = None,
        difficulty: str = 'normal',
        notes: str | None = None
    ) -> str:
        """Add a fixture directly (for synthetic/manual fixtures)."""
        with _transaction() as conn:
            fixture_id = _generate_id()
            conn.execute("""
                INSERT INTO fixtures
                (id, raw_capture, screen_before, expected_output, category,
                 tags, difficulty, source, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (fixture_id, raw_capture, screen_before, expected_output,
                  category, json.dumps(tags or []), difficulty, source, notes))

        logger.info(f"Added {source} fixture {fixture_id[:8]} category={category}")
        return fixture_id

    def get_fixtures(
        self,
        category: str | None = None,
        failing_only: bool = False,
        limit: int | None = None
    ) -> list[ParserFixture]:
        """Get fixtures, optionally filtered."""
        conn = _get_connection()

        query = "SELECT * FROM fixtures WHERE 1=1"
        params = []

        if category:
            query += " AND category = ?"
            params.append(category)

        if failing_only:
            query += " AND (last_pass = 0 OR last_pass IS NULL)"

        query += " ORDER BY category, created_at"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        rows = conn.execute(query, params).fetchall()

        fixtures = []
        for row in rows:
            data = dict(row)
            data['tags'] = json.loads(data.get('tags') or '[]')
            fixtures.append(ParserFixture(**data))

        return fixtures

    def get_fixture(self, fixture_id: str) -> Optional[ParserFixture]:
        """Get a specific fixture by ID."""
        conn = _get_connection()
        row = conn.execute(
            "SELECT * FROM fixtures WHERE id = ?", (fixture_id,)
        ).fetchone()

        if row:
            data = dict(row)
            data['tags'] = json.loads(data.get('tags') or '[]')
            return ParserFixture(**data)
        return None

    def update_fixture_result(
        self,
        fixture_id: str,
        passed: bool,
        regressed: bool = False
    ) -> None:
        """Update fixture with test result."""
        now = datetime.utcnow().isoformat()

        with _transaction() as conn:
            conn.execute("""
                UPDATE fixtures SET
                    last_pass = ?,
                    last_run_at = ?,
                    fail_count = fail_count + ?,
                    regression_at = CASE WHEN ? = 1 THEN ? ELSE regression_at END
                WHERE id = ?
            """, (
                passed,
                now,
                0 if passed else 1,
                1 if regressed else 0,
                now,
                fixture_id
            ))

    def get_fixture_stats(self) -> dict:
        """Get fixture statistics."""
        conn = _get_connection()

        total = conn.execute("SELECT COUNT(*) as c FROM fixtures").fetchone()['c']
        passing = conn.execute(
            "SELECT COUNT(*) as c FROM fixtures WHERE last_pass = 1"
        ).fetchone()['c']
        failing = conn.execute(
            "SELECT COUNT(*) as c FROM fixtures WHERE last_pass = 0"
        ).fetchone()['c']
        untested = conn.execute(
            "SELECT COUNT(*) as c FROM fixtures WHERE last_pass IS NULL"
        ).fetchone()['c']

        by_category = {}
        rows = conn.execute("""
            SELECT category, COUNT(*) as total,
                   SUM(CASE WHEN last_pass = 1 THEN 1 ELSE 0 END) as passed
            FROM fixtures GROUP BY category
        """).fetchall()
        for r in rows:
            by_category[r['category']] = {
                'total': r['total'],
                'passed': r['passed'] or 0
            }

        return {
            'total': total,
            'passing': passing,
            'failing': failing,
            'untested': untested,
            'pass_rate': passing / total if total > 0 else 0.0,
            'by_category': by_category
        }

    def cleanup_old_captures(self, keep_days: int = 7) -> tuple[int, int]:
        """Remove old captures that haven't been promoted.

        Returns (normal_deleted, failure_deleted).
        """
        cutoff_normal = (datetime.utcnow() - timedelta(days=keep_days)).isoformat()
        cutoff_failures = (datetime.utcnow() - timedelta(days=keep_days * 4)).isoformat()

        with _transaction() as conn:
            # Normal captures: keep 7 days
            cursor = conn.execute("""
                DELETE FROM captures
                WHERE captured_at < ?
                AND promoted = 0
                AND was_empty = 0 AND had_ansi = 0 AND had_echo = 0
                AND user_reacted IS NULL
            """, (cutoff_normal,))
            normal_deleted = cursor.rowcount

            # Failure captures: keep 28 days
            cursor = conn.execute("""
                DELETE FROM captures
                WHERE captured_at < ?
                AND promoted = 0
            """, (cutoff_failures,))
            failure_deleted = cursor.rowcount

        if normal_deleted or failure_deleted:
            logger.info(f"Parser capture cleanup: {normal_deleted} normal, {failure_deleted} failure deleted")

        return normal_deleted, failure_deleted

    def get_capture_stats(self, hours: int = 24) -> dict:
        """Get capture statistics for the last N hours."""
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        conn = _get_connection()

        total = conn.execute(
            "SELECT COUNT(*) as c FROM captures WHERE captured_at > ?", (cutoff,)
        ).fetchone()['c']

        empty = conn.execute(
            "SELECT COUNT(*) as c FROM captures WHERE captured_at > ? AND was_empty = 1",
            (cutoff,)
        ).fetchone()['c']

        ansi = conn.execute(
            "SELECT COUNT(*) as c FROM captures WHERE captured_at > ? AND had_ansi = 1",
            (cutoff,)
        ).fetchone()['c']

        echo = conn.execute(
            "SELECT COUNT(*) as c FROM captures WHERE captured_at > ? AND had_echo = 1",
            (cutoff,)
        ).fetchone()['c']

        reacted = conn.execute(
            "SELECT COUNT(*) as c FROM captures WHERE captured_at > ? AND user_reacted IS NOT NULL",
            (cutoff,)
        ).fetchone()['c']

        promoted = conn.execute(
            "SELECT COUNT(*) as c FROM captures WHERE captured_at > ? AND promoted = 1",
            (cutoff,)
        ).fetchone()['c']

        failures = empty + ansi + echo + reacted

        return {
            'total': total,
            'failures': failures,
            'empty': empty,
            'ansi': ansi,
            'echo': echo,
            'reacted': reacted,
            'promoted': promoted,
            'failure_rate': failures / total if total > 0 else 0
        }

    def _detect_echo(self, screen_before: str | None, pipeline_output: str | None) -> bool:
        """Detect if instruction text leaked into output.

        Expanded detection to catch more leakage scenarios:
        - More lines searched (15 instead of 5)
        - Lower character threshold (10 instead of 15)
        - More prompt markers supported
        - Fuzzy matching with normalized whitespace
        - Internal artifact pattern detection
        """
        if not screen_before or not pipeline_output:
            return False

        # Check for common artifact patterns that indicate leakage
        # This is the primary detection method - keep comprehensive
        artifact_patterns = [
            # Instruction echo (THE #1 issue - 63/75 captures)
            'Current Message section',
            'Message section.',
            'Answer:',

            # JSON API response fragments
            '"message_id":',
            '"event_id":',
            '"session_id":',
            '"deleted_id":',
            '"set_number":',

            # Command chain fragments
            '|| echo',
            '&& curl',
            '; curl',

            # Python one-liners
            'import sys,json',
            'json.load(sys.stdin)',
            'd.get(',
            'python3 -c',

            # Internal paths
            '.claude/projects/',
            '/home/chris_hadley/',
            '.jsonl',
            'peterbot/*.jsonl',

            # Status indicators (spinners, thinking)
            '✽ Sketching',
            '✽ Concocting',
            '✽ Thinking',
            'Sketching (',      # Without spinner char
            'Concocting (',
            'Thinking (',
            'tokens · thinking',
            '↓ 1.7k tokens',
            '↓ ',  # Token arrow (general)
            '↑ ',

            # Truncated API paths
            'pi/inventory/',
            'hb/inventory/',
            'api/inventory/',

            # Curl artifacts
            '" \\',              # Line continuations
            '-H "Content-Type:',
            'application/json" -d',

            # Partial UUIDs (common pattern)
            '-f80cb',
            'cefd"',

            # API error/status fragments
            'Endpoint not f',
            'Unauthorized',
            'invalid_scope',
        ]
        for pattern in artifact_patterns:
            if pattern in pipeline_output:
                return True

        # Extract the last user instruction from screen_before
        lines = screen_before.strip().split('\n')
        if len(lines) < 2:
            return False

        # Extended prompt markers (various shell styles)
        prompt_markers = ('>', '❯', '$', '#', '→', '%', '»', '›', '⟩')

        # Look for lines that look like user input (check last 15 lines)
        user_lines = []
        for line in lines[-15:]:
            stripped = line.strip()
            # Check if line starts with any prompt marker
            for marker in prompt_markers:
                if stripped.startswith(marker):
                    content = stripped.lstrip(''.join(prompt_markers) + ' ').strip()
                    if len(content) > 10:  # Lower threshold (was 15)
                        user_lines.append(content)
                    break

        # Check if any user input appears in the pipeline output
        # Use both exact and normalized whitespace matching
        output_normalized = ' '.join(pipeline_output.split())
        for user_line in user_lines:
            # Exact match
            if user_line in pipeline_output:
                return True
            # Normalized whitespace match
            user_normalized = ' '.join(user_line.split())
            if len(user_normalized) > 20 and user_normalized in output_normalized:
                return True

        return False


# Module-level singleton
_store: Optional[ParserCaptureStore] = None


def get_parser_capture_store() -> ParserCaptureStore:
    """Get the singleton parser capture store."""
    global _store
    if _store is None:
        _store = ParserCaptureStore()
    return _store


def close() -> None:
    """Close the database connection."""
    global _connection, _store
    if _connection:
        _connection.close()
        _connection = None
        _store = None
        logger.debug("Parser capture store connection closed")
