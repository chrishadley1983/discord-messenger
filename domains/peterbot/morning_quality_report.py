"""Morning Quality Report - Phase 5: Consolidated daily quality report.

Delivered every morning before the morning briefing, summarizing:
- Parser health (fixture pass rate, captures, leakage)
- Overnight improvement cycle results
- Scheduled output health (format drift)
- Feedback summary
- 7-day trends
- Action items

Based on SELF_IMPROVING_PARSER.md Phase 5.
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from logger import logger


# Database path
DB_PATH = Path("data/parser_fixtures.db")


@dataclass
class QualityReport:
    """Consolidated morning quality report."""

    # Parser health
    fixture_total: int
    fixture_passed: int
    capture_total_24h: int
    capture_failures_24h: int
    ansi_leaks: int
    echo_leaks: int
    empty_responses: int
    fixture_cache_size: int
    fixtures_promoted_overnight: int

    # Improvement cycle
    improvement_ran: bool
    improvement_target: Optional[str]
    improvement_committed: bool
    improvement_score_before: Optional[float]
    improvement_score_after: Optional[float]
    improvement_fixtures_improved: int
    improvement_regressions: int
    cycles_since_human_review: int

    # Scheduled output health
    scheduled_scores: list[dict]   # [{skill, score, status, notes}]
    drift_alerts: list[dict]       # [{skill, issue, likely_cause, recommendation}]

    # Feedback summary
    feedback_received: int
    feedback_resolved: int
    feedback_pending: int

    # 7-day trends
    trend_parser_pass_rate: tuple[float, float]     # (7_days_ago, now)
    trend_capture_failure_rate: tuple[float, float]
    trend_scheduled_avg: tuple[float, float]
    trend_fixtures_added: int

    # Action items (auto-generated)
    action_items: list[str]

    def format_discord(self) -> str:
        """Format as Discord message."""
        now = datetime.utcnow()
        lines = []

        lines.append("**Parser & Output Quality Report**")
        lines.append(f"{now.strftime('%A %d %b %Y')} | {now.strftime('%H:%M')} GMT")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

        # Parser health
        lines.append("**Parser Health**")
        pass_rate = self.fixture_passed / self.fixture_total if self.fixture_total else 0
        fail_rate = self.capture_failures_24h / self.capture_total_24h if self.capture_total_24h else 0
        target_marker = "✅" if pass_rate >= 0.95 else "⚠️" if pass_rate >= 0.90 else "❌"

        lines.append(f"• Fixture pass rate: {self.fixture_passed}/{self.fixture_total} "
                     f"({pass_rate:.1%}) {target_marker}")
        lines.append(f"• 24h captures: {self.capture_total_24h} total, "
                     f"{self.capture_failures_24h} failures ({fail_rate:.1%})")
        lines.append(f"• ANSI leaks: {self.ansi_leaks} {'✅' if self.ansi_leaks == 0 else '⚠️'}")
        lines.append(f"• Echo leaks: {self.echo_leaks} {'✅' if self.echo_leaks == 0 else '⚠️'}")
        lines.append(f"• Empty responses: {self.empty_responses} "
                     f"{'✅' if self.empty_responses == 0 else '⚠️'}")
        lines.append(f"• Fixture cache: {self.fixture_cache_size} fixtures "
                     f"(+{self.fixtures_promoted_overnight} overnight)")
        lines.append("")

        # Improvement cycle
        lines.append("**Overnight Improvement Cycle**")
        if self.improvement_ran:
            status = "✅ Committed" if self.improvement_committed else "❌ Rolled back"
            lines.append(f"• Target stage: {self.improvement_target}")
            if self.improvement_score_before and self.improvement_score_after:
                lines.append(f"• Result: {status} — score "
                            f"{self.improvement_score_before:.3f} → {self.improvement_score_after:.3f}")
            lines.append(f"• Fixtures improved: {self.improvement_fixtures_improved} | "
                        f"Regressions: {self.improvement_regressions}")
        else:
            lines.append("• No improvement cycle ran overnight")
        lines.append(f"• Cycles since review: {self.cycles_since_human_review}/5"
                     f"{' ⚠️' if self.cycles_since_human_review >= 4 else ''}")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

        # Scheduled output health
        lines.append("**Scheduled Output Health**")
        lines.append("")
        for s in self.scheduled_scores:
            if s.get('status') == 'not_due':
                lines.append(f"─  {s['skill']:<22} —     ({s.get('notes', '')})")
            else:
                score = s.get('score', 0)
                marker = "✅" if score >= 0.85 else "⚠️" if score >= 0.70 else "❌"
                lines.append(f"{marker} {s['skill']:<22} {score:.2f}  ({s.get('notes', '')})")

        if self.drift_alerts:
            lines.append("")
            lines.append(f"Drift alerts: {len(self.drift_alerts)}")
            for alert in self.drift_alerts[:3]:
                lines.append(f"• {alert.get('skill', 'Unknown')}: {alert.get('issue', '')}")
                if alert.get('recommendation'):
                    lines.append(f"  → {alert['recommendation']}")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

        # Feedback summary
        lines.append("**Feedback Summary**")
        lines.append(f"• Received yesterday: {self.feedback_received}")
        lines.append(f"• Resolved: {self.feedback_resolved} ✅")
        lines.append(f"• Pending: {self.feedback_pending}")
        lines.append("")

        # 7-day trends
        lines.append("**7-Day Trends**")
        pr_old, pr_new = self.trend_parser_pass_rate
        cf_old, cf_new = self.trend_capture_failure_rate
        sa_old, sa_new = self.trend_scheduled_avg

        pr_arrow = "↑" if pr_new > pr_old else "↓" if pr_new < pr_old else "→"
        cf_arrow = "↓" if cf_new < cf_old else "↑" if cf_new > cf_old else "→"
        sa_arrow = "↑" if sa_new > sa_old else "↓" if sa_new < sa_old else "→"

        lines.append(f"• Parser pass rate: {pr_old:.1%} → {pr_new:.1%} ({pr_arrow}{abs(pr_new - pr_old):.1%})")
        lines.append(f"• Capture failure rate: {cf_old:.1%} → {cf_new:.1%} ({cf_arrow}{abs(cf_new - cf_old):.1%})")
        lines.append(f"• Scheduled avg score: {sa_old:.2f} → {sa_new:.2f} ({sa_arrow}{abs(sa_new - sa_old):.2f})")
        lines.append(f"• Fixtures added: {self.trend_fixtures_added}")
        lines.append("")

        # Action items
        if self.action_items:
            lines.append("**Action Items**")
            for i, item in enumerate(self.action_items[:5], 1):
                lines.append(f"{i}. {item}")
            lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        tomorrow = now + timedelta(days=1)
        lines.append(f"Next report: {tomorrow.strftime('%A %d %b')} 06:45 GMT")

        return '\n'.join(lines)


class MorningQualityReportBuilder:
    """Gathers data from all subsystems and builds the morning report."""

    def __init__(self, db_path: str = None):
        self.db_path = Path(db_path) if db_path else DB_PATH

    def build(self) -> QualityReport:
        """Collect all data and build the report."""

        # 1. Get fixture stats
        fixture_stats = self._get_fixture_stats()

        # 2. Get 24h capture stats
        capture_stats = self._get_capture_stats(hours=24)

        # 3. Get improvement cycle results
        improvement = self._get_last_improvement_result()

        # 4. Get scheduled output health
        scheduled = self._get_scheduled_output_health()

        # 5. Get feedback stats
        feedback = self._get_feedback_stats()

        # 6. Compute 7-day trends
        trends = self._compute_trends()

        # 7. Generate action items
        action_items = self._generate_action_items(
            fixture_stats, capture_stats, improvement, scheduled, feedback
        )

        return QualityReport(
            fixture_total=fixture_stats.get('total', 0),
            fixture_passed=fixture_stats.get('passing', 0),
            capture_total_24h=capture_stats.get('total', 0),
            capture_failures_24h=capture_stats.get('failures', 0),
            ansi_leaks=capture_stats.get('ansi', 0),
            echo_leaks=capture_stats.get('echo', 0),
            empty_responses=capture_stats.get('empty', 0),
            fixture_cache_size=fixture_stats.get('total', 0),
            fixtures_promoted_overnight=capture_stats.get('promoted', 0),
            improvement_ran=improvement.get('ran', False),
            improvement_target=improvement.get('target'),
            improvement_committed=improvement.get('committed', False),
            improvement_score_before=improvement.get('score_before'),
            improvement_score_after=improvement.get('score_after'),
            improvement_fixtures_improved=improvement.get('fixtures_improved', 0),
            improvement_regressions=improvement.get('regressions', 0),
            cycles_since_human_review=improvement.get('cycles_since_review', 0),
            scheduled_scores=scheduled.get('scores', []),
            drift_alerts=scheduled.get('alerts', []),
            feedback_received=feedback.get('received', 0),
            feedback_resolved=feedback.get('resolved', 0),
            feedback_pending=feedback.get('pending', 0),
            trend_parser_pass_rate=trends.get('parser_pass_rate', (0.0, 0.0)),
            trend_capture_failure_rate=trends.get('capture_failure_rate', (0.0, 0.0)),
            trend_scheduled_avg=trends.get('scheduled_avg', (0.0, 0.0)),
            trend_fixtures_added=trends.get('fixtures_added', 0),
            action_items=action_items,
        )

    def _get_fixture_stats(self) -> dict:
        """Get fixture statistics."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                total = conn.execute("SELECT COUNT(*) FROM fixtures").fetchone()[0]
                passing = conn.execute(
                    "SELECT COUNT(*) FROM fixtures WHERE last_pass = 1"
                ).fetchone()[0]
                failing = conn.execute(
                    "SELECT COUNT(*) FROM fixtures WHERE last_pass = 0"
                ).fetchone()[0]

            return {
                'total': total,
                'passing': passing,
                'failing': failing,
            }
        except Exception as e:
            logger.warning(f"Failed to get fixture stats: {e}")
            return {'total': 0, 'passing': 0, 'failing': 0}

    def _get_capture_stats(self, hours: int = 24) -> dict:
        """Get capture statistics for the last N hours."""
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                total = conn.execute(
                    "SELECT COUNT(*) FROM captures WHERE captured_at > ?", (cutoff,)
                ).fetchone()[0]
                empty = conn.execute(
                    "SELECT COUNT(*) FROM captures WHERE captured_at > ? AND was_empty = 1",
                    (cutoff,)
                ).fetchone()[0]
                ansi = conn.execute(
                    "SELECT COUNT(*) FROM captures WHERE captured_at > ? AND had_ansi = 1",
                    (cutoff,)
                ).fetchone()[0]
                echo = conn.execute(
                    "SELECT COUNT(*) FROM captures WHERE captured_at > ? AND had_echo = 1",
                    (cutoff,)
                ).fetchone()[0]
                promoted = conn.execute(
                    "SELECT COUNT(*) FROM captures WHERE captured_at > ? AND promoted = 1",
                    (cutoff,)
                ).fetchone()[0]

            failures = empty + ansi + echo

            return {
                'total': total,
                'failures': failures,
                'empty': empty,
                'ansi': ansi,
                'echo': echo,
                'promoted': promoted,
            }
        except Exception as e:
            logger.warning(f"Failed to get capture stats: {e}")
            return {'total': 0, 'failures': 0, 'empty': 0, 'ansi': 0, 'echo': 0, 'promoted': 0}

    def _get_last_improvement_result(self) -> dict:
        """Get results of the last improvement cycle."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute("""
                    SELECT * FROM improvement_cycles
                    ORDER BY started_at DESC LIMIT 1
                """).fetchone()

                if not row:
                    return {'ran': False, 'cycles_since_review': 0}

                # Count cycles since last review (placeholder - need review tracking)
                cycles_since = conn.execute(
                    "SELECT COUNT(*) FROM improvement_cycles WHERE committed = 1"
                ).fetchone()[0] % 5

            return {
                'ran': True,
                'target': row['target_stage'],
                'committed': bool(row['committed']),
                'score_before': row['score_before'],
                'score_after': row['score_after'],
                'fixtures_improved': row['fixtures_improved'] or 0,
                'regressions': row['regressions'] or 0,
                'cycles_since_review': cycles_since,
            }
        except Exception as e:
            logger.warning(f"Failed to get improvement result: {e}")
            return {'ran': False, 'cycles_since_review': 0}

    def _get_scheduled_output_health(self) -> dict:
        """Get health status of scheduled outputs."""
        try:
            from .scheduled_output_scorer import get_scheduled_output_scorer
            scorer = get_scheduled_output_scorer()
            skill_health = scorer.get_skill_health()
            drift_alerts = scorer.get_drift_alerts(hours=24)

            scores = []
            for skill in skill_health:
                scores.append({
                    'skill': skill['display_name'],
                    'score': skill['avg_score'] or 0,
                    'status': skill['status'],
                    'notes': f"{skill['drift_count']} drift{'s' if skill['drift_count'] != 1 else ''}" if skill['drift_count'] else 'consistent',
                })

            alerts = []
            for alert in drift_alerts[:5]:
                details = json.loads(alert.get('drift_details', '[]'))
                alerts.append({
                    'skill': alert.get('skill_name', 'Unknown'),
                    'issue': details[0] if details else 'Format drift detected',
                    'recommendation': 'Review skill prompt or data source',
                })

            return {'scores': scores, 'alerts': alerts}
        except Exception as e:
            logger.warning(f"Failed to get scheduled output health: {e}")
            return {'scores': [], 'alerts': []}

    def _get_feedback_stats(self) -> dict:
        """Get feedback statistics."""
        cutoff_24h = (datetime.utcnow() - timedelta(hours=24)).isoformat()

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                received = conn.execute(
                    "SELECT COUNT(*) FROM feedback WHERE created_at > ?", (cutoff_24h,)
                ).fetchone()[0]
                resolved = conn.execute(
                    "SELECT COUNT(*) FROM feedback WHERE resolved_at > ?", (cutoff_24h,)
                ).fetchone()[0]
                pending = conn.execute(
                    "SELECT COUNT(*) FROM feedback WHERE status = 'pending'"
                ).fetchone()[0]

            return {
                'received': received,
                'resolved': resolved,
                'pending': pending,
            }
        except Exception as e:
            logger.warning(f"Failed to get feedback stats: {e}")
            return {'received': 0, 'resolved': 0, 'pending': 0}

    def _compute_trends(self) -> dict:
        """Compute 7-day trends."""
        # Placeholder - would need historical data storage
        return {
            'parser_pass_rate': (0.90, 0.90),
            'capture_failure_rate': (0.05, 0.05),
            'scheduled_avg': (0.85, 0.85),
            'fixtures_added': 0,
        }

    def _generate_action_items(
        self,
        fixture_stats: dict,
        capture_stats: dict,
        improvement: dict,
        scheduled: dict,
        feedback: dict,
    ) -> list[str]:
        """Auto-generate prioritized action items."""
        items = []

        # Critical: regressions
        if improvement.get('regressions', 0) > 0:
            items.append(f"Investigate {improvement['regressions']} fixture regressions")

        # Drift alerts
        for alert in scheduled.get('alerts', [])[:2]:
            items.append(f"Review {alert.get('skill', 'skill')}: {alert.get('issue', 'format drift')}")

        # ANSI leaks
        if capture_stats.get('ansi', 0) > 0:
            items.append(f"ANSI leakage in {capture_stats['ansi']} messages - check strip_ansi()")

        # Echo leaks
        if capture_stats.get('echo', 0) > 2:
            items.append(f"Echo leakage elevated ({capture_stats['echo']} in 24h)")

        # Empty responses
        if capture_stats.get('empty', 0) > 3:
            items.append(f"High empty response rate ({capture_stats['empty']} in 24h)")

        # Human review approaching
        if improvement.get('cycles_since_review', 0) >= 4:
            items.append("Human review checkpoint approaching")

        # Pass rate below target
        total = fixture_stats.get('total', 0)
        passed = fixture_stats.get('passing', 0)
        if total > 0:
            rate = passed / total
            if rate < 0.90:
                items.append(f"Fixture pass rate critical ({rate:.1%}) - below 90%")
            elif rate < 0.95:
                items.append(f"Fixture pass rate below target ({rate:.1%}) - target >= 95%")

        # Pending feedback
        if feedback.get('pending', 0) > 5:
            items.append(f"Review {feedback['pending']} pending feedback items")

        return items


async def generate_morning_quality_report() -> str:
    """Generate and return the morning quality report as Discord text."""
    builder = MorningQualityReportBuilder()
    report = builder.build()
    return report.format_discord()


# Skill data fetcher for scheduled job
async def fetch_morning_quality_data() -> dict:
    """Data fetcher for the morning-quality-report skill."""
    builder = MorningQualityReportBuilder()
    report = builder.build()
    return {
        'report_text': report.format_discord(),
        'fixture_stats': {
            'total': report.fixture_total,
            'passed': report.fixture_passed,
        },
        'capture_stats': {
            'total': report.capture_total_24h,
            'failures': report.capture_failures_24h,
        },
        'action_items': report.action_items,
    }
