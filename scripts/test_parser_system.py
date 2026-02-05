"""Comprehensive test of the self-improving parser system."""

import sys
sys.path.insert(0, '.')

import json
from pathlib import Path

def test_capture_store():
    """Test Phase 1: Capture store."""
    print("\n=== Phase 1: Capture Store ===")
    from domains.peterbot.capture_parser import get_parser_capture_store

    store = get_parser_capture_store()

    # Test capture
    capture_id = store.capture(
        channel_id="test-123",
        channel_name="test-channel",
        screen_before="Previous screen content",
        screen_after="Claude's response here",
        parser_output="Claude's response here",
        pipeline_output="Claude's response here",
        is_scheduled=False,
        skill_name=None,
        discord_msg_id="msg-001"
    )
    print(f"  - Created capture: {capture_id[:8]}...")

    # Test retrieval
    cap = store.get_capture(capture_id)
    assert cap is not None, "Failed to retrieve capture"
    print(f"  - Retrieved capture: channel={cap.channel_name}")

    # Test stats
    stats = store.get_capture_stats(hours=24)
    assert stats['total'] >= 1, "Stats should show at least 1 capture"
    print(f"  - Capture stats: {stats['total']} total, {stats['failures']} failures")

    print("  Phase 1 PASSED")
    return True


def test_parser_scorer():
    """Test Phase 2: Parser scorer."""
    print("\n=== Phase 2: Parser Scorer ===")
    from domains.peterbot.parser_scorer import get_parser_scorer

    scorer = get_parser_scorer()

    # Test scoring
    result = scorer.score(
        raw_capture="Hello, how can I help?",
        expected_output="Hello, how can I help?",
        actual_output="Hello, how can I help?",
        screen_before=None
    )

    print(f"  - Overall score: {result.overall:.3f}")
    print(f"  - Passed: {result.passed}")
    print(f"  - Content preservation: {result.content_preservation:.3f}")
    print(f"  - ANSI cleanliness: {result.ansi_cleanliness:.3f}")

    assert result.overall >= 0.9, "Matching output should score >= 0.9"
    assert result.passed, "Matching output should pass"
    print("  Phase 2 PASSED")
    return True


def test_regression_runner():
    """Test Phase 2: Regression runner."""
    print("\n=== Phase 2: Regression Runner ===")
    from domains.peterbot.parser_regression import RegressionRunner

    runner = RegressionRunner()
    report = runner.run()

    print(f"  - Total fixtures: {report.total}")
    print(f"  - Passed: {report.passed}")
    print(f"  - Failed: {report.failed}")
    print(f"  - Pass rate: {report.pass_rate:.1%}")

    assert report.total > 0, "Should have fixtures"
    print("  Phase 2 PASSED")
    return True


def test_scheduled_output_scorer():
    """Test Phase 4: Scheduled output scorer."""
    print("\n=== Phase 4: Scheduled Output Scorer ===")
    from domains.peterbot.scheduled_output_scorer import get_scheduled_output_scorer

    scorer = get_scheduled_output_scorer()

    # Get spec
    spec = scorer.get_spec("morning-briefing")
    if spec:
        print(f"  - Found spec for morning-briefing")
        print(f"  - Required sections: {spec.get('required_sections')[:50]}...")

        # Test scoring
        test_output = """**Morning Briefing**
📰 AI News | 4 Feb 2026

**Headlines:**
• Claude released new features
• AI safety research advances

**Summary:**
Major developments in AI this week..."""

        result = scorer.score(test_output, spec)
        print(f"  - Test output score: {result.overall:.3f}")
        print(f"  - Drifted: {result.drifted}")
    else:
        print("  - No spec found (will be created on first run)")

    print("  Phase 4 PASSED")
    return True


def test_feedback_processor():
    """Test Phase 6: Feedback processor."""
    print("\n=== Phase 6: Feedback Processor ===")
    from domains.peterbot.feedback_processor import get_feedback_processor, is_parser_feedback

    processor = get_feedback_processor()

    # Test natural language detection
    assert is_parser_feedback("that was wrong"), "Should detect feedback trigger"
    assert is_parser_feedback("formatting is broken"), "Should detect format feedback"
    assert not is_parser_feedback("hello there"), "Should not detect normal message"
    print("  - Natural language detection working")

    # Test recording
    feedback_id = processor.record_slash_command(
        user_id="user-123",
        channel_id="channel-456",
        channel_name="test",
        message="The morning briefing format was off",
        category="format_drift",
        skill_name="morning-briefing"
    )
    print(f"  - Recorded feedback: {feedback_id[:8]}...")

    # Test summary
    summary = processor.get_pending_summary()
    print(f"  - Pending feedback: {summary['total']}")

    print("  Phase 6 PASSED")
    return True


def test_morning_quality_report():
    """Test Phase 5: Morning quality report."""
    print("\n=== Phase 5: Morning Quality Report ===")
    from domains.peterbot.morning_quality_report import MorningQualityReportBuilder

    builder = MorningQualityReportBuilder()
    report = builder.build()

    print(f"  - Fixture total: {report.fixture_total}")
    print(f"  - Fixture passed: {report.fixture_passed}")
    print(f"  - Capture total (24h): {report.capture_total_24h}")
    print(f"  - Action items: {len(report.action_items)}")

    # Test formatting
    formatted = report.format_discord()
    assert "Parser Health" in formatted, "Report should include Parser Health"
    assert "Scheduled Output Health" in formatted, "Report should include Scheduled Output Health"
    print(f"  - Report length: {len(formatted)} chars")

    print("  Phase 5 PASSED")
    return True


def main():
    print("=" * 60)
    print("Self-Improving Parser System - Integration Test")
    print("=" * 60)

    results = {}

    try:
        results['capture_store'] = test_capture_store()
    except Exception as e:
        print(f"  Phase 1 FAILED: {e}")
        results['capture_store'] = False

    try:
        results['parser_scorer'] = test_parser_scorer()
    except Exception as e:
        print(f"  Phase 2a FAILED: {e}")
        results['parser_scorer'] = False

    try:
        results['regression_runner'] = test_regression_runner()
    except Exception as e:
        print(f"  Phase 2b FAILED: {e}")
        results['regression_runner'] = False

    try:
        results['scheduled_output'] = test_scheduled_output_scorer()
    except Exception as e:
        print(f"  Phase 4 FAILED: {e}")
        results['scheduled_output'] = False

    try:
        results['feedback_processor'] = test_feedback_processor()
    except Exception as e:
        print(f"  Phase 6 FAILED: {e}")
        results['feedback_processor'] = False

    try:
        results['morning_report'] = test_morning_quality_report()
    except Exception as e:
        print(f"  Phase 5 FAILED: {e}")
        results['morning_report'] = False

    # Summary
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, result in results.items():
        status = "PASS" if result else "FAIL"
        print(f"  {name}: {status}")

    print(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        print("\nAll systems operational!")
        return 0
    else:
        print("\nSome tests failed - check output above")
        return 1


if __name__ == "__main__":
    exit(main())
