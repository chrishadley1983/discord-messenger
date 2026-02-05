"""Scheduled Output Scorer - Phase 4: Format drift detection.

Monitors recurring skill outputs (briefings, digests, reports) for consistency.
Detects when format drifts from established specifications.

Based on SELF_IMPROVING_PARSER.md Phase 4.
"""

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from logger import logger


# Database path (shared with parser_fixtures.db)
DB_PATH = Path("data/parser_fixtures.db")


@dataclass
class FormatScoreResult:
    """Result of scoring scheduled output against format spec."""
    overall: float
    section_presence: float        # Are all required sections present?
    section_order: float           # Are sections in the expected order?
    indicator_presence: float      # Are expected emoji/markers present?
    length_compliance: float       # Within min/max length bounds?
    pattern_compliance: float      # Do expected patterns match?
    structural_similarity: float   # How similar to golden examples?
    drift_details: list[str]       # Human-readable list of what drifted

    @property
    def drifted(self) -> bool:
        return self.overall < 0.85  # Default threshold

    def to_dict(self) -> dict:
        return {
            'overall': self.overall,
            'section_presence': self.section_presence,
            'section_order': self.section_order,
            'indicator_presence': self.indicator_presence,
            'length_compliance': self.length_compliance,
            'pattern_compliance': self.pattern_compliance,
            'structural_similarity': self.structural_similarity,
            'drift_details': self.drift_details,
            'drifted': self.drifted,
        }


# Section detection heuristics
SECTION_SIGNALS = {
    'weather':       ['🌡️', '°c', '°f', 'temperature', 'rain', 'sunny', 'cloudy', 'weather'],
    'traffic':       ['🚗', 'traffic', 'minutes', 'route', 'congestion', 'a21', 'a26', 'm25'],
    'calendar':      ['📅', 'calendar', 'meeting', 'event', 'appointment', 'schedule'],
    'ev_status':     ['🔋', 'battery', 'charge', 'kia', 'ev', 'range', 'miles'],
    'ring_status':   ['🔔', 'ring', 'doorbell', 'motion', 'last seen'],
    'route':         ['route', 'via', 'direction', 'distance'],
    'departure_time':['⏰', 'leave by', 'depart', 'departure'],
    'steps':         ['steps', 'walked', 'step count'],
    'sleep':         ['sleep', 'slept', 'hours sleep', 'rem', 'deep sleep'],
    'weight':        ['weight', 'kg', 'lbs', 'body comp'],
    'hydration':     ['💧', 'water', 'hydration', 'ml', 'glasses'],
    'heart_rate':    ['❤️', 'heart rate', 'bpm', 'resting hr'],
    'headlines':     ['headline', 'news', 'top stories'],
    'summaries':     ['summary', 'key points', 'highlights'],
    'unread_count':  ['unread', 'new emails', 'inbox'],
    'priority_emails':['priority', 'important', 'urgent', 'flagged'],
    'action_items':  ['action', 'todo', 'follow up', 'respond'],
    'sales_count':   ['sales', 'orders', 'sold'],
    'revenue':       ['revenue', '£', 'total', 'earnings'],
    'top_items':     ['top items', 'best sellers', 'popular'],
    'account_balances':['balance', 'account', '£'],
    'changes':       ['change', 'movement', 'difference', 'vs'],
    'week_summary':  ['this week', 'weekly', 'past 7'],
    'month_summary': ['this month', 'monthly', 'past 30'],
    'trends':        ['📈', '📉', 'trend', 'trending', 'compared to'],
    'goals_progress':['goal', 'target', 'progress', '%'],
    'achievements':  ['🏆', 'achievement', 'personal best', 'pb', 'milestone'],
    'recommendations':['recommend', 'suggestion', 'consider', 'try'],
}


