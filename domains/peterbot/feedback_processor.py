"""Feedback Processor - Phase 6: Human feedback loop.

Collects human feedback throughout the day via:
1. Discord reactions (zero-effort)
2. Thread replies (low-effort, high-value)
3. Slash command /parser-feedback
4. Natural language detection

Feedback is weighted 3x vs automated signals in improvement cycles.

Based on SELF_IMPROVING_PARSER.md Phase 6.
"""

import json
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from logger import logger


# Database path (shared with parser_fixtures.db)
DB_PATH = Path("data/parser_fixtures.db")


@dataclass
class FeedbackEntry:
    """A feedback entry from any input method."""
    id: str
    input_method: str
    category: str
    skill_name: Optional[str]
    description: Optional[str]
    discord_msg_id: Optional[str]
    capture_id: Optional[str]
    priority: str
    created_at: str


# Category detection from reaction emoji
REACTION_CATEGORIES = {
    '🔧': 'parser_issue',
    '📋': 'format_drift',
    '❌': 'content_wrong',
    '🗑️': 'false_positive',
    '👎': 'general',
    '⚠️': 'parser_issue',
}

# Natural language intent patterns
INTENT_PATTERNS = {
    'parser_issue': [
        r'(?:ansi|escape|garbled|mangled|broken.*output|parser)',
        r'(?:echo|instruction.*showing|my.*question.*appeared)',
        r'(?:empty.*response|blank.*message|nothing.*sent)',
    ],
    'format_drift': [
        r'(?:missing.*section|should.*(?:have|include)|used to)',
        r'(?:format.*(?:wrong|changed|different|broken))',
        r'(?:order.*(?:wrong|changed)|sections.*(?:moved|swapped))',
    ],
    'content_wrong': [
        r'(?:wrong|incorrect|inaccurate|not right)',
        r'(?:stale|outdated|old data|yesterday)',
        r'(?:should.*(?:be|say)|that.*(?:was|is)n.t)',
    ],
    'prompt_issue': [
        r'(?:prompt|instruction|skill.*(?:needs|should))',
        r'(?:tone|style|approach).*(?:wrong|different|change)',
    ],
}

# Natural language feedback triggers
FEEDBACK_TRIGGERS = [
    r'(?:that|this|last)\s+(?:was|is)\s+(?:wrong|broken|bad|off)',
    r'missing\s+(?:the\s+)?(?:\w+\s+)?section',
    r'(?:format|formatting)\s+(?:is\s+)?(?:wrong|broken|changed)',
    r'used\s+to\s+(?:show|have|include|display)',
    r'(?:fix|broken|issue\s+with)\s+(?:the\s+)?(?:parser|output|response)',
    r'(?:should\s+have|should\s+include|supposed\s+to)',
    r'(?:echo|instruction)\s+(?:text|showing|leaked)',
]

# Skill name detection
SKILL_KEYWORDS = {
    'morning-briefing': ['briefing', 'morning brief', 'morning report'],
    'school-run': ['school run', 'school report', 'departure'],
    'health-digest': ['health digest', 'health report', 'health summary'],
    'news': ['news', 'news digest', 'headlines'],
    'email-summary': ['email', 'email summary', 'inbox'],
    'hb-daily-activity': ['sales', 'daily sales', 'hb sales', 'revenue'],
    'balance-monitor': ['balance', 'bank', 'accounts'],
    'weekly-health': ['weekly health', 'weekly report'],
    'monthly-health': ['monthly health', 'monthly report'],
}


