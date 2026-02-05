"""Parser Improver - Phase 3: Self-improving agent loop.

Runs as a scheduled job to analyze failures, propose targeted changes,
validate via regression, and commit or rollback.

Based on SELF_IMPROVING_PARSER.md Phase 3.

CLI Usage:
    # Run full improvement cycle
    python -m domains.peterbot.parser_improver run

    # Run review phase only (no changes)
    python -m domains.peterbot.parser_improver review

    # Check human review status
    python -m domains.peterbot.parser_improver status
"""

import argparse
import json
import os
import re
import secrets
import sqlite3
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import Optional

import httpx

from logger import logger

# Hadley API base URL for task creation
HADLEY_API_URL = os.getenv("HADLEY_API_URL", "http://localhost:8100")

# Database path
DB_PATH = Path("data/parser_fixtures.db")

# Maximum cycles before human review required
MAX_CYCLES_WITHOUT_REVIEW = 5

# Maximum diff size (lines)
MAX_DIFF_LINES = 100


@dataclass
class ReviewReport:
    """Analysis of recent captures, fixtures, and feedback."""
    capture_total_24h: int = 0
    capture_failures: int = 0
    failure_breakdown: dict = field(default_factory=dict)

    fixture_total: int = 0
    fixture_pass_rate: float = 0.0
    worst_category: Optional[str] = None
    worst_dimension: Optional[str] = None
    chronic_failures: list = field(default_factory=list)

    feedback_pending: int = 0
    feedback_by_category: dict = field(default_factory=dict)
    high_priority_feedback: list = field(default_factory=list)

    recommended_target: Optional[str] = None
    target_rationale: str = ""
    affected_fixtures: list = field(default_factory=list)
    example_failure: Optional[dict] = None

    # Leakage audit results
    leakage_audit: Optional[LeakageAuditResult] = None

    def to_dict(self) -> dict:
        result = {
            'capture_summary': {
                'total_24h': self.capture_total_24h,
                'failures': self.capture_failures,
                'failure_rate': self.capture_failures / self.capture_total_24h if self.capture_total_24h else 0,
                'failure_breakdown': self.failure_breakdown,
            },
            'fixture_summary': {
                'total': self.fixture_total,
                'pass_rate': self.fixture_pass_rate,
                'worst_category': self.worst_category,
                'worst_dimension': self.worst_dimension,
                'chronic_failures': self.chronic_failures[:5],
            },
            'feedback_summary': {
                'pending': self.feedback_pending,
                'by_category': self.feedback_by_category,
                'high_priority': self.high_priority_feedback[:3],
            },
            'recommended_target': {
                'stage': self.recommended_target,
                'rationale': self.target_rationale,
                'affected_fixtures': self.affected_fixtures[:10],
                'example_failure': self.example_failure,
            }
        }
        if self.leakage_audit:
            result['leakage_audit'] = self.leakage_audit.to_dict()
        return result


@dataclass
class ChangePlan:
    """A concrete, scoped change proposal."""
    target_stage: str
    target_file: str
    target_function: str
    problem_statement: str
    proposed_approach: str
    affected_fixtures: list
    risk_assessment: str
    estimated_diff_lines: int

    def to_dict(self) -> dict:
        return {
            'target_stage': self.target_stage,
            'target_file': self.target_file,
            'target_function': self.target_function,
            'problem_statement': self.problem_statement,
            'proposed_approach': self.proposed_approach,
            'affected_fixtures': self.affected_fixtures,
            'risk_assessment': self.risk_assessment,
            'estimated_diff_lines': self.estimated_diff_lines,
        }


@dataclass
class CycleResult:
    """Result of an improvement cycle."""
    cycle_id: str
    started_at: str
    completed_at: Optional[str] = None
    target_stage: Optional[str] = None
    committed: bool = False
    rollback_reason: Optional[str] = None
    score_before: Optional[float] = None
    score_after: Optional[float] = None
    fixtures_improved: int = 0
    regressions: int = 0
    review_required: bool = False
    task_id: Optional[str] = None  # Task created for fixing leakage gaps