class ScheduledOutputScorer:
    """Scores scheduled skill outputs against format specifications."""

    def __init__(self, db_path: str = None):
        self.db_path = Path(db_path) if db_path else DB_PATH

    def get_spec(self, skill_name: str) -> Optional[dict]:
        """Get format spec for a skill."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM scheduled_output_specs WHERE skill_name = ?",
                    (skill_name,)
                ).fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.warning(f"Failed to get spec for {skill_name}: {e}")
            return None

    def score(self, output: str, spec: dict) -> FormatScoreResult:
        """Score scheduled output against format spec."""
        details = []

        # 1. Section presence
        required = json.loads(spec.get('required_sections', '[]'))
        sections_found = self._detect_sections(output, required)
        section_presence = len(sections_found) / len(required) if required else 1.0
        missing = [s for s in required if s not in sections_found]
        if missing:
            details.append(f"Missing sections: {', '.join(missing)}")

        # 2. Section order
        if spec.get('section_order'):
            expected_order = json.loads(spec['section_order'])
            found_order = [s for s in expected_order if s in sections_found]
            section_order = self._order_score(expected_order, found_order)
            if section_order < 1.0:
                details.append(f"Section order drift")
        else:
            section_order = 1.0

        # 3. Indicator presence
        indicators = json.loads(spec.get('required_indicators', '[]'))
        if indicators:
            found_indicators = [i for i in indicators if i in output]
            indicator_presence = len(found_indicators) / len(indicators)
            missing_ind = [i for i in indicators if i not in output]
            if missing_ind:
                details.append(f"Missing indicators: {' '.join(missing_ind)}")
        else:
            indicator_presence = 1.0

        # 4. Length compliance
        min_len = spec.get('min_length', 100)
        max_len = spec.get('max_length', 3000)
        output_len = len(output)

        if min_len <= output_len <= max_len:
            length_compliance = 1.0
        elif output_len < min_len:
            length_compliance = max(0.0, output_len / min_len)
            details.append(f"Output too short ({output_len} chars, min {min_len})")
        else:
            length_compliance = max(0.0, 1.0 - (output_len - max_len) / max_len)
            details.append(f"Output too long ({output_len} chars, max {max_len})")

        # 5. Pattern compliance
        expected_patterns = json.loads(spec.get('expected_patterns', '[]'))
        forbidden_patterns = json.loads(spec.get('forbidden_patterns', '[]'))
        pattern_hits = 0
        pattern_total = len(expected_patterns) + len(forbidden_patterns)

        for pat in expected_patterns:
            if re.search(pat, output):
                pattern_hits += 1
            else:
                details.append(f"Expected pattern not found: {pat[:50]}")

        for pat in forbidden_patterns:
            if not re.search(pat, output):
                pattern_hits += 1
            else:
                details.append(f"Forbidden pattern found: {pat[:50]}")

        pattern_compliance = pattern_hits / pattern_total if pattern_total else 1.0

        # 6. Structural similarity to golden examples
        golden = json.loads(spec.get('golden_examples', '[]'))
        if golden:
            similarities = [
                self._structural_similarity(output, example)
                for example in golden
            ]
            structural_similarity = max(similarities) if similarities else 1.0
            if structural_similarity < 0.6:
                details.append(f"Low structural similarity ({structural_similarity:.2f})")
        else:
            structural_similarity = 1.0

        # Weighted overall
        overall = (
            section_presence * 0.25 +
            section_order * 0.10 +
            indicator_presence * 0.15 +
            length_compliance * 0.10 +
            pattern_compliance * 0.15 +
            structural_similarity * 0.25
        )

        return FormatScoreResult(
            overall=overall,
            section_presence=section_presence,
            section_order=section_order,
            indicator_presence=indicator_presence,
            length_compliance=length_compliance,
            pattern_compliance=pattern_compliance,
            structural_similarity=structural_similarity,
            drift_details=details,
        )

    def store_history(
        self,
        skill_name: str,
        channel_id: str,
        output_text: str,
        format_score: float,
        section_scores: FormatScoreResult,
        drift_detected: bool,
        drift_details: list[str],
    ) -> str:
        """Store scheduled output history."""
        import secrets
        history_id = secrets.token_hex(8)

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute("""
                    INSERT INTO scheduled_output_history
                    (id, skill_name, channel_id, output_text, format_score,
                     section_scores, drift_detected, drift_details)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    history_id,
                    skill_name,
                    channel_id,
                    output_text,
                    format_score,
                    json.dumps(section_scores.to_dict()),
                    drift_detected,
                    json.dumps(drift_details),
                ))
            return history_id
        except Exception as e:
            logger.warning(f"Failed to store output history: {e}")
            return ""

    def get_drift_alerts(self, hours: int = 24) -> list[dict]:
        """Get drift alerts from the last N hours."""
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT * FROM scheduled_output_history
                    WHERE captured_at > ? AND drift_detected = 1
                    ORDER BY captured_at DESC
                """, (cutoff,)).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"Failed to get drift alerts: {e}")
            return []

    def get_skill_health(self) -> list[dict]:
        """Get health summary for all scheduled skills with specs."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row

                # Get all specs
                specs = conn.execute(
                    "SELECT skill_name, display_name FROM scheduled_output_specs"
                ).fetchall()

                results = []
                for spec in specs:
                    skill_name = spec['skill_name']

                    # Get recent scores
                    recent = conn.execute("""
                        SELECT format_score, drift_detected
                        FROM scheduled_output_history
                        WHERE skill_name = ?
                        ORDER BY captured_at DESC
                        LIMIT 5
                    """, (skill_name,)).fetchall()

                    if recent:
                        avg_score = sum(r['format_score'] for r in recent) / len(recent)
                        drift_count = sum(1 for r in recent if r['drift_detected'])
                        status = 'healthy' if avg_score >= 0.85 else 'warning' if avg_score >= 0.70 else 'critical'
                    else:
                        avg_score = None
                        drift_count = 0
                        status = 'no_data'

                    results.append({
                        'skill_name': skill_name,
                        'display_name': spec['display_name'],
                        'avg_score': avg_score,
                        'drift_count': drift_count,
                        'status': status,
                    })

                return results
        except Exception as e:
            logger.warning(f"Failed to get skill health: {e}")
            return []

    def _detect_sections(self, output: str, required: list[str]) -> list[str]:
        """Detect which required sections are present."""
        found = []
        output_lower = output.lower()

        for section in required:
            signals = SECTION_SIGNALS.get(section, [section])
            matches = sum(1 for s in signals if s in output_lower)
            if matches >= 2 or (matches >= 1 and len(signals) <= 2):
                found.append(section)

        return found

    def _order_score(self, expected: list, actual: list) -> float:
        """Score how well the actual order matches expected order."""
        if not expected or not actual:
            return 1.0
        matcher = SequenceMatcher(None, expected, actual)
        return matcher.ratio()

    def _structural_similarity(self, output: str, golden: str) -> float:
        """Compare structural similarity (not content)."""
        def skeletonize(text: str) -> str:
            lines = text.strip().split('\n')
            skeleton_lines = []
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    skeleton_lines.append('[BLANK]')
                elif stripped.startswith('#'):
                    skeleton_lines.append('[HEADER]')
                elif stripped.startswith(('- ', '• ', '* ')):
                    skeleton_lines.append('[BULLET]')
                elif stripped.startswith(('1.', '2.', '3.', '4.', '5.')):
                    skeleton_lines.append('[NUMBERED]')
                elif '|' in stripped and stripped.count('|') >= 2:
                    skeleton_lines.append('[TABLE_ROW]')
                elif any(e in stripped for e in ['✅', '❌', '⚠️', '🔋', '🌡️', '📅', '🚗']):
                    skeleton_lines.append('[INDICATOR_LINE]')
                elif stripped.startswith('```'):
                    skeleton_lines.append('[CODE_FENCE]')
                elif len(stripped) < 40 and stripped.endswith(':'):
                    skeleton_lines.append('[LABEL]')
                else:
                    skeleton_lines.append('[TEXT]')
            return '\n'.join(skeleton_lines)

        skel_output = skeletonize(output)
        skel_golden = skeletonize(golden)
        return SequenceMatcher(None, skel_output, skel_golden).ratio()