class FeedbackProcessor:
    """Manages the feedback loop between human input and improvement cycles."""

    def __init__(self, db_path: str = None):
        self.db_path = Path(db_path) if db_path else DB_PATH

    def record_reaction(
        self,
        discord_msg_id: str,
        user_id: str,
        emoji: str,
        channel_id: str,
        channel_name: str
    ) -> Optional[str]:
        """Record feedback from a reaction on Peter's message."""
        category = REACTION_CATEGORIES.get(emoji)
        if not category:
            return None

        # Look up the capture for this message
        capture_id = self._find_capture(discord_msg_id)

        feedback_id = self._store(
            input_method='reaction',
            channel_id=channel_id,
            channel_name=channel_name,
            user_id=user_id,
            discord_msg_id=discord_msg_id,
            capture_id=capture_id,
            category=category,
            reaction_emoji=emoji,
        )
        return feedback_id

    def record_thread_reply(self, feedback_id: str, description: str):
        """Add a thread reply description to an existing reaction feedback."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    "UPDATE feedback SET description = ?, input_method = 'thread_reply' WHERE id = ?",
                    (description, feedback_id)
                )
            logger.debug(f"Added thread reply to feedback {feedback_id[:8]}")
        except Exception as e:
            logger.warning(f"Failed to record thread reply: {e}")

    def record_slash_command(
        self,
        user_id: str,
        channel_id: str,
        channel_name: str,
        message: str,
        category: str = 'general',
        skill_name: Optional[str] = None,
        priority: str = 'normal'
    ) -> str:
        """Record feedback from /parser-feedback command."""
        return self._store(
            input_method='slash_command',
            channel_id=channel_id,
            channel_name=channel_name,
            user_id=user_id,
            category=category,
            skill_name=skill_name,
            description=message,
            priority=priority,
        )

    def record_natural_language(
        self,
        user_id: str,
        channel_id: str,
        channel_name: str,
        message: str,
        referenced_msg_id: Optional[str] = None
    ) -> str:
        """Record feedback from natural language detection."""
        category = self._detect_category(message)
        skill_name = self._detect_skill(message)
        capture_id = self._find_capture(referenced_msg_id) if referenced_msg_id else None

        return self._store(
            input_method='natural_language',
            channel_id=channel_id,
            channel_name=channel_name,
            user_id=user_id,
            discord_msg_id=referenced_msg_id,
            capture_id=capture_id,
            category=category,
            skill_name=skill_name,
            description=message,
        )

    def get_pending(self) -> list[FeedbackEntry]:
        """Get all pending feedback for the next improvement cycle."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT id, input_method, category, skill_name, description,
                           discord_msg_id, capture_id, priority, created_at
                    FROM feedback
                    WHERE status = 'pending'
                    ORDER BY
                        CASE priority WHEN 'high' THEN 0 ELSE 1 END,
                        created_at ASC
                """).fetchall()
            return [FeedbackEntry(**dict(r)) for r in rows]
        except Exception as e:
            logger.warning(f"Failed to get pending feedback: {e}")
            return []

    def get_pending_summary(self) -> dict:
        """Get summary stats for pending feedback."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row

                total = conn.execute(
                    "SELECT COUNT(*) as c FROM feedback WHERE status = 'pending'"
                ).fetchone()['c']

                by_category = {}
                rows = conn.execute("""
                    SELECT category, COUNT(*) as c FROM feedback
                    WHERE status = 'pending' GROUP BY category
                """).fetchall()
                for r in rows:
                    by_category[r['category']] = r['c']

                by_skill = {}
                rows = conn.execute("""
                    SELECT skill_name, COUNT(*) as c FROM feedback
                    WHERE status = 'pending' AND skill_name IS NOT NULL
                    GROUP BY skill_name
                """).fetchall()
                for r in rows:
                    by_skill[r['skill_name']] = r['c']

                high_priority = conn.execute(
                    "SELECT COUNT(*) as c FROM feedback WHERE status = 'pending' AND priority = 'high'"
                ).fetchone()['c']

            return {
                'total': total,
                'by_category': by_category,
                'by_skill': by_skill,
                'high_priority': high_priority,
            }
        except Exception as e:
            logger.warning(f"Failed to get feedback summary: {e}")
            return {'total': 0, 'by_category': {}, 'by_skill': {}, 'high_priority': 0}

    def mark_consumed(self, feedback_ids: list[str], cycle_id: str):
        """Mark feedback as consumed by an improvement cycle."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                for fid in feedback_ids:
                    conn.execute("""
                        UPDATE feedback SET
                            status = 'processing',
                            consumed_by_cycle = ?
                        WHERE id = ?
                    """, (cycle_id, fid))
                conn.commit()
            logger.debug(f"Marked {len(feedback_ids)} feedback items as consumed")
        except Exception as e:
            logger.warning(f"Failed to mark feedback consumed: {e}")

    def resolve(
        self,
        feedback_id: str,
        resolution: str,
        status: str = 'resolved'
    ):
        """Mark feedback as resolved with an explanation."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute("""
                    UPDATE feedback SET
                        status = ?,
                        resolution = ?,
                        resolved_at = ?
                    WHERE id = ?
                """, (status, resolution, datetime.utcnow().isoformat(), feedback_id))
            logger.debug(f"Resolved feedback {feedback_id[:8]}: {status}")
        except Exception as e:
            logger.warning(f"Failed to resolve feedback: {e}")

    def _detect_category(self, message: str) -> str:
        """Detect feedback category from natural language."""
        message_lower = message.lower()
        for category, patterns in INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, message_lower):
                    return category
        return 'general'

    def _detect_skill(self, message: str) -> Optional[str]:
        """Detect if feedback references a specific skill."""
        message_lower = message.lower()
        for skill, keywords in SKILL_KEYWORDS.items():
            if any(kw in message_lower for kw in keywords):
                return skill
        return None

    def _find_capture(self, discord_msg_id: Optional[str]) -> Optional[str]:
        """Find the capture record for a Discord message."""
        if not discord_msg_id:
            return None
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                row = conn.execute(
                    "SELECT id FROM captures WHERE discord_msg_id = ?",
                    (discord_msg_id,)
                ).fetchone()
            return row[0] if row else None
        except Exception:
            return None

    def _store(self, **kwargs) -> str:
        """Store a feedback entry."""
        feedback_id = secrets.token_hex(8)

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute("""
                    INSERT INTO feedback
                    (id, input_method, channel_id, channel_name, user_id,
                     discord_msg_id, capture_id, category, skill_name,
                     description, reaction_emoji, priority)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    feedback_id,
                    kwargs.get('input_method'),
                    kwargs.get('channel_id'),
                    kwargs.get('channel_name'),
                    kwargs.get('user_id'),
                    kwargs.get('discord_msg_id'),
                    kwargs.get('capture_id'),
                    kwargs.get('category', 'general'),
                    kwargs.get('skill_name'),
                    kwargs.get('description'),
                    kwargs.get('reaction_emoji'),
                    kwargs.get('priority', 'normal'),
                ))
            logger.debug(f"Stored feedback {feedback_id[:8]} [{kwargs.get('category')}]")
            return feedback_id
        except Exception as e:
            logger.warning(f"Failed to store feedback: {e}")
            return ""


def is_parser_feedback(message_text: str) -> bool:
    """Detect if a message is parser/output feedback."""
    text_lower = message_text.lower()
    return any(re.search(p, text_lower) for p in FEEDBACK_TRIGGERS)


# Singleton
_processor: FeedbackProcessor | None = None


def get_feedback_processor() -> FeedbackProcessor:
    """Get the singleton feedback processor."""
    global _processor
    if _processor is None:
        _processor = FeedbackProcessor()
    return _processor
