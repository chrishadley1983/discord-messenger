"""Claude Code Health Monitoring.

Tracks Claude Code session health metrics:
- Scheduled job success/failure rate
- /clear command success rate
- Response extraction quality (garbage detection)
- Consecutive failure alerting

This module provides the core health tracking. Alerting is handled separately
to allow the dashboard to also use health stats without circular imports.
"""

import os
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from logger import logger

# UK timezone for timestamps
UK_TZ = ZoneInfo("Europe/London")

# Configuration
MAX_HISTORY_SIZE = 100  # Max job results to keep
CONSECUTIVE_FAILURE_THRESHOLD = 2  # Alert after N consecutive failures
CLEAR_SUCCESS_THRESHOLD = 0.80  # Alert if clear success rate drops below 80%
GARBAGE_ALERT_ENABLED = True  # Alert on garbage detection


@dataclass
class JobResult:
    """Record of a scheduled job execution."""
    job_name: str
    success: bool
    timestamp: datetime
    duration_seconds: float = 0.0
    response_length: int = 0
    is_garbage: bool = False
    garbage_patterns: list[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class ClearResult:
    """Record of a /clear command execution."""
    success: bool
    timestamp: datetime
    duration_seconds: float = 0.0
    timeout: bool = False


class ClaudeCodeHealthTracker:
    """Tracks Claude Code session health metrics."""

    def __init__(self):
        # Job execution history
        self._job_results: deque[JobResult] = deque(maxlen=MAX_HISTORY_SIZE)
        self._consecutive_failures: int = 0
        self._last_job_time: Optional[datetime] = None

        # Clear command history
        self._clear_results: deque[ClearResult] = deque(maxlen=MAX_HISTORY_SIZE)

        # Garbage detection stats
        self._garbage_count: int = 0
        self._total_responses: int = 0

        # Alert tracking (prevent spam)
        self._last_failure_alert: Optional[datetime] = None
        self._last_clear_alert: Optional[datetime] = None
        self._last_garbage_alert: Optional[datetime] = None

    def record_job_result(
        self,
        job_name: str,
        success: bool,
        duration_seconds: float = 0.0,
        response_length: int = 0,
        is_garbage: bool = False,
        garbage_patterns: list[str] = None,
        error: str = None
    ) -> None:
        """Record a job execution result.

        Args:
            job_name: Name of the scheduled job
            success: Whether job completed successfully
            duration_seconds: How long the job took
            response_length: Length of response (0 if empty)
            is_garbage: Whether response was detected as garbage
            garbage_patterns: List of garbage patterns found
            error: Error message if failed
        """
        now = datetime.now(UK_TZ)
        result = JobResult(
            job_name=job_name,
            success=success,
            timestamp=now,
            duration_seconds=duration_seconds,
            response_length=response_length,
            is_garbage=is_garbage,
            garbage_patterns=garbage_patterns or [],
            error=error
        )
        self._job_results.append(result)
        self._last_job_time = now

        # Track consecutive failures
        if success and not is_garbage:
            self._consecutive_failures = 0
        else:
            self._consecutive_failures += 1

        # Track garbage stats
        if response_length > 0:
            self._total_responses += 1
            if is_garbage:
                self._garbage_count += 1

        logger.debug(
            f"Health: Job {job_name} {'success' if success else 'failed'}, "
            f"consecutive_failures={self._consecutive_failures}, "
            f"is_garbage={is_garbage}"
        )

    def record_clear_result(
        self,
        success: bool,
        duration_seconds: float = 0.0,
        timeout: bool = False
    ) -> None:
        """Record a /clear command result.

        Args:
            success: Whether clear completed successfully
            duration_seconds: How long the clear took
            timeout: Whether the clear timed out
        """
        now = datetime.now(UK_TZ)
        result = ClearResult(
            success=success,
            timestamp=now,
            duration_seconds=duration_seconds,
            timeout=timeout
        )
        self._clear_results.append(result)

        logger.debug(
            f"Health: /clear {'success' if success else 'failed'} "
            f"in {duration_seconds:.1f}s, timeout={timeout}"
        )

    def get_job_success_rate(self, last_n: int = 20) -> float:
        """Get job success rate for last N jobs.

        Args:
            last_n: Number of recent jobs to consider

        Returns:
            Success rate as float (0.0 to 1.0)
        """
        if not self._job_results:
            return 1.0  # No data = assume healthy

        recent = list(self._job_results)[-last_n:]
        if not recent:
            return 1.0

        # Count jobs that succeeded AND weren't garbage
        successes = sum(1 for r in recent if r.success and not r.is_garbage)
        return successes / len(recent)

    def get_clear_success_rate(self, last_n: int = 20) -> float:
        """Get /clear success rate for last N clears.

        Args:
            last_n: Number of recent clears to consider

        Returns:
            Success rate as float (0.0 to 1.0)
        """
        if not self._clear_results:
            return 1.0  # No data = assume healthy

        recent = list(self._clear_results)[-last_n:]
        if not recent:
            return 1.0

        successes = sum(1 for r in recent if r.success)
        return successes / len(recent)

    def get_garbage_rate(self) -> float:
        """Get garbage response rate.

        Returns:
            Garbage rate as float (0.0 to 1.0)
        """
        if self._total_responses == 0:
            return 0.0
        return self._garbage_count / self._total_responses

    def get_health_stats(self) -> dict:
        """Get comprehensive health statistics.

        Returns:
            Dict with all health metrics
        """
        recent_jobs = list(self._job_results)[-10:]
        recent_clears = list(self._clear_results)[-10:]

        return {
            "job_success_rate": round(self.get_job_success_rate() * 100, 1),
            "clear_success_rate": round(self.get_clear_success_rate() * 100, 1),
            "garbage_rate": round(self.get_garbage_rate() * 100, 1),
            "consecutive_failures": self._consecutive_failures,
            "total_jobs_tracked": len(self._job_results),
            "total_clears_tracked": len(self._clear_results),
            "last_job_time": self._last_job_time.isoformat() if self._last_job_time else None,
            "recent_jobs": [
                {
                    "name": r.job_name,
                    "success": r.success,
                    "timestamp": r.timestamp.strftime("%H:%M:%S"),
                    "duration": round(r.duration_seconds, 1),
                    "is_garbage": r.is_garbage,
                    "error": r.error,
                }
                for r in reversed(recent_jobs)
            ],
            "recent_clears": [
                {
                    "success": r.success,
                    "timestamp": r.timestamp.strftime("%H:%M:%S"),
                    "duration": round(r.duration_seconds, 1),
                    "timeout": r.timeout,
                }
                for r in reversed(recent_clears)
            ],
            "alerts": {
                "consecutive_failure_alert": self._consecutive_failures >= CONSECUTIVE_FAILURE_THRESHOLD,
                "clear_rate_alert": self.get_clear_success_rate() < CLEAR_SUCCESS_THRESHOLD,
                "recent_garbage": any(r.is_garbage for r in recent_jobs[-3:]) if recent_jobs else False,
            },
        }

    def should_alert_failures(self) -> bool:
        """Check if we should alert for consecutive failures.

        Returns:
            True if alert should be sent
        """
        if self._consecutive_failures < CONSECUTIVE_FAILURE_THRESHOLD:
            return False

        # Check cooldown (10 minutes)
        if self._last_failure_alert:
            cooldown = (datetime.now(UK_TZ) - self._last_failure_alert).total_seconds()
            if cooldown < 600:
                return False

        return True

    def should_alert_clear_rate(self) -> bool:
        """Check if we should alert for low clear success rate.

        Returns:
            True if alert should be sent
        """
        if self.get_clear_success_rate() >= CLEAR_SUCCESS_THRESHOLD:
            return False

        # Need at least 5 clear attempts before alerting
        if len(self._clear_results) < 5:
            return False

        # Check cooldown (10 minutes)
        if self._last_clear_alert:
            cooldown = (datetime.now(UK_TZ) - self._last_clear_alert).total_seconds()
            if cooldown < 600:
                return False

        return True

    def should_alert_garbage(self, job_result: JobResult) -> bool:
        """Check if we should alert for garbage response.

        Args:
            job_result: The job result to check

        Returns:
            True if alert should be sent
        """
        if not GARBAGE_ALERT_ENABLED or not job_result.is_garbage:
            return False

        # Check cooldown (10 minutes)
        if self._last_garbage_alert:
            cooldown = (datetime.now(UK_TZ) - self._last_garbage_alert).total_seconds()
            if cooldown < 600:
                return False

        return True

    def mark_failure_alerted(self) -> None:
        """Mark that a failure alert was sent."""
        self._last_failure_alert = datetime.now(UK_TZ)

    def mark_clear_alerted(self) -> None:
        """Mark that a clear rate alert was sent."""
        self._last_clear_alert = datetime.now(UK_TZ)

    def mark_garbage_alerted(self) -> None:
        """Mark that a garbage alert was sent."""
        self._last_garbage_alert = datetime.now(UK_TZ)


# Global singleton instance
_health_tracker: Optional[ClaudeCodeHealthTracker] = None


def get_health_tracker() -> ClaudeCodeHealthTracker:
    """Get the global health tracker instance."""
    global _health_tracker
    if _health_tracker is None:
        _health_tracker = ClaudeCodeHealthTracker()
    return _health_tracker


# Discord webhook for alerts (same as service monitor)
ALERTS_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_ALERTS")


async def send_health_alert(message: str) -> None:
    """Send health alert to Discord via webhook.

    Args:
        message: Alert message to send
    """
    import httpx

    if not ALERTS_WEBHOOK_URL:
        logger.warning(f"[ClaudeCodeHealth] No webhook configured, would alert: {message}")
        return

    timestamp = datetime.now(UK_TZ).strftime("%H:%M:%S")
    payload = {
        "content": f"🔴 **[{timestamp}] Claude Code Health**\n{message}",
        "username": "Claude Code Health Monitor",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(ALERTS_WEBHOOK_URL, json=payload)
        logger.info(f"[ClaudeCodeHealth] Sent alert: {message[:50]}...")
    except Exception as e:
        logger.error(f"[ClaudeCodeHealth] Failed to send alert: {e}")


async def check_and_alert() -> None:
    """Check health metrics and send alerts if needed."""
    tracker = get_health_tracker()
    stats = tracker.get_health_stats()

    # Check for consecutive failures
    if tracker.should_alert_failures():
        await send_health_alert(
            f"**{stats['consecutive_failures']} consecutive job failures detected**\n\n"
            f"Recent failed jobs:\n" +
            "\n".join(
                f"- {r['name']} at {r['timestamp']}: {r.get('error', 'empty/garbage response')}"
                for r in stats['recent_jobs'][:3]
                if not r['success'] or r['is_garbage']
            )
        )
        tracker.mark_failure_alerted()

    # Check for low clear success rate
    if tracker.should_alert_clear_rate():
        await send_health_alert(
            f"**/clear success rate dropped to {stats['clear_success_rate']}%**\n\n"
            f"Last 5 clears had {sum(1 for r in stats['recent_clears'][:5] if r['timeout'])} timeouts.\n"
            f"Session may need manual restart."
        )
        tracker.mark_clear_alerted()


def register_health_check(scheduler, bot) -> None:
    """Register periodic health check job.

    Args:
        scheduler: APScheduler instance
        bot: Discord bot instance for sending alerts
    """
    async def health_check_job():
        await check_and_alert()

    scheduler.add_job(
        health_check_job,
        'interval',
        minutes=5,
        id="claude_code_health_check"
    )
    logger.info("Registered Claude Code health check job (every 5 mins)")
