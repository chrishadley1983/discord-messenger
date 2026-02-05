"""Tests for Claude Code health tracker module.

Tests the ClaudeCodeHealthTracker class that monitors:
- Job success/failure rates
- /clear command success rates
- Garbage response detection
- Alert thresholds
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock

from jobs.claude_code_health import (
    ClaudeCodeHealthTracker,
    JobResult,
    ClearResult,
    get_health_tracker,
    CONSECUTIVE_FAILURE_THRESHOLD,
    CLEAR_SUCCESS_THRESHOLD,
)


class TestClaudeCodeHealthTracker:
    """Tests for ClaudeCodeHealthTracker class."""

    @pytest.fixture
    def tracker(self):
        """Create a fresh tracker for each test."""
        return ClaudeCodeHealthTracker()

    def test_initial_state(self, tracker):
        """Tracker should start with healthy defaults."""
        stats = tracker.get_health_stats()
        assert stats["job_success_rate"] == 100.0
        assert stats["clear_success_rate"] == 100.0
        assert stats["garbage_rate"] == 0.0
        assert stats["consecutive_failures"] == 0
        assert stats["total_jobs_tracked"] == 0

    def test_record_successful_job(self, tracker):
        """Should track successful job execution."""
        tracker.record_job_result(
            "test-job",
            success=True,
            duration_seconds=5.0,
            response_length=500
        )

        stats = tracker.get_health_stats()
        assert stats["total_jobs_tracked"] == 1
        assert stats["job_success_rate"] == 100.0
        assert stats["consecutive_failures"] == 0

    def test_record_failed_job(self, tracker):
        """Should track failed job execution."""
        tracker.record_job_result(
            "test-job",
            success=False,
            error="timeout"
        )

        stats = tracker.get_health_stats()
        assert stats["total_jobs_tracked"] == 1
        assert stats["job_success_rate"] == 0.0
        assert stats["consecutive_failures"] == 1

    def test_consecutive_failures_increment(self, tracker):
        """Consecutive failures should increment counter."""
        for i in range(3):
            tracker.record_job_result(f"job-{i}", success=False)

        stats = tracker.get_health_stats()
        assert stats["consecutive_failures"] == 3

    def test_success_resets_consecutive_failures(self, tracker):
        """Successful job should reset consecutive failure counter."""
        tracker.record_job_result("job-1", success=False)
        tracker.record_job_result("job-2", success=False)
        tracker.record_job_result("job-3", success=True)

        stats = tracker.get_health_stats()
        assert stats["consecutive_failures"] == 0

    def test_garbage_response_counts_as_failure(self, tracker):
        """Garbage responses should increment failure counter."""
        tracker.record_job_result(
            "job-1",
            success=True,  # Job "completed" but response was garbage
            response_length=100,  # Need response length for garbage rate tracking
            is_garbage=True,
            garbage_patterns=["shell_path", "command_fragment"]
        )

        stats = tracker.get_health_stats()
        assert stats["consecutive_failures"] == 1
        assert stats["garbage_rate"] > 0

    def test_record_clear_success(self, tracker):
        """Should track successful /clear commands."""
        tracker.record_clear_result(success=True, duration_seconds=2.0)

        stats = tracker.get_health_stats()
        assert stats["clear_success_rate"] == 100.0
        assert stats["total_clears_tracked"] == 1

    def test_record_clear_timeout(self, tracker):
        """Should track /clear timeouts."""
        tracker.record_clear_result(
            success=False,
            duration_seconds=15.0,
            timeout=True
        )

        stats = tracker.get_health_stats()
        assert stats["clear_success_rate"] == 0.0

    def test_job_success_rate_calculation(self, tracker):
        """Should correctly calculate job success rate."""
        # 7 successes, 3 failures = 70%
        for i in range(7):
            tracker.record_job_result(f"success-{i}", success=True)
        for i in range(3):
            tracker.record_job_result(f"failure-{i}", success=False)

        rate = tracker.get_job_success_rate()
        assert rate == 0.7

    def test_clear_success_rate_calculation(self, tracker):
        """Should correctly calculate clear success rate."""
        # 8 successes, 2 failures = 80%
        for i in range(8):
            tracker.record_clear_result(success=True, duration_seconds=1.0)
        for i in range(2):
            tracker.record_clear_result(success=False, duration_seconds=10.0)

        rate = tracker.get_clear_success_rate()
        assert rate == 0.8

    def test_recent_jobs_in_stats(self, tracker):
        """Should include recent jobs in stats."""
        tracker.record_job_result("job-a", success=True, duration_seconds=3.0)
        tracker.record_job_result("job-b", success=False, error="failed")

        stats = tracker.get_health_stats()
        assert len(stats["recent_jobs"]) == 2
        assert stats["recent_jobs"][0]["name"] == "job-b"  # Most recent first
        assert stats["recent_jobs"][1]["name"] == "job-a"

    def test_recent_clears_in_stats(self, tracker):
        """Should include recent clears in stats."""
        tracker.record_clear_result(success=True, duration_seconds=2.0)
        tracker.record_clear_result(success=False, timeout=True)

        stats = tracker.get_health_stats()
        assert len(stats["recent_clears"]) == 2


class TestHealthAlerts:
    """Tests for alert threshold logic."""

    @pytest.fixture
    def tracker(self):
        """Create a fresh tracker for each test."""
        return ClaudeCodeHealthTracker()

    def test_no_alert_when_healthy(self, tracker):
        """Should not alert when everything is healthy."""
        tracker.record_job_result("job-1", success=True)

        assert tracker.should_alert_failures() is False
        assert tracker.should_alert_clear_rate() is False

    def test_alert_on_consecutive_failures(self, tracker):
        """Should alert after threshold consecutive failures."""
        for i in range(CONSECUTIVE_FAILURE_THRESHOLD):
            tracker.record_job_result(f"job-{i}", success=False)

        assert tracker.should_alert_failures() is True

    def test_no_alert_below_failure_threshold(self, tracker):
        """Should not alert below failure threshold."""
        for i in range(CONSECUTIVE_FAILURE_THRESHOLD - 1):
            tracker.record_job_result(f"job-{i}", success=False)

        assert tracker.should_alert_failures() is False

    def test_alert_on_low_clear_rate(self, tracker):
        """Should alert when clear success rate drops below threshold."""
        # Need enough data points first
        success_count = int(5 * CLEAR_SUCCESS_THRESHOLD) - 1
        failure_count = 5 - success_count

        for i in range(success_count):
            tracker.record_clear_result(success=True, duration_seconds=1.0)
        for i in range(failure_count + 1):
            tracker.record_clear_result(success=False, duration_seconds=10.0)

        assert tracker.should_alert_clear_rate() is True

    def test_alert_cooldown(self, tracker):
        """Should not re-alert within cooldown period."""
        for i in range(CONSECUTIVE_FAILURE_THRESHOLD):
            tracker.record_job_result(f"job-{i}", success=False)

        # First alert should be allowed
        assert tracker.should_alert_failures() is True
        tracker.mark_failure_alerted()

        # Second alert within cooldown should be blocked
        assert tracker.should_alert_failures() is False

    def test_garbage_alert(self, tracker):
        """Should alert on garbage detection."""
        result = JobResult(
            job_name="test",
            success=True,
            timestamp=datetime.now(),
            is_garbage=True,
            garbage_patterns=["shell_path"]
        )

        assert tracker.should_alert_garbage(result) is True
        tracker.mark_garbage_alerted()
        assert tracker.should_alert_garbage(result) is False


class TestGlobalHealthTracker:
    """Tests for global singleton tracker."""

    def test_get_health_tracker_returns_singleton(self):
        """get_health_tracker should return the same instance."""
        tracker1 = get_health_tracker()
        tracker2 = get_health_tracker()
        assert tracker1 is tracker2

    def test_tracker_is_instance_of_correct_class(self):
        """Returned tracker should be ClaudeCodeHealthTracker."""
        tracker = get_health_tracker()
        assert isinstance(tracker, ClaudeCodeHealthTracker)


class TestHealthStats:
    """Tests for health stats output format."""

    @pytest.fixture
    def tracker(self):
        """Create a tracker with some data."""
        tracker = ClaudeCodeHealthTracker()
        tracker.record_job_result("job-1", success=True, duration_seconds=5.0)
        tracker.record_job_result("job-2", success=False, error="timeout")
        tracker.record_clear_result(success=True, duration_seconds=2.0)
        return tracker

    def test_stats_contains_required_keys(self, tracker):
        """Stats should contain all required keys."""
        stats = tracker.get_health_stats()

        required_keys = [
            "job_success_rate",
            "clear_success_rate",
            "garbage_rate",
            "consecutive_failures",
            "total_jobs_tracked",
            "total_clears_tracked",
            "last_job_time",
            "recent_jobs",
            "recent_clears",
            "alerts",
        ]

        for key in required_keys:
            assert key in stats, f"Missing key: {key}"

    def test_stats_alerts_structure(self, tracker):
        """Alerts should have correct structure."""
        stats = tracker.get_health_stats()
        alerts = stats["alerts"]

        assert "consecutive_failure_alert" in alerts
        assert "clear_rate_alert" in alerts
        assert "recent_garbage" in alerts

    def test_recent_jobs_format(self, tracker):
        """Recent jobs should have correct format."""
        stats = tracker.get_health_stats()
        job = stats["recent_jobs"][0]

        assert "name" in job
        assert "success" in job
        assert "timestamp" in job
        assert "duration" in job