# Parser stages that can be targeted
PARSER_STAGES = {
    'strip_ansi': {
        'file': 'domains/peterbot/parser.py',
        'function': 'strip_ansi',
        'description': 'ANSI escape sequence removal',
        'dimension': 'ansi_cleanliness',
    },
    'extract_response': {
        'file': 'domains/peterbot/parser.py',
        'function': 'extract_new_response',
        'description': 'Screen diff extraction',
        'dimension': 'content_preservation',
    },
    'remove_echo': {
        'file': 'domains/peterbot/parser.py',
        'function': 'remove_echo',
        'description': 'Instruction echo removal',
        'dimension': 'echo_removal',
    },
    'dedupe_lines': {
        'file': 'domains/peterbot/parser.py',
        'function': 'dedupe_lines',
        'description': 'Duplicate line removal',
        'dimension': 'noise_removal',
    },
    'trim_whitespace': {
        'file': 'domains/peterbot/parser.py',
        'function': 'trim_whitespace',
        'description': 'Whitespace normalization',
        'dimension': 'format_integrity',
    },
}


# =============================================================================
# LEAKAGE AUDITOR - Comprehensive pattern scan
# =============================================================================

# All known leak patterns for comprehensive scanning
LEAK_PATTERNS = {
    # Instruction/Context (highest frequency)
    'instruction_current_msg': (r'Current Message section', 'Instruction echo'),
    'instruction_answer': (r'^Answer:', 'Answer prefix'),
    'context_memory': (r'Memory Context|Relevant Knowledge', 'Memory context marker'),

    # JSON structures
    'json_message_id': (r'"message_id":', 'JSON message_id'),
    'json_event_id': (r'"event_id":', 'JSON event_id'),
    'json_session_id': (r'"session_id":', 'JSON session_id'),
    'json_generic_id': (r'"[a-z]+_id":', 'JSON generic ID'),
    'json_key_string': (r'"[a-z_]+"\s*:\s*"[^"]*"', 'JSON key:string'),
    'json_key_number': (r'"[a-z_]+"\s*:\s*\d+', 'JSON key:number'),
    'json_key_bool': (r'"[a-z_]+"\s*:\s*(?:true|false|null)', 'JSON key:bool/null'),
    'json_open_brace': (r'^\s*\{\s*$', 'Standalone {'),
    'json_close_brace': (r'^\s*\}\s*$', 'Standalone }'),

    # Claude Code UI
    'cc_spinner_star': (r'[\u273b\u273d]', 'Star spinner'),
    'cc_thinking_time': (r'(?:Sketching|Thinking|Working|Concocting).*\d+s', 'Thinking with time'),
    'cc_tokens_count': (r'\d+\.?\d*k?\s*tokens', 'Token count'),
    'cc_token_arrow': (r'[\u2193\u2191]\s*\d+', 'Token arrow'),
    'cc_tool_marker': (r'[\u23bf\u251c\u2514]\s*(?:Read|Write|Edit|Bash)', 'Tool marker'),

    # Paths
    'path_home_chris': (r'/home/chris_hadley/', '/home/chris_hadley/'),
    'path_claude_projects': (r'\.claude/projects/', '.claude/projects/'),
    'path_jsonl': (r'\.jsonl', '.jsonl reference'),
    'path_peterbot': (r'peterbot/', 'peterbot/ path'),

    # Commands
    'cmd_pipe_echo': (r'\|\|\s*echo', 'Pipe echo'),
    'cmd_and_curl': (r'&&\s*curl', 'And curl'),
    'cmd_import_sys': (r'import\s+sys', 'import sys'),
    'cmd_json_load': (r'json\.load\(', 'json.load()'),
    'cmd_head_tail': (r'(?:head|tail)\s+-\d+', 'head/tail command'),
    'cmd_line_cont': (r'"\s*\\$', 'Line continuation'),

    # API/URLs
    'api_localhost': (r'localhost:\d+', 'Localhost URL'),
    'api_172': (r'172\.\d+\.\d+\.\d+:\d+', '172.x.x.x URL'),
    'api_path_pi': (r'pi/\w+/', 'pi/ API path'),
    'api_path_hb': (r'hb/\w+/', 'hb/ API path'),
    'api_uuid_full': (r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', 'Full UUID'),
    'api_content_type': (r'Content-Type:\s*application/json', 'Content-Type header'),
    'api_data_d': (r"-d\s*'?\{", 'Curl -d data'),

    # Errors
    'error_unauthorized': (r'Unauthorized', 'Unauthorized error'),
    'error_traceback': (r'Traceback \(most recent', 'Python traceback'),
    'error_invalid_scope': (r'invalid_scope', 'OAuth scope error'),

    # Misc
    'artifact_task_output': (r'^Task Output\s+[a-z0-9]+', 'Task Output ID'),
}


@dataclass
class LeakageAuditResult:
    """Result of comprehensive leakage audit."""
    total_captures: int = 0
    captures_with_leakage: int = 0
    leakage_rate: float = 0.0
    patterns_found: dict = field(default_factory=dict)  # pattern_name -> count
    undetected_by_pattern: dict = field(default_factory=dict)  # pattern_name -> undetected_count
    samples: dict = field(default_factory=dict)  # pattern_name -> sample text
    top_undetected: list = field(default_factory=list)  # [(pattern_name, count, sample), ...]

    def to_dict(self) -> dict:
        return {
            'total_captures': self.total_captures,
            'captures_with_leakage': self.captures_with_leakage,
            'leakage_rate': self.leakage_rate,
            'detection_gap': len([p for p, c in self.undetected_by_pattern.items() if c > 0]),
            'top_undetected': self.top_undetected[:10],
        }


class LeakageAuditor:
    """Comprehensive leakage pattern auditor.

    Scans ALL captures (not just flagged ones) to find patterns that
    slip through the current detection logic.
    """

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH

    def audit(self, hours: int = 24) -> LeakageAuditResult:
        """Run comprehensive leakage audit on recent captures.

        Args:
            hours: How many hours of captures to analyze

        Returns:
            LeakageAuditResult with findings
        """
        result = LeakageAuditResult()

        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row

            cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()

            captures = conn.execute('''
                SELECT id, pipeline_output, had_ansi, had_echo
                FROM captures
                WHERE captured_at > ?
                ORDER BY captured_at DESC
            ''', (cutoff,)).fetchall()

            conn.close()

            result.total_captures = len(captures)
            if result.total_captures == 0:
                return result

            patterns_found = Counter()
            undetected_by_pattern = Counter()
            samples = {}

            for c in captures:
                output = c['pipeline_output'] or ''
                was_detected = c['had_echo'] or c['had_ansi']
                capture_has_leak = False

                for pattern_name, (pattern, desc) in LEAK_PATTERNS.items():
                    try:
                        if re.search(pattern, output, re.MULTILINE | re.IGNORECASE):
                            patterns_found[pattern_name] += 1
                            capture_has_leak = True

                            if not was_detected:
                                undetected_by_pattern[pattern_name] += 1

                            # Store sample if we don't have one
                            if pattern_name not in samples:
                                match = re.search(pattern, output, re.MULTILINE | re.IGNORECASE)
                                if match:
                                    start = max(0, match.start() - 10)
                                    end = min(len(output), match.end() + 40)
                                    samples[pattern_name] = output[start:end].replace('\n', '\\n')[:80]
                    except Exception:
                        pass

                if capture_has_leak:
                    result.captures_with_leakage += 1

            result.leakage_rate = result.captures_with_leakage / result.total_captures
            result.patterns_found = dict(patterns_found)
            result.undetected_by_pattern = dict(undetected_by_pattern)
            result.samples = samples

            # Build top undetected list
            result.top_undetected = [
                {
                    'pattern': name,
                    'count': count,
                    'description': LEAK_PATTERNS[name][1],
                    'sample': samples.get(name, '')[:60],
                }
                for name, count in sorted(
                    undetected_by_pattern.items(),
                    key=lambda x: -x[1]
                )[:10]
                if count > 0
            ]

        except Exception as e:
            logger.error(f"Leakage audit failed: {e}")

        return result

    def format_report(self, result: LeakageAuditResult) -> str:
        """Format audit result for Discord."""
        lines = []
        lines.append("**Leakage Audit**")
        lines.append(f"• {result.total_captures} captures analyzed")
        lines.append(f"• {result.captures_with_leakage} with leakage ({result.leakage_rate:.0%})")

        if result.top_undetected:
            lines.append("")
            lines.append("**Top Undetected Patterns:**")
            for item in result.top_undetected[:5]:
                lines.append(f"• `{item['pattern']}`: {item['count']} ({item['description']})")

        detection_gap = len([p for p, c in result.undetected_by_pattern.items() if c > 0])
        if detection_gap > 0:
            lines.append("")
            lines.append(f"⚠️ {detection_gap} pattern types slipping through detection")

        return "\n".join(lines)

    def create_fix_task(self, result: LeakageAuditResult) -> Optional[str]:
        """Create a to-do task with detailed fix plan.

        Args:
            result: Leakage audit result with findings

        Returns:
            Task ID if created, None otherwise
        """
        if not result.top_undetected:
            logger.info("No undetected patterns - no task needed")
            return None

        # Check for existing task from TODAY to avoid duplicates (but allow accumulation across days)
        today_str = datetime.now(UTC).strftime('%Y-%m-%d')
        try:
            response = httpx.get(
                f"{HADLEY_API_URL}/ptasks/",
                params={
                    "list_type": "peter_queue",
                    "limit": 50,
                },
                timeout=10.0,
                follow_redirects=True,
            )
            if response.status_code == 200:
                tasks = response.json().get("tasks", [])
                for task in tasks:
                    # Skip if there's already a leakage fix task from TODAY
                    if (task.get("created_by") == "parser_improver" and
                        "leakage" in task.get("title", "").lower() and
                        today_str in task.get("title", "") and
                        task.get("status") not in ("done", "cancelled")):
                        logger.info(f"Existing leakage fix task from today found: {task['id'][:8]} - skipping creation")
                        return task["id"]
        except Exception as e:
            logger.warning(f"Failed to check for existing tasks: {e}")

        # Build detailed description with fix plan
        desc_lines = [
            "## Leakage Detection Gaps Found",
            "",
            f"**Analysis Date:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')} UTC",
            f"**Captures Analyzed:** {result.total_captures}",
            f"**With Leakage:** {result.captures_with_leakage} ({result.leakage_rate:.0%})",
            f"**Detection Gap:** {len(result.top_undetected)} pattern types undetected",
            "",
            "---",
            "",
            "## Top Undetected Patterns",
            "",
        ]

        for item in result.top_undetected[:10]:
            desc_lines.append(f"### `{item['pattern']}` ({item['count']} occurrences)")
            desc_lines.append(f"- **Type:** {item['description']}")
            if item.get('sample'):
                safe_sample = item['sample'].replace('`', "'")
                desc_lines.append(f"- **Sample:** `{safe_sample}`")
            desc_lines.append("")

        desc_lines.extend([
            "---",
            "",
            "## Fix Plan",
            "",
            "### 1. Update Detection (`capture_parser.py`)",
            "Add these patterns to `_detect_echo()` artifact_patterns list:",
            "```python",
            "artifact_patterns = [",
            "    # ... existing patterns ...",
        ])

        # Generate suggested patterns
        for item in result.top_undetected[:5]:
            pattern_name = item['pattern']
            if pattern_name in LEAK_PATTERNS:
                regex = LEAK_PATTERNS[pattern_name][0]
                desc_lines.append(f"    '{regex}',  # {item['description']}")

        desc_lines.extend([
            "]",
            "```",
            "",
            "### 2. Update Sanitiser (`response/sanitiser.py`)",
            "Add corresponding patterns to `AGGRESSIVE_PATTERNS`:",
            "```python",
            "{",
            "    'name': '<pattern_name>',",
            "    'pattern': re.compile(r'<regex>'),",
            "    'replacement': '',",
            "    'description': '<description>'",
            "},",
            "```",
            "",
            "### 3. Add Regression Tests",
            "Add test cases to `tests/test_leakage_regression.py` for each new pattern.",
            "",
            "### 4. Verify",
            "```bash",
            "pytest tests/test_leakage_regression.py -v",
            "python scripts/analyze_all_captures.py",
            "```",
            "",
            "---",
            "",
            "## Files to Modify",
            "- `domains/peterbot/capture_parser.py` - Detection patterns",
            "- `domains/peterbot/response/sanitiser.py` - Cleaning patterns",
            "- `tests/test_leakage_regression.py` - Test cases",
        ])

        description = "\n".join(desc_lines)

        # Create task via API
        try:
            task_data = {
                "list_type": "peter_queue",
                "title": f"[{today_str}] Fix {len(result.top_undetected)} leakage detection gaps",
                "description": description,
                "priority": "high" if result.leakage_rate > 0.5 else "medium",
                "created_by": "parser_improver",
                "category_slugs": ["maintenance"],
            }

            response = httpx.post(
                f"{HADLEY_API_URL}/ptasks/",
                json=task_data,
                timeout=10.0,
                follow_redirects=True,
            )

            if response.status_code in (200, 201):
                task = response.json()
                task_id = task.get('id')
                logger.info(f"Created leakage fix task: {task_id}")
                return task_id
            else:
                logger.warning(f"Failed to create task: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Failed to create task: {e}")
            return None


class ParserImprover:
    """Self-improving parser agent loop."""

    def __init__(self, db_path: str = None):
        self.db_path = Path(db_path) if db_path else DB_PATH

    def review(self) -> ReviewReport:
        """
        Analyze recent captures, fixture failures, and human feedback.
        Returns a review report with recommended target.
        """
        report = ReviewReport()

        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row

            # 1. Capture summary (last 24h)
            cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat()

            capture_stats = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN was_empty = 1 THEN 1 ELSE 0 END) as empty,
                    SUM(CASE WHEN had_ansi = 1 THEN 1 ELSE 0 END) as ansi,
                    SUM(CASE WHEN had_echo = 1 THEN 1 ELSE 0 END) as echo,
                    SUM(CASE WHEN user_reacted IS NOT NULL THEN 1 ELSE 0 END) as reacted
                FROM captures
                WHERE captured_at > ?
            """, (cutoff,)).fetchone()

            report.capture_total_24h = capture_stats['total'] or 0
            report.failure_breakdown = {
                'was_empty': capture_stats['empty'] or 0,
                'had_ansi': capture_stats['ansi'] or 0,
                'had_echo': capture_stats['echo'] or 0,
                'user_reacted': capture_stats['reacted'] or 0,
            }
            report.capture_failures = sum(report.failure_breakdown.values())

            # 2. Fixture summary
            fixture_stats = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN last_pass = 1 THEN 1 ELSE 0 END) as passed
                FROM fixtures
            """).fetchone()

            report.fixture_total = fixture_stats['total'] or 0
            report.fixture_pass_rate = (
                fixture_stats['passed'] / fixture_stats['total']
                if fixture_stats['total'] else 0
            )

            # Find worst category
            worst_cat = conn.execute("""
                SELECT category,
                       COUNT(*) as total,
                       SUM(CASE WHEN last_pass = 0 THEN 1 ELSE 0 END) as failed
                FROM fixtures
                GROUP BY category
                HAVING failed > 0
                ORDER BY failed DESC
                LIMIT 1
            """).fetchone()
            if worst_cat:
                report.worst_category = worst_cat['category']

            # Chronic failures (failed 3+ times)
            chronic = conn.execute("""
                SELECT id, category, fail_count
                FROM fixtures
                WHERE fail_count >= 3
                ORDER BY fail_count DESC
                LIMIT 10
            """).fetchall()
            report.chronic_failures = [
                {'id': r['id'], 'category': r['category'], 'fail_count': r['fail_count']}
                for r in chronic
            ]

            # 3. Feedback summary
            feedback_stats = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN priority = 'high' THEN 1 ELSE 0 END) as high_priority
                FROM feedback
                WHERE status = 'pending'
            """).fetchone()
            report.feedback_pending = feedback_stats['total'] or 0

            feedback_by_cat = conn.execute("""
                SELECT category, COUNT(*) as count
                FROM feedback
                WHERE status = 'pending'
                GROUP BY category
            """).fetchall()
            report.feedback_by_category = {r['category']: r['count'] for r in feedback_by_cat}

            conn.close()

            # 4. Determine recommended target
            report.recommended_target, report.target_rationale = self._determine_target(report)

            # 5. Run comprehensive leakage audit
            auditor = LeakageAuditor(self.db_path)
            report.leakage_audit = auditor.audit(hours=24)
            logger.info(f"Leakage audit: {report.leakage_audit.captures_with_leakage}/{report.leakage_audit.total_captures} "
                       f"with leakage, {len(report.leakage_audit.top_undetected)} pattern types undetected")

        except Exception as e:
            logger.error(f"Review failed: {e}")

        return report

    def _determine_target(self, report: ReviewReport) -> tuple[Optional[str], str]:
        """Determine which parser stage to target based on review data."""
        scores = {}
        rationale_parts = []

        # Score each stage based on failure data
        # Higher score = more urgent to fix

        # ANSI issues
        ansi_issues = report.failure_breakdown.get('had_ansi', 0)
        if ansi_issues > 0:
            scores['strip_ansi'] = ansi_issues * 10
            rationale_parts.append(f"{ansi_issues} captures had ANSI leakage")

        # Echo issues
        echo_issues = report.failure_breakdown.get('had_echo', 0)
        if echo_issues > 0:
            scores['remove_echo'] = echo_issues * 10
            rationale_parts.append(f"{echo_issues} captures had echo leakage")

        # Empty responses (likely extraction issue)
        empty_issues = report.failure_breakdown.get('was_empty', 0)
        if empty_issues > 2:
            scores['extract_response'] = empty_issues * 5
            rationale_parts.append(f"{empty_issues} empty responses")

        # Feedback weighting (3x multiplier for human feedback)
        for category, count in report.feedback_by_category.items():
            if category == 'parser_issue':
                scores['strip_ansi'] = scores.get('strip_ansi', 0) + count * 30
            elif category == 'format_drift':
                scores['trim_whitespace'] = scores.get('trim_whitespace', 0) + count * 30

        if not scores:
            return None, "No significant issues detected"

        # Pick highest scoring stage
        target = max(scores, key=scores.get)
        rationale = f"Targeting {target}: " + ", ".join(rationale_parts[:3])

        return target, rationale

    def plan(self, review: ReviewReport) -> Optional[ChangePlan]:
        """
        Produce a change plan targeting one parser stage.
        Returns None if no improvement is recommended.
        """
        if not review.recommended_target:
            logger.info("No improvement target recommended")
            return None

        stage = review.recommended_target
        stage_info = PARSER_STAGES.get(stage)

        if not stage_info:
            logger.warning(f"Unknown stage: {stage}")
            return None

        # Build problem statement based on review data
        problem_parts = []
        if review.failure_breakdown.get('had_ansi', 0) > 0 and stage == 'strip_ansi':
            problem_parts.append(
                f"{review.failure_breakdown['had_ansi']} captures in 24h had ANSI escape codes"
            )
        if review.failure_breakdown.get('had_echo', 0) > 0 and stage == 'remove_echo':
            problem_parts.append(
                f"{review.failure_breakdown['had_echo']} captures had instruction echo"
            )

        problem_statement = "; ".join(problem_parts) if problem_parts else review.target_rationale

        return ChangePlan(
            target_stage=stage,
            target_file=stage_info['file'],
            target_function=stage_info['function'],
            problem_statement=problem_statement,
            proposed_approach=f"Improve {stage_info['description']} to handle edge cases",
            affected_fixtures=[f['id'] for f in review.chronic_failures[:5]],
            risk_assessment="Low - isolated change within single function",
            estimated_diff_lines=30,
        )

    def check_review_gate(self) -> tuple[bool, int]:
        """Check if human review is required before proceeding.

        Returns (review_required, cycles_since_review).
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cycles_since = conn.execute("""
                SELECT COUNT(*) FROM improvement_cycles
                WHERE committed = 1
            """).fetchone()[0]
            conn.close()

            # Check for review checkpoint file
            checkpoint_file = Path("data/.parser_review_checkpoint")
            last_reviewed = 0
            if checkpoint_file.exists():
                last_reviewed = int(checkpoint_file.read_text().strip())

            cycles_since_review = cycles_since - last_reviewed

            return cycles_since_review >= MAX_CYCLES_WITHOUT_REVIEW, cycles_since_review

        except Exception as e:
            logger.warning(f"Failed to check review gate: {e}")
            return False, 0

    def mark_reviewed(self):
        """Mark that human review has been completed."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            total_cycles = conn.execute("""
                SELECT COUNT(*) FROM improvement_cycles WHERE committed = 1
            """).fetchone()[0]
            conn.close()

            checkpoint_file = Path("data/.parser_review_checkpoint")
            checkpoint_file.write_text(str(total_cycles))
            logger.info(f"Marked review complete at cycle {total_cycles}")
        except Exception as e:
            logger.warning(f"Failed to mark reviewed: {e}")

    def run_cycle(self, dry_run: bool = False) -> CycleResult:
        """Run a full improvement cycle.

        Args:
            dry_run: If True, only review and plan, don't implement

        Returns:
            CycleResult with outcome
        """
        cycle_id = secrets.token_hex(8)
        result = CycleResult(
            cycle_id=cycle_id,
            started_at=datetime.now(UTC).isoformat()
        )

        logger.info(f"Starting improvement cycle {cycle_id[:8]}")

        # Check review gate
        review_required, cycles_since = self.check_review_gate()
        if review_required:
            result.review_required = True
            result.rollback_reason = f"Human review required after {cycles_since} cycles"
            logger.warning(result.rollback_reason)
            self._store_cycle(result)
            return result

        # 1. Review (includes leakage audit)
        review = self.review()
        logger.info(f"Review: {review.capture_total_24h} captures, {review.capture_failures} failures")

        # 2. Create task if leakage audit found undetected patterns
        task_id = None
        if review.leakage_audit and review.leakage_audit.top_undetected:
            auditor = LeakageAuditor(self.db_path)
            task_id = auditor.create_fix_task(review.leakage_audit)
            if task_id:
                logger.info(f"Created fix task: {task_id}")

        # Store task_id in result for reporting
        result.task_id = task_id

        if not review.recommended_target:
            result.rollback_reason = "No flagged issues - see leakage audit for detection gaps"
            logger.info(result.rollback_reason)
            self._store_cycle(result)
            return result

        result.target_stage = review.recommended_target

        # 2. Plan
        plan = self.plan(review)
        if not plan:
            result.rollback_reason = "Could not create plan"
            self._store_cycle(result)
            return result

        logger.info(f"Plan: target {plan.target_stage} in {plan.target_file}")

        if dry_run:
            result.rollback_reason = "Dry run - no changes applied"
            self._store_cycle(result)
            return result

        # 3. Get baseline regression
        from .parser_regression import RegressionRunner
        runner = RegressionRunner()
        baseline = runner.run()
        result.score_before = baseline.overall_score

        logger.info(f"Baseline: {baseline.passed}/{baseline.total} ({baseline.pass_rate:.1%})")

        # 4. Implementation would happen here
        # For safety, we don't auto-implement changes yet
        # This would require Claude Code integration

        result.rollback_reason = "Auto-implementation not yet enabled"
        result.completed_at = datetime.now(UTC).isoformat()
        self._store_cycle(result)

        return result

    def _store_cycle(self, result: CycleResult):
        """Store improvement cycle result."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("""
                INSERT INTO improvement_cycles
                (id, started_at, completed_at, target_stage, committed,
                 rollback_reason, score_before, score_after,
                 fixtures_improved, regressions)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result.cycle_id,
                result.started_at,
                result.completed_at,
                result.target_stage,
                result.committed,
                result.rollback_reason,
                result.score_before,
                result.score_after,
                result.fixtures_improved,
                result.regressions,
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to store cycle result: {e}")

    def format_report(self, result: CycleResult, review: ReviewReport = None) -> str:
        """Format improvement cycle result for Discord."""
        lines = []
        lines.append("**Parser Improvement Report**")
        lines.append(f"{datetime.now(UTC).strftime('%Y-%m-%d %H:%M')} UTC")
        lines.append("")

        if result.review_required:
            lines.append("⚠️ **Human Review Required**")
            lines.append(f"• {result.rollback_reason}")
            lines.append("• Run `/parser-review` to approve and continue")
            return "\n".join(lines)

        if review:
            lines.append("**Review Findings:**")
            lines.append(f"• {review.capture_total_24h} captures in 24h, "
                        f"{review.capture_failures} flagged failures")
            if review.recommended_target:
                lines.append(f"• Recommended target: {review.recommended_target}")
            lines.append("")

            # Leakage audit section
            if review.leakage_audit:
                audit = review.leakage_audit
                lines.append("**Leakage Audit:**")
                lines.append(f"• {audit.captures_with_leakage}/{audit.total_captures} "
                            f"with leakage ({audit.leakage_rate:.0%})")

                if audit.top_undetected:
                    detection_gap = len(audit.top_undetected)
                    lines.append(f"• {detection_gap} pattern types slipping through detection")
                    lines.append("")
                    lines.append("**Top Undetected:**")
                    for item in audit.top_undetected[:5]:
                        lines.append(f"• `{item['pattern']}`: {item['count']} ({item['description']})")
                else:
                    lines.append("• ✅ All patterns detected correctly")
                lines.append("")

        # Task created notification
        if result.task_id:
            lines.append("**📋 Task Created:**")
            lines.append(f"• ID: `{result.task_id}`")
            lines.append("• Check Peter Queue for detailed fix plan")
            lines.append("")

        if result.target_stage:
            lines.append("**Target:**")
            lines.append(f"• Stage: `{result.target_stage}`")
            lines.append("")

        if result.score_before:
            lines.append("**Baseline:**")
            lines.append(f"• Score: {result.score_before:.3f}")
            lines.append("")

        if result.rollback_reason:
            lines.append(f"**Result:** {result.rollback_reason}")
        elif result.committed:
            lines.append("**Result:** ✅ Committed")
            lines.append(f"• Score: {result.score_before:.3f} → {result.score_after:.3f}")
            lines.append(f"• Fixtures improved: {result.fixtures_improved}")
        else:
            lines.append("**Result:** ❌ Rolled back")

        return "\n".join(lines)


