"""Job Analytics API for Peter Dashboard.

Provides endpoints for tracking and monitoring scheduled job execution:
- GET /api/jobs - List all scheduled jobs with current state
- GET /api/jobs/{job_id}/history - Get execution history for a job
- GET /api/jobs/{job_id}/logs - Get recent logs for a job
- GET /api/job-stats - Get aggregate statistics
- POST /api/jobs/{job_id}/run - Manually trigger a job

Uses SQLite for lightweight persistent storage of job execution history.
"""

import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# UK timezone for timestamps
UK_TZ = ZoneInfo("Europe/London")

# Database path - sibling to this file
DB_PATH = Path(__file__).parent.parent / "job_history.db"

# SCHEDULE.md path
SCHEDULE_PATH = Path(__file__).parent.parent.parent / "domains" / "peterbot" / "wsl_config" / "SCHEDULE.md"

# Create router
router = APIRouter(prefix="/api", tags=["jobs"])


# =============================================================================
# Database Setup
# =============================================================================

def init_db() -> None:
    """Initialize the job history database with required tables."""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS job_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL DEFAULT 'running',
                duration_ms INTEGER,
                output TEXT,
                error_message TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_executions_job_id
            ON job_executions(job_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_executions_started_at
            ON job_executions(started_at DESC)
        """)

        # Job logs table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS job_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL DEFAULT 'INFO',
                message TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_logs_job_id
            ON job_logs(job_id, timestamp DESC)
        """)
        conn.commit()


@contextmanager
def get_db():
    """Get a database connection with proper cleanup."""
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# Initialize database on module load
init_db()


# =============================================================================
# SCHEDULE.md Parser
# =============================================================================

class ScheduledJob(BaseModel):
    """Parsed job definition from SCHEDULE.md."""
    id: str
    name: str
    skill: str
    schedule: str
    channel: str
    enabled: bool
    whatsapp: bool = False
    quiet_exempt: bool = False


def parse_schedule_md() -> list[ScheduledJob]:
    """Parse SCHEDULE.md to get job definitions.

    Returns:
        List of ScheduledJob objects parsed from the schedule file
    """
    jobs = []

    if not SCHEDULE_PATH.exists():
        return jobs

    content = SCHEDULE_PATH.read_text(encoding="utf-8")

    # Find Fixed Time Jobs table
    cron_match = re.search(
        r"## Fixed Time Jobs.*?\n\|.*?\n\|[-\s|]+\n((?:\|.*?\n)+)",
        content,
        re.DOTALL | re.IGNORECASE
    )

    if cron_match:
        for row in cron_match.group(1).strip().split("\n"):
            job = _parse_table_row(row)
            if job:
                jobs.append(job)

    return jobs


def _parse_table_row(row: str) -> Optional[ScheduledJob]:
    """Parse a markdown table row into a ScheduledJob."""
    cols = [c.strip() for c in row.split("|") if c.strip()]
    if len(cols) < 5:
        return None

    name = cols[0]
    skill = cols[1]
    schedule = cols[2]
    channel = cols[3]
    enabled = cols[4].lower() in ("yes", "true", "1")

    # Generate stable job_id from skill (lowercase, no spaces)
    job_id = skill.lower().replace(" ", "-").replace("_", "-")

    # Check for WhatsApp flag
    whatsapp = "+whatsapp" in channel.lower()
    if whatsapp:
        channel = channel.replace("+whatsapp", "").replace("+WhatsApp", "").strip()

    # Check for quiet hours exemption
    quiet_exempt = "!quiet" in channel.lower()
    if quiet_exempt:
        channel = channel.replace("!quiet", "").replace("!Quiet", "").strip()

    return ScheduledJob(
        id=job_id,
        name=name,
        skill=skill,
        schedule=schedule,
        channel=channel,
        enabled=enabled,
        whatsapp=whatsapp,
        quiet_exempt=quiet_exempt
    )


