"""Parser Regression Runner - Test all fixtures and generate reports.

Runs all parser fixtures through the current parser implementation and
scores them using the 6-dimension rubric.

Based on SELF_IMPROVING_PARSER.md Phase 2.

CLI Usage:
    # Run full regression suite
    python -m domains.peterbot.parser_regression run

    # Run only fixtures in a category
    python -m domains.peterbot.parser_regression run --category code_block

    # Run only previously-failing fixtures
    python -m domains.peterbot.parser_regression run --failing-only

    # Show detailed failure analysis for a specific fixture
    python -m domains.peterbot.parser_regression inspect <fixture_id>

    # Promote a capture to a fixture
    python -m domains.peterbot.parser_regression promote <capture_id> --category <cat> --expected "..."
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .capture_parser import get_parser_capture_store, ParserFixture
from .parser_scorer import ParserScorer, ScoreResult, get_parser_scorer
from .parser import extract_new_response, parse_response, ParseMode

from logger import logger


@dataclass
class RegressionReport:
    """Result of running the full regression suite."""
    total: int = 0
    passed: int = 0
    failed: int = 0
    regressions: int = 0       # Previously passing, now failing
    improvements: int = 0       # Previously failing, now passing
    by_category: dict = field(default_factory=dict)
    failures: list = field(default_factory=list)
    overall_score: float = 0.0
    run_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def summary(self) -> str:
        """Generate text summary of the regression report."""
        lines = [
            "=== Parser Regression Report ===",
            f"Run at: {self.run_at}Z",
            "",
            f"Total fixtures:  {self.total}",
            f"Passed:          {self.passed} ({self.pass_rate:.1%})",
            f"Failed:          {self.failed}",
            f"Regressions:     {self.regressions} {'⚠️' if self.regressions else '✅'}",
            f"Improvements:    {self.improvements} {'🎉' if self.improvements else ''}",
            f"Overall score:   {self.overall_score:.3f}",
            "",
            "--- By Category ---",
        ]

        for cat, stats in sorted(self.by_category.items()):
            rate = stats['passed'] / stats['total'] if stats['total'] else 0
            marker = "✅" if rate >= 0.9 else "⚠️" if rate >= 0.7 else "❌"
            lines.append(f"  {marker} {cat}: {stats['passed']}/{stats['total']} ({rate:.0%})")

        if self.failures:
            lines.append("")
            lines.append(f"--- Failed Fixtures (top 10) ---")
            for f in self.failures[:10]:
                lines.append(f"  [{f['category']}] {f['id'][:8]}: {f['score']:.3f} — {', '.join(f['failed_dims'])}")

        return '\n'.join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            'total': self.total,
            'passed': self.passed,
            'failed': self.failed,
            'regressions': self.regressions,
            'improvements': self.improvements,
            'by_category': self.by_category,
            'failures': self.failures[:20],  # Limit stored failures
            'overall_score': self.overall_score,
            'pass_rate': self.pass_rate,
            'run_at': self.run_at,
        }


class RegressionRunner:
    """Run all fixtures through the current parser and score them."""

    def __init__(
        self,
        parser_fn: Optional[Callable] = None,
        scorer: Optional[ParserScorer] = None,
    ):
        """Initialize the runner.

        Args:
            parser_fn: Callable(raw_capture, screen_before) -> parsed_output
                       If None, uses the default parser.py implementation
            scorer: ParserScorer instance. If None, uses default.
        """
        self.store = get_parser_capture_store()
        self.parser_fn = parser_fn or self._default_parser
        self.scorer = scorer or get_parser_scorer()

    def _default_parser(self, raw_capture: str, screen_before: str | None) -> str:
        """Default parser function using parser.py."""
        if screen_before:
            return extract_new_response(screen_before, raw_capture)
        else:
            result = parse_response(raw_capture, mode=ParseMode.CONVERSATIONAL)
            return result.content

    def run(
        self,
        category: str | None = None,
        failing_only: bool = False,
    ) -> RegressionReport:
        """Execute full regression suite.

        Args:
            category: Optional category filter
            failing_only: Only run previously-failing fixtures

        Returns:
            RegressionReport with full results
        """
        report = RegressionReport()

        # Get fixtures
        fixtures = self.store.get_fixtures(
            category=category,
            failing_only=failing_only
        )

        logger.info(f"Running regression on {len(fixtures)} fixtures...")

        for fixture in fixtures:
            report.total += 1

            # Run parser
            try:
                actual_output = self.parser_fn(
                    raw_capture=fixture.raw_capture,
                    screen_before=fixture.screen_before
                )
            except Exception as e:
                actual_output = f"[PARSER ERROR: {e}]"
                logger.warning(f"Parser error on fixture {fixture.id[:8]}: {e}")

            # Score
            result = self.scorer.score(
                raw_capture=fixture.raw_capture,
                expected_output=fixture.expected_output,
                actual_output=actual_output,
                screen_before=fixture.screen_before
            )

            passed = result.passed
            was_passing = fixture.last_pass

            # Track category stats
            cat = fixture.category
            if cat not in report.by_category:
                report.by_category[cat] = {'total': 0, 'passed': 0, 'failed': 0}
            report.by_category[cat]['total'] += 1

            if passed:
                report.passed += 1
                report.by_category[cat]['passed'] += 1
                if was_passing is False:
                    report.improvements += 1
            else:
                report.failed += 1
                report.by_category[cat]['failed'] += 1
                report.failures.append({
                    'id': fixture.id,
                    'category': cat,
                    'score': result.overall,
                    'failed_dims': result.failures,
                    'actual_output_preview': (actual_output or '')[:200],
                })
                if was_passing is True:
                    report.regressions += 1

            # Update fixture record
            self.store.update_fixture_result(
                fixture_id=fixture.id,
                passed=passed,
                regressed=(was_passing is True and not passed)
            )

        report.overall_score = report.passed / report.total if report.total else 0.0

        logger.info(f"Regression complete: {report.passed}/{report.total} passed ({report.pass_rate:.1%})")

        return report

    def inspect(self, fixture_id: str) -> dict:
        """Get detailed analysis of a specific fixture.

        Args:
            fixture_id: ID of the fixture to inspect

        Returns:
            Dict with fixture details, score breakdown, actual vs expected
        """
        fixture = self.store.get_fixture(fixture_id)
        if not fixture:
            return {'error': f'Fixture {fixture_id} not found'}

        # Run parser
        try:
            actual_output = self.parser_fn(
                raw_capture=fixture.raw_capture,
                screen_before=fixture.screen_before
            )
        except Exception as e:
            actual_output = f"[PARSER ERROR: {e}]"

        # Score
        result = self.scorer.score(
            raw_capture=fixture.raw_capture,
            expected_output=fixture.expected_output,
            actual_output=actual_output,
            screen_before=fixture.screen_before
        )

        return {
            'fixture': {
                'id': fixture.id,
                'category': fixture.category,
                'tags': fixture.tags,
                'difficulty': fixture.difficulty,
                'source': fixture.source,
                'notes': fixture.notes,
                'fail_count': fixture.fail_count,
            },
            'score': result.to_dict(),
            'expected_output': fixture.expected_output,
            'actual_output': actual_output,
            'raw_capture_preview': fixture.raw_capture[:500] if fixture.raw_capture else None,
            'diff_summary': self._diff_summary(fixture.expected_output, actual_output),
        }

    def _diff_summary(self, expected: str, actual: str) -> str:
        """Generate a brief summary of differences."""
        if expected == actual:
            return "Exact match"

        expected_lines = set(expected.strip().split('\n'))
        actual_lines = set(actual.strip().split('\n'))

        missing = expected_lines - actual_lines
        extra = actual_lines - expected_lines

        parts = []
        if missing:
            parts.append(f"Missing {len(missing)} lines")
        if extra:
            parts.append(f"Extra {len(extra)} lines")

        len_diff = len(actual) - len(expected)
        if abs(len_diff) > 50:
            parts.append(f"Length diff: {len_diff:+d} chars")

        return ", ".join(parts) if parts else "Minor differences"


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Parser regression testing and fixture management"
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # run command
    run_parser = subparsers.add_parser('run', help='Run regression suite')
    run_parser.add_argument('--category', '-c', help='Only run fixtures in this category')
    run_parser.add_argument('--failing-only', '-f', action='store_true',
                           help='Only run previously-failing fixtures')

    # inspect command
    inspect_parser = subparsers.add_parser('inspect', help='Inspect a specific fixture')
    inspect_parser.add_argument('fixture_id', help='Fixture ID to inspect')

    # promote command
    promote_parser = subparsers.add_parser('promote', help='Promote capture to fixture')
    promote_parser.add_argument('capture_id', help='Capture ID to promote')
    promote_parser.add_argument('--category', '-c', required=True, help='Fixture category')
    promote_parser.add_argument('--expected', '-e', required=True, help='Expected output')
    promote_parser.add_argument('--tags', '-t', help='Comma-separated tags')
    promote_parser.add_argument('--notes', '-n', help='Notes about this fixture')

    # stats command
    stats_parser = subparsers.add_parser('stats', help='Show fixture statistics')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    runner = RegressionRunner()

    if args.command == 'run':
        report = runner.run(
            category=args.category,
            failing_only=args.failing_only
        )
        print(report.summary())

    elif args.command == 'inspect':
        result = runner.inspect(args.fixture_id)
        print(json.dumps(result, indent=2, default=str))

    elif args.command == 'promote':
        store = get_parser_capture_store()
        tags = args.tags.split(',') if args.tags else []
        try:
            fixture_id = store.promote_to_fixture(
                capture_id=args.capture_id,
                expected_output=args.expected,
                category=args.category,
                tags=tags,
                notes=args.notes
            )
            print(f"✅ Promoted to fixture: {fixture_id}")
        except ValueError as e:
            print(f"❌ {e}")
            sys.exit(1)

    elif args.command == 'stats':
        store = get_parser_capture_store()
        stats = store.get_fixture_stats()
        print(json.dumps(stats, indent=2))


if __name__ == '__main__':
    main()