# Singleton
_improver: ParserImprover | None = None


def get_parser_improver() -> ParserImprover:
    """Get the singleton parser improver."""
    global _improver
    if _improver is None:
        _improver = ParserImprover()
    return _improver


async def run_improvement_cycle() -> str:
    """Run an improvement cycle (for scheduled job)."""
    improver = get_parser_improver()
    review = improver.review()
    result = improver.run_cycle()
    return improver.format_report(result, review)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Parser improvement agent")
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # run command
    run_parser = subparsers.add_parser('run', help='Run improvement cycle')
    run_parser.add_argument('--dry-run', action='store_true',
                           help='Review and plan only, no changes')

    # review command
    subparsers.add_parser('review', help='Run review phase only')

    # status command
    subparsers.add_parser('status', help='Check improvement status')

    # mark-reviewed command
    subparsers.add_parser('mark-reviewed', help='Mark human review complete')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    improver = get_parser_improver()

    if args.command == 'run':
        result = improver.run_cycle(dry_run=args.dry_run)
        review = improver.review()
        print(improver.format_report(result, review))

    elif args.command == 'review':
        review = improver.review()
        print(json.dumps(review.to_dict(), indent=2, default=str))

    elif args.command == 'status':
        review_required, cycles_since = improver.check_review_gate()
        print(f"Cycles since last review: {cycles_since}")
        print(f"Review required: {'Yes' if review_required else 'No'}")
        print(f"Max cycles without review: {MAX_CYCLES_WITHOUT_REVIEW}")

    elif args.command == 'mark-reviewed':
        improver.mark_reviewed()
        print("Review marked complete")


if __name__ == '__main__':
    main()