def get_next_run_time(schedule: str) -> Optional[datetime]:
    """Calculate the next run time for a schedule expression.

    Args:
        schedule: Schedule string like "07:00 UK" or "hourly+3 UK"

    Returns:
        Next scheduled run time, or None if cannot be calculated
    """
    now = datetime.now(UK_TZ)
    schedule_clean = schedule.replace(" UK", "").strip()

    # Hourly with offset: "hourly" or "hourly+3"
    hourly_match = re.match(r"hourly(?:\+(\d+))?", schedule_clean.lower())
    if hourly_match:
        offset = int(hourly_match.group(1) or 0)
        next_run = now.replace(minute=offset, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(hours=1)
        return next_run

    # Half-hourly with offset: "half-hourly" or "half-hourly+1"
    half_hourly_match = re.match(r"half-hourly(?:\+(\d+))?", schedule_clean.lower())
    if half_hourly_match:
        offset = int(half_hourly_match.group(1) or 0)
        # Calculate next :offset or :30+offset
        if now.minute < offset:
            next_run = now.replace(minute=offset, second=0, microsecond=0)
        elif now.minute < 30 + offset:
            next_run = now.replace(minute=30 + offset, second=0, microsecond=0)
        else:
            next_run = (now + timedelta(hours=1)).replace(minute=offset, second=0, microsecond=0)
        return next_run

    # Monthly: "1st 09:00"
    if schedule_clean.startswith("1st "):
        time_part = schedule_clean[4:]
        time_match = re.match(r"(\d{1,2}):(\d{2})", time_part)
        if time_match:
            hour, minute = int(time_match.group(1)), int(time_match.group(2))
            next_run = now.replace(day=1, hour=hour, minute=minute, second=0, microsecond=0)
            if next_run <= now:
                # Move to first of next month
                if now.month == 12:
                    next_run = next_run.replace(year=now.year + 1, month=1)
                else:
                    next_run = next_run.replace(month=now.month + 1)
            return next_run

    # Simple daily time: "07:00" or multiple times "09:00,11:00,13:00"
    if ":" in schedule_clean:
        times = [t.strip() for t in schedule_clean.split(",") if ":" in t]
        next_runs = []

        for t in times:
            time_match = re.match(r"(\d{1,2}):(\d{2})", t)
            if time_match:
                hour, minute = int(time_match.group(1)), int(time_match.group(2))
                next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if next_run <= now:
                    next_run += timedelta(days=1)
                next_runs.append(next_run)

        if next_runs:
            return min(next_runs)

    return None


# =============================================================================
# Job Execution Tracking Functions (called from scheduler.py)
# =============================================================================

def record_job_start(job_id: str) -> int:
    """Record that a job has started executing.

    Args:
        job_id: The job identifier

    Returns:
        The execution record ID for later update
    """
    started_at = datetime.now(UK_TZ).isoformat()

    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO job_executions (job_id, started_at, status)
            VALUES (?, ?, 'running')
            """,
            (job_id, started_at)
        )
        execution_id = cursor.lastrowid
        conn.commit()

        # Also log the start
        conn.execute(
            """
            INSERT INTO job_logs (job_id, timestamp, level, message)
            VALUES (?, ?, 'INFO', 'Job started')
            """,
            (job_id, started_at)
        )
        conn.commit()

    return execution_id


def record_job_complete(
    job_id: str,
    success: bool,
    output: Optional[str] = None,
    error: Optional[str] = None,
    execution_id: Optional[int] = None
) -> None:
    """Record that a job has completed.

    Args:
        job_id: The job identifier
        success: Whether the job succeeded
        output: The job output (truncated to 500 chars)
        error: Error message if failed
        execution_id: The execution record ID (if known)
    """
    completed_at = datetime.now(UK_TZ).isoformat()
    status = "success" if success else "error"

    # Truncate output to 500 chars
    if output and len(output) > 500:
        output = output[:497] + "..."

    with get_db() as conn:
        if execution_id:
            # Update existing record
            conn.execute(
                """
                UPDATE job_executions
                SET completed_at = ?, status = ?, output = ?, error_message = ?,
                    duration_ms = CAST((julianday(?) - julianday(started_at)) * 86400000 AS INTEGER)
                WHERE id = ?
                """,
                (completed_at, status, output, error, completed_at, execution_id)
            )
        else:
            # Find most recent running execution for this job
            conn.execute(
                """
                UPDATE job_executions
                SET completed_at = ?, status = ?, output = ?, error_message = ?,
                    duration_ms = CAST((julianday(?) - julianday(started_at)) * 86400000 AS INTEGER)
                WHERE job_id = ? AND status = 'running'
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (completed_at, status, output, error, completed_at, job_id)
            )
        conn.commit()

        # Log completion
        log_message = f"Job completed: {status}"
        if error:
            log_message = f"Job failed: {error}"
        elif output:
            preview = output[:50] + "..." if len(output) > 50 else output
            log_message = f"Job completed successfully. Output: {preview}"

        conn.execute(
            """
            INSERT INTO job_logs (job_id, timestamp, level, message)
            VALUES (?, ?, ?, ?)
            """,
            (job_id, completed_at, "ERROR" if error else "INFO", log_message)
        )
        conn.commit()