# Singleton
_scorer: ScheduledOutputScorer | None = None


def get_scheduled_output_scorer() -> ScheduledOutputScorer:
    """Get the singleton scheduled output scorer."""
    global _scorer
    if _scorer is None:
        _scorer = ScheduledOutputScorer()
    return _scorer


def create_format_spec(
    skill_name: str,
    display_name: str,
    required_sections: list[str],
    required_indicators: list[str] = None,
    section_order: list[str] = None,
    min_length: int = 100,
    max_length: int = 3000,
    expected_patterns: list[str] = None,
    golden_examples: list[str] = None,
) -> str:
    """Create a format spec for a skill.

    Returns the spec ID.
    """
    import secrets
    spec_id = secrets.token_hex(8)

    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO scheduled_output_specs
                (id, skill_name, display_name, required_sections, section_order,
                 required_indicators, min_length, max_length, expected_patterns, golden_examples)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                spec_id,
                skill_name,
                display_name,
                json.dumps(required_sections),
                json.dumps(section_order or []),
                json.dumps(required_indicators or []),
                min_length,
                max_length,
                json.dumps(expected_patterns or []),
                json.dumps(golden_examples or []),
            ))
        logger.info(f"Created format spec for {skill_name}")
        return spec_id
    except Exception as e:
        logger.error(f"Failed to create format spec: {e}")
        return ""