def log_job_event(job_id: str, level: str, message: str) -> None:
    """Log a job-related event.

    Args:
        job_id: The job identifier
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        message: Log message
    """
    timestamp = datetime.now(UK_TZ).isoformat()

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO job_logs (job_id, timestamp, level, message)
            VALUES (?, ?, ?, ?)
            """,
            (job_id, timestamp, level.upper(), message)
        )
        conn.commit()


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/jobs")
async def list_jobs():
    """Get all scheduled jobs with current state.

    Returns jobs from SCHEDULE.md enriched with execution history.
    """
    jobs = parse_schedule_md()
    now = datetime.now(UK_TZ)

    # Get last run info for each job from database
    with get_db() as conn:
        result = []

        for job in jobs:
            # Get last execution
            last_exec = conn.execute(
                """
                SELECT started_at, completed_at, status, duration_ms
                FROM job_executions
                WHERE job_id = ?
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (job.id,)
            ).fetchone()

            # Get average duration from last 10 runs
            avg_duration = conn.execute(
                """
                SELECT AVG(duration_ms) as avg_ms
                FROM job_executions
                WHERE job_id = ? AND status = 'success' AND duration_ms IS NOT NULL
                ORDER BY started_at DESC
                LIMIT 10
                """,
                (job.id,)
            ).fetchone()

            # Check if currently running
            running = conn.execute(
                """
                SELECT COUNT(*) as count
                FROM job_executions
                WHERE job_id = ? AND status = 'running'
                """,
                (job.id,)
            ).fetchone()

            # Determine status
            if running and running["count"] > 0:
                status = "running"
            elif not job.enabled:
                status = "paused"
            elif last_exec and last_exec["status"] == "error":
                status = "error"
            else:
                status = "idle"

            # Calculate next run
            next_run = get_next_run_time(job.schedule)

            result.append({
                "id": job.id,
                "name": job.name,
                "skill": job.skill,
                "schedule": job.schedule,
                "channel": job.channel,
                "enabled": job.enabled,
                "status": status,
                "last_run": last_exec["started_at"] if last_exec else None,
                "last_status": last_exec["status"] if last_exec else None,
                "last_duration_ms": last_exec["duration_ms"] if last_exec else None,
                "next_run": next_run.isoformat() if next_run else None,
                "avg_duration_ms": int(avg_duration["avg_ms"]) if avg_duration and avg_duration["avg_ms"] else None,
            })

    # Count by status
    status_counts = {}
    for job in result:
        status = job["status"]
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "jobs": result,
        "total": len(result),
        "running": status_counts.get("running", 0),
        "queued": 0,  # Would need scheduler integration to get queue
        "jobs_by_status": status_counts,
    }


@router.get("/jobs/{job_id}/history")
async def get_job_history(job_id: str, limit: int = 50):
    """Get execution history for a specific job.

    Args:
        job_id: The job identifier
        limit: Maximum number of records to return (default 50)
    """
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT started_at, completed_at, status, duration_ms, output, error_message
            FROM job_executions
            WHERE job_id = ?
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (job_id, limit)
        ).fetchall()

        history = []
        for row in rows:
            output_preview = None
            if row["output"]:
                output_preview = row["output"][:100] + "..." if len(row["output"]) > 100 else row["output"]

            history.append({
                "started_at": row["started_at"],
                "completed_at": row["completed_at"],
                "status": row["status"],
                "duration_ms": row["duration_ms"],
                "output_preview": output_preview,
                "error": row["error_message"],
            })

    return {
        "job_id": job_id,
        "history": history,
        "count": len(history),
    }


@router.get("/jobs/{job_id}/logs")
async def get_job_logs(job_id: str, limit: int = 100):
    """Get recent logs for a specific job.

    Args:
        job_id: The job identifier
        limit: Maximum number of log entries to return (default 100)
    """
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT timestamp, level, message
            FROM job_logs
            WHERE job_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (job_id, limit)
        ).fetchall()

        logs = [
            {
                "timestamp": row["timestamp"],
                "level": row["level"],
                "message": row["message"],
            }
            for row in rows
        ]

    return {
        "job_id": job_id,
        "logs": logs,
        "count": len(logs),
    }


@router.get("/job-stats")
async def get_job_stats():
    """Get aggregate job statistics."""
    jobs = parse_schedule_md()
    now = datetime.now(UK_TZ)
    yesterday = now - timedelta(hours=24)

    with get_db() as conn:
        # Count executions in last 24 hours
        stats_24h = conn.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful,
                SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as failed,
                AVG(CASE WHEN status = 'success' THEN duration_ms END) as avg_duration
            FROM job_executions
            WHERE started_at >= ?
            """,
            (yesterday.isoformat(),)
        ).fetchone()

        # Count currently running
        running = conn.execute(
            "SELECT COUNT(*) as count FROM job_executions WHERE status = 'running'"
        ).fetchone()

        # Get recent failures for display
        recent_failures = conn.execute(
            """
            SELECT job_id, started_at, error_message
            FROM job_executions
            WHERE status = 'error' AND started_at >= ?
            ORDER BY started_at DESC
            LIMIT 10
            """,
            (yesterday.isoformat(),)
        ).fetchall()

    total = stats_24h["total"] or 0
    successful = stats_24h["successful"] or 0
    failed = stats_24h["failed"] or 0
    success_rate = (successful / total * 100) if total > 0 else 100.0

    # Count by status from jobs list
    enabled_count = sum(1 for j in jobs if j.enabled)
    paused_count = sum(1 for j in jobs if not j.enabled)
    running_count = running["count"] if running else 0
    idle_count = enabled_count - running_count

    return {
        "total_jobs": len(jobs),
        "enabled_jobs": enabled_count,
        "active_jobs": running_count,
        "jobs_24h": total,
        "success_rate_24h": round(success_rate, 1),
        "errors_24h": failed,
        "avg_duration_ms": int(stats_24h["avg_duration"]) if stats_24h["avg_duration"] else 0,
        "jobs_by_status": {
            "running": running_count,
            "idle": idle_count,
            "paused": paused_count,
        },
        "recent_failures": [
            {
                "job_id": row["job_id"],
                "timestamp": row["started_at"],
                "error": row["error_message"],
            }
            for row in recent_failures
        ],
    }


@router.post("/jobs/{job_id}/run")
async def trigger_job_run(job_id: str):
    """Manually trigger a job to run.

    This requires integration with the scheduler module.
    For now, returns instructions on how to trigger via Discord.

    Args:
        job_id: The job identifier (same as skill name)
    """
    # Find the job in schedule
    jobs = parse_schedule_md()
    job = next((j for j in jobs if j.id == job_id), None)

    if not job:
        raise HTTPException(404, f"Job not found: {job_id}")

    # For now, return instructions - full integration would require
    # access to the scheduler instance which lives in the Discord bot
    return {
        "status": "pending",
        "message": f"To manually run '{job.name}', use Discord command: !skill {job.skill}",
        "job_id": job_id,
        "skill": job.skill,
    }


# =============================================================================
# Cleanup Utilities
# =============================================================================

def cleanup_old_records(days: int = 30) -> int:
    """Remove job execution records older than specified days.

    Args:
        days: Number of days to retain (default 30)

    Returns:
        Number of records deleted
    """
    cutoff = (datetime.now(UK_TZ) - timedelta(days=days)).isoformat()

    with get_db() as conn:
        # Delete old executions
        cursor = conn.execute(
            "DELETE FROM job_executions WHERE started_at < ?",
            (cutoff,)
        )
        executions_deleted = cursor.rowcount

        # Delete old logs
        cursor = conn.execute(
            "DELETE FROM job_logs WHERE timestamp < ?",
            (cutoff,)
        )
        logs_deleted = cursor.rowcount

        conn.commit()

    return executions_deleted + logs_deleted
