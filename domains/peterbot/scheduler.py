"""Peterbot scheduler - SCHEDULE.md parsing and job execution.

Parses SCHEDULE.md markdown tables and registers jobs with APScheduler.
Jobs execute by routing skill context to Claude Code session.
"""

import asyncio
import json
import re
import yaml
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from logger import logger
from .response.pipeline import process as process_response

# Import job history recording functions
try:
    from peter_dashboard.api.jobs import record_job_start, record_job_complete
    JOB_HISTORY_ENABLED = True
except ImportError:
    JOB_HISTORY_ENABLED = False
    record_job_start = None
    record_job_complete = None

# Channel name to ID mapping
CHANNEL_IDS = {
    "#peterbot": None,  # Set from environment
    "#food-log": 1465294449038069912,
    "#ai-briefings": 1465277483866788037,
    "#ai-news": 1465277483866788037,
    "#api-costs": 1465761699582972142,
    "#api-balances": 1465761699582972142,
    "#api-usage": 1465761699582972142,
    "#traffic-reports": 1466522078462083325,
    "#news": 1465277483866788037,
    "#youtube": 1465277483866788037,
    "#peter-heartbeat": 1467553740570755105,
}

# UK timezone
UK_TZ = ZoneInfo("Europe/London")

# Quiet hours (no jobs)
QUIET_START = 23  # 11pm
QUIET_END = 6     # 6am


@dataclass
class JobConfig:
    """Configuration for a scheduled job."""
    name: str
    skill: str
    schedule: str
    channel: str
    enabled: bool
    job_type: str  # "cron" or "interval"
    whatsapp: bool = False  # Also send to WhatsApp
    exempt_quiet_hours: bool = False  # Run even during quiet hours (23:00-06:00)


class PeterbotScheduler:
    """Scheduler that reads SCHEDULE.md and executes skills via Claude Code."""

    # Job execution configuration
    JOB_TIMEOUT_SECONDS = 180  # 3 minutes max per job
    MAX_QUEUED_JOBS = 3  # Max jobs to queue when busy

    def __init__(self, bot, scheduler: AsyncIOScheduler, peterbot_channel_id: int):
        """Initialize scheduler.

        Args:
            bot: Discord bot instance
            scheduler: APScheduler instance
            peterbot_channel_id: Channel ID for #peterbot
        """
        self.bot = bot
        self.scheduler = scheduler
        self.schedule_path = Path(__file__).parent / "wsl_config" / "SCHEDULE.md"
        self.skills_path = Path(__file__).parent / "wsl_config" / "skills"
        self.peterbot_channel_id = peterbot_channel_id
        CHANNEL_IDS["#peterbot"] = peterbot_channel_id

        # Track registered job IDs for reload
        self._job_ids: list[str] = []

        # Data fetchers (injected from data_fetchers.py)
        self.data_fetchers: dict[str, Callable] = {}

        # Last job status for heartbeat
        self.last_job_status: dict[str, bool] = {}

        # Job overlap prevention
        self._job_executing: bool = False
        self._current_job_name: Optional[str] = None
        self._job_queue: list[JobConfig] = []
        self._job_lock = asyncio.Lock()

    def set_data_fetchers(self, fetchers: dict[str, Callable]):
        """Set data fetcher functions for skills."""
        self.data_fetchers = fetchers

    def load_schedule(self) -> int:
        """Load schedule from SCHEDULE.md and register jobs.

        Also generates skills manifest for Peter's awareness.

        Returns:
            Number of jobs registered
        """
        if not self.schedule_path.exists():
            logger.warning(f"SCHEDULE.md not found at {self.schedule_path}")
            return 0

        content = self.schedule_path.read_text(encoding="utf-8")
        jobs = self._parse_schedule_md(content)

        for job in jobs:
            if not job.enabled:
                logger.debug(f"Skipping disabled job: {job.name}")
                continue

            try:
                self._register_job(job)
            except Exception as e:
                logger.error(f"Failed to register job {job.name}: {e}")

        # Generate skills manifest
        self._generate_manifest()

        logger.info(f"Loaded {len(self._job_ids)} scheduled jobs from SCHEDULE.md")
        return len(self._job_ids)

    def reload_schedule(self) -> int:
        """Reload schedule - remove old jobs and register new ones.

        Returns:
            Number of jobs registered
        """
        # Remove existing jobs
        for job_id in self._job_ids:
            try:
                self.scheduler.remove_job(job_id)
            except Exception:
                pass  # Job may not exist

        self._job_ids.clear()

        # Load fresh schedule
        return self.load_schedule()

    def _parse_schedule_md(self, content: str) -> list[JobConfig]:
        """Parse SCHEDULE.md content into job configs.

        Expects markdown tables with columns:
        - Fixed Time: | Job | Skill | Schedule | Channel | Enabled |
        - Interval: | Job | Skill | Interval | Channel | Enabled |
        """
        jobs = []

        # Find Fixed Time Jobs section
        cron_match = re.search(
            r"## Fixed Time Jobs.*?\n\|.*?\n\|[-\s|]+\n((?:\|.*?\n)+)",
            content,
            re.DOTALL | re.IGNORECASE
        )
        if cron_match:
            for row in cron_match.group(1).strip().split("\n"):
                job = self._parse_table_row(row, "cron")
                if job:
                    jobs.append(job)

        # Find Interval Jobs section
        interval_match = re.search(
            r"## Interval Jobs.*?\n\|.*?\n\|[-\s|]+\n((?:\|.*?\n)+)",
            content,
            re.DOTALL | re.IGNORECASE
        )
        if interval_match:
            for row in interval_match.group(1).strip().split("\n"):
                job = self._parse_table_row(row, "interval")
                if job:
                    jobs.append(job)

        return jobs

    def _parse_table_row(self, row: str, job_type: str) -> Optional[JobConfig]:
        """Parse a markdown table row into JobConfig."""
        cols = [c.strip() for c in row.split("|") if c.strip()]
        if len(cols) < 5:
            return None

        name = cols[0]
        skill = cols[1]
        schedule = cols[2]
        channel = cols[3]
        enabled = cols[4].lower() in ("yes", "true", "1")

        # Check for WhatsApp flag (optional 6th column or in channel name)
        whatsapp = False
        if len(cols) > 5:
            whatsapp = cols[5].lower() in ("yes", "true", "1", "whatsapp")
        elif "+whatsapp" in channel.lower():
            whatsapp = True
            channel = channel.replace("+whatsapp", "").replace("+WhatsApp", "").strip()

        # Check for quiet hours exemption (!quiet suffix)
        exempt_quiet_hours = False
        if "!quiet" in channel.lower():
            exempt_quiet_hours = True
            channel = channel.replace("!quiet", "").replace("!Quiet", "").strip()

        return JobConfig(
            name=name,
            skill=skill,
            schedule=schedule,
            channel=channel,
            enabled=enabled,
            job_type=job_type,
            whatsapp=whatsapp,
            exempt_quiet_hours=exempt_quiet_hours
        )

    def _register_job(self, job: JobConfig):
        """Register a job with APScheduler."""
        # Generate unique job ID by including a hash of the schedule
        # This allows multiple jobs with the same skill but different schedules
        schedule_hash = hash(job.schedule) & 0xFFFF  # 16-bit hash
        job_id = f"peterbot_{job.skill}_{schedule_hash:04x}"

        if job.job_type == "cron":
            trigger = self._parse_cron_schedule(job.schedule)
        else:
            trigger = self._parse_interval_schedule(job.schedule)

        if not trigger:
            logger.warning(f"Could not parse schedule for {job.name}: {job.schedule}")
            return

        self.scheduler.add_job(
            self._execute_job,
            trigger,
            args=[job],
            id=job_id,
            replace_existing=True
        )

        self._job_ids.append(job_id)
        logger.debug(f"Registered job: {job.name} ({job.skill}) - {job.schedule}")

    def _parse_cron_schedule(self, schedule: str) -> Optional[CronTrigger]:
        """Parse cron schedule string to APScheduler trigger.

        Formats supported:
        - "07:00 UK" -> 7am UK time
        - "09:00,11:00,13:00 UK" -> multiple times
        - "Mon-Wed,Fri 08:10 UK" -> specific days
        - "Sunday 09:00 UK" -> weekly
        - "1st 09:00 UK" -> monthly
        - "hourly UK" -> every hour at :00
        - "half-hourly UK" -> every 30 mins at :00 and :30
        """
        schedule = schedule.strip()

        # Extract timezone (default UK)
        tz = UK_TZ
        if " UK" in schedule:
            schedule = schedule.replace(" UK", "").strip()

        # Hourly with optional offset: "hourly" or "hourly+3" (at :03)
        hourly_match = re.match(r"hourly(?:\+(\d+))?", schedule.lower())
        if hourly_match:
            offset = int(hourly_match.group(1) or 0)
            return CronTrigger(hour="*", minute=offset, timezone=tz)

        # Half-hourly with optional offset: "half-hourly" or "half-hourly+1" (at :01 and :31)
        half_hourly_match = re.match(r"half-hourly(?:\+(\d+))?", schedule.lower())
        if half_hourly_match:
            offset = int(half_hourly_match.group(1) or 0)
            return CronTrigger(hour="*", minute=f"{offset},{30+offset}", timezone=tz)

        # Monthly: "1st 09:00"
        if schedule.startswith("1st "):
            time_part = schedule[4:]
            hour, minute = self._parse_time(time_part)
            if hour is not None:
                return CronTrigger(day=1, hour=hour, minute=minute, timezone=tz)

        # Weekly: "Sunday 09:00", "Mon 09:00"
        day_match = re.match(r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\d{1,2}:\d{2})", schedule, re.I)
        if day_match:
            day_name = day_match.group(1).lower()[:3]
            day_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
            day_of_week = day_map.get(day_name, 0)
            hour, minute = self._parse_time(day_match.group(2))
            if hour is not None:
                return CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute, timezone=tz)

        # Specific days: "Mon-Wed,Fri 08:10" or "Mon,Tue,Thu,Fri 14:55"
        days_match = re.match(r"([A-Za-z,\-]+)\s+(\d{1,2}:\d{2})", schedule)
        if days_match:
            days_str = days_match.group(1)
            hour, minute = self._parse_time(days_match.group(2))
            if hour is not None:
                day_of_week = self._parse_days(days_str)
                return CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute, timezone=tz)

        # Multiple times: "09:00,11:00,13:00"
        if "," in schedule and ":" in schedule:
            times = [t.strip() for t in schedule.split(",")]
            hours = []
            minute = 0
            for t in times:
                h, m = self._parse_time(t)
                if h is not None:
                    hours.append(h)
                    minute = m  # Use last minute value
            if hours:
                return CronTrigger(hour=",".join(map(str, hours)), minute=minute, timezone=tz)

        # Simple time: "07:00"
        hour, minute = self._parse_time(schedule)
        if hour is not None:
            return CronTrigger(hour=hour, minute=minute, timezone=tz)

        return None

    def _parse_interval_schedule(self, schedule: str) -> Optional[IntervalTrigger]:
        """Parse interval schedule string.

        Formats: "30m", "60m", "2h", "1h"
        """
        schedule = schedule.strip().lower()

        # Extract hours
        hours_match = re.match(r"(\d+)h", schedule)
        if hours_match:
            return IntervalTrigger(hours=int(hours_match.group(1)))

        # Extract minutes
        minutes_match = re.match(r"(\d+)m", schedule)
        if minutes_match:
            return IntervalTrigger(minutes=int(minutes_match.group(1)))

        return None

    def _parse_time(self, time_str: str) -> tuple[Optional[int], int]:
        """Parse time string like "07:00" or "7:00"."""
        match = re.match(r"(\d{1,2}):(\d{2})", time_str)
        if match:
            return int(match.group(1)), int(match.group(2))
        return None, 0

    def _parse_days(self, days_str: str) -> str:
        """Parse day string like "Mon-Wed,Fri" to APScheduler format."""
        day_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
        result_days = set()

        parts = days_str.lower().split(",")
        for part in parts:
            part = part.strip()
            if "-" in part:
                # Range: "Mon-Wed"
                start, end = part.split("-")
                start_num = day_map.get(start[:3], 0)
                end_num = day_map.get(end[:3], 0)
                for d in range(start_num, end_num + 1):
                    result_days.add(d)
            else:
                # Single day: "Fri"
                day_num = day_map.get(part[:3])
                if day_num is not None:
                    result_days.add(day_num)

        return ",".join(map(str, sorted(result_days)))

    def _is_quiet_hours(self) -> bool:
        """Check if current time is in quiet hours (23:00-06:00 UK)."""
        now = datetime.now(UK_TZ)
        return now.hour >= QUIET_START or now.hour < QUIET_END

    async def _execute_job(self, job: JobConfig):
        """Execute a scheduled job via Claude Code with overlap prevention.

        If another job is executing, queues this job (up to MAX_QUEUED_JOBS).
        After completion, processes any queued jobs.
        """
        # Skip during quiet hours (unless exempt)
        if self._is_quiet_hours() and not job.exempt_quiet_hours:
            logger.debug(f"Skipping {job.name} during quiet hours")
            return

        # Check for job overlap
        async with self._job_lock:
            if self._job_executing:
                # Another job is running - queue this one
                if len(self._job_queue) < self.MAX_QUEUED_JOBS:
                    self._job_queue.append(job)
                    logger.info(f"Queued job {job.name} (queue size: {len(self._job_queue)}, current: {self._current_job_name})")
                else:
                    logger.warning(f"Job queue full, dropping job: {job.name}")
                return

            # Mark as executing
            self._job_executing = True
            self._current_job_name = job.name

        try:
            await self._execute_job_internal(job)
        finally:
            # Mark as complete and process queue
            async with self._job_lock:
                self._job_executing = False
                self._current_job_name = None

                # Process queued jobs
                if self._job_queue:
                    next_job = self._job_queue.pop(0)
                    logger.info(f"Processing queued job: {next_job.name} (remaining: {len(self._job_queue)})")
                    # Schedule next job to run immediately (don't block current completion)
                    asyncio.create_task(self._execute_job(next_job))

    async def _execute_job_internal(self, job: JobConfig):
        """Internal job execution with timeout.

        1. Pre-fetch data if needed
        2. Load skill
        3. Send to Claude Code (with timeout)
        4. Post to channel(s) with optional file attachments
        """
        import time

        # Import health tracker for metrics
        try:
            from jobs.claude_code_health import get_health_tracker
            from .parser import is_garbage_response
            health_tracker = get_health_tracker()
        except ImportError:
            health_tracker = None
            is_garbage_response = None

        logger.info(f"Executing scheduled job: {job.name} ({job.skill})")

        # Generate job_id matching the API parser (lowercase, hyphens)
        job_id = job.skill.lower().replace(" ", "-").replace("_", "-")
        execution_id = None

        # Record job start in dashboard database
        if JOB_HISTORY_ENABLED:
            try:
                execution_id = record_job_start(job_id)
                logger.debug(f"Recorded job start for {job_id}, execution_id={execution_id}")
            except Exception as e:
                logger.warning(f"Failed to record job start: {e}")
        start_time = time.time()

        try:
            # 1. Pre-fetch data if skill has a fetcher
            data = None
            files_to_attach = []  # List of (filepath, filename) tuples
            if job.skill in self.data_fetchers:
                try:
                    fetcher = self.data_fetchers[job.skill]
                    data = await fetcher()
                    logger.debug(f"Pre-fetched data for {job.skill}")

                    # Extract file attachments if present
                    if isinstance(data, dict) and "files_to_attach" in data:
                        files_to_attach = data.pop("files_to_attach", [])
                        logger.debug(f"Found {len(files_to_attach)} files to attach")
                except Exception as e:
                    logger.warning(f"Data fetch failed for {job.skill}: {e}")

            # 2. Load skill
            skill_content = self._load_skill(job.skill)
            if not skill_content:
                logger.error(f"Skill not found: {job.skill}")
                self.last_job_status[job.skill] = False
                if health_tracker:
                    health_tracker.record_job_result(
                        job.name, success=False, error="skill not found"
                    )
                # Record job completion (failure)
                if JOB_HISTORY_ENABLED:
                    try:
                        record_job_complete(job_id, success=False, error="skill not found", execution_id=execution_id)
                    except Exception as e:
                        logger.warning(f"Failed to record job complete: {e}")
                return

            # 3. Build context
            context = self._build_skill_context(job, skill_content, data)

            # 4. Send to Claude Code with timeout
            try:
                response = await asyncio.wait_for(
                    self._send_to_claude_code(context),
                    timeout=self.JOB_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                duration = time.time() - start_time
                logger.error(f"Job {job.name} timed out after {duration:.1f}s")

                # Send Ctrl+C to cancel stuck operation
                from domains.claude_code.tools import _tmux
                from .config import PETERBOT_SESSION
                _tmux("send-keys", "-t", PETERBOT_SESSION, "C-c")

                self.last_job_status[job.skill] = False
                if health_tracker:
                    health_tracker.record_job_result(
                        job.name, success=False, duration_seconds=duration,
                        error=f"timeout after {self.JOB_TIMEOUT_SECONDS}s"
                    )
                # Record job completion (timeout)
                if JOB_HISTORY_ENABLED:
                    try:
                        record_job_complete(job_id, success=False, error=f"timeout after {self.JOB_TIMEOUT_SECONDS}s", execution_id=execution_id)
                    except Exception as e:
                        logger.warning(f"Failed to record job complete: {e}")
                return

            duration = time.time() - start_time

            # 5. Check for NO_REPLY
            if "NO_REPLY" in response:
                logger.info(f"Job {job.name} returned NO_REPLY, suppressing output")
                self.last_job_status[job.skill] = True
                if health_tracker:
                    health_tracker.record_job_result(
                        job.name, success=True, duration_seconds=duration,
                        response_length=len(response)
                    )
                # Record job completion (success - NO_REPLY is still success)
                if JOB_HISTORY_ENABLED:
                    try:
                        record_job_complete(job_id, success=True, output="NO_REPLY", execution_id=execution_id)
                    except Exception as e:
                        logger.warning(f"Failed to record job complete: {e}")
                return

            # 6. Check for garbage response
            is_garbage = False
            garbage_patterns = []
            if is_garbage_response and response:
                is_garbage, garbage_patterns = is_garbage_response(response)
                if is_garbage:
                    logger.warning(f"Garbage response detected for {job.name}: {garbage_patterns}")

            # 7. Post to Discord channel (with optional file attachments)
            if response and not is_garbage:
                await self._post_to_channel(job, response, files=files_to_attach)
                self.last_job_status[job.skill] = True

                # 8. Capture to memory (async, fire-and-forget)
                asyncio.create_task(self._capture_to_memory(job, response))

                if health_tracker:
                    health_tracker.record_job_result(
                        job.name, success=True, duration_seconds=duration,
                        response_length=len(response)
                    )
                # Record job completion (success)
                if JOB_HISTORY_ENABLED:
                    try:
                        record_job_complete(job_id, success=True, output=response[:500] if response else None, execution_id=execution_id)
                    except Exception as e:
                        logger.warning(f"Failed to record job complete: {e}")
            elif is_garbage:
                logger.warning(f"Suppressed garbage response for {job.name}")
                self.last_job_status[job.skill] = False
                if health_tracker:
                    health_tracker.record_job_result(
                        job.name, success=False, duration_seconds=duration,
                        response_length=len(response), is_garbage=True,
                        garbage_patterns=garbage_patterns
                    )
                # Record job completion (garbage)
                if JOB_HISTORY_ENABLED:
                    try:
                        record_job_complete(job_id, success=False, error=f"garbage response: {garbage_patterns}", execution_id=execution_id)
                    except Exception as e:
                        logger.warning(f"Failed to record job complete: {e}")
            else:
                logger.warning(f"No response from Claude Code for {job.name}")
                self.last_job_status[job.skill] = False
                if health_tracker:
                    health_tracker.record_job_result(
                        job.name, success=False, duration_seconds=duration,
                        error="empty response"
                    )
                # Record job completion (empty response)
                if JOB_HISTORY_ENABLED:
                    try:
                        record_job_complete(job_id, success=False, error="empty response", execution_id=execution_id)
                    except Exception as e:
                        logger.warning(f"Failed to record job complete: {e}")

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Job execution failed for {job.name}: {e}")
            self.last_job_status[job.skill] = False
            if health_tracker:
                health_tracker.record_job_result(
                    job.name, success=False, duration_seconds=duration,
                    error=str(e)
                )
            # Record job completion (exception)
            if JOB_HISTORY_ENABLED:
                try:
                    record_job_complete(job_id, success=False, error=str(e), execution_id=execution_id)
                except Exception as rec_err:
                    logger.warning(f"Failed to record job complete: {rec_err}")

    def _load_skill(self, skill_name: str) -> Optional[str]:
        """Load skill content from skills folder."""
        skill_path = self.skills_path / skill_name / "SKILL.md"
        if skill_path.exists():
            return skill_path.read_text(encoding="utf-8")

        # Try without folder structure
        skill_path = self.skills_path / f"{skill_name}.md"
        if skill_path.exists():
            return skill_path.read_text(encoding="utf-8")

        return None

    def _generate_manifest(self) -> dict:
        """Generate skills manifest from all SKILL.md files.

        Scans skills directory, parses YAML frontmatter, and writes manifest.json.
        Peter loads this manifest to know available skills and their triggers.

        Returns:
            The generated manifest dict
        """
        manifest = {}

        # Scan all skill directories
        if not self.skills_path.exists():
            logger.warning(f"Skills path not found: {self.skills_path}")
            return manifest

        for skill_dir in self.skills_path.iterdir():
            if not skill_dir.is_dir():
                continue
            if skill_dir.name.startswith("_"):
                continue  # Skip template

            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue

            try:
                content = skill_file.read_text(encoding="utf-8")
                frontmatter = self._parse_skill_frontmatter(content)

                if frontmatter:
                    skill_name = frontmatter.get("name", skill_dir.name)
                    manifest[skill_name] = {
                        "triggers": frontmatter.get("trigger", []),
                        "conversational": frontmatter.get("conversational", True),
                        "scheduled": frontmatter.get("scheduled", False),
                        "description": frontmatter.get("description", ""),
                        "channel": frontmatter.get("channel", "#peterbot"),
                    }
                    logger.debug(f"Added skill to manifest: {skill_name}")

            except Exception as e:
                logger.warning(f"Failed to parse skill {skill_dir.name}: {e}")

        # Write manifest.json
        manifest_path = self.skills_path / "manifest.json"
        try:
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
            logger.info(f"Generated skills manifest with {len(manifest)} skills")
        except Exception as e:
            logger.error(f"Failed to write manifest: {e}")

        return manifest

    def _parse_skill_frontmatter(self, content: str) -> Optional[dict]:
        """Parse YAML frontmatter from SKILL.md content.

        Args:
            content: Full SKILL.md file content

        Returns:
            Parsed frontmatter dict, or None if not found
        """
        # Match --- delimited frontmatter
        match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if not match:
            return None

        try:
            return yaml.safe_load(match.group(1))
        except yaml.YAMLError as e:
            logger.warning(f"YAML parse error in skill frontmatter: {e}")
            return None

    def _build_skill_context(self, job: JobConfig, skill_content: str, data: Optional[dict]) -> str:
        """Build full context for Claude Code execution."""
        now = datetime.now(UK_TZ)

        parts = [
            f"# Scheduled Job: {job.name}",
            f"Time: {now.strftime('%A, %d %B %Y %H:%M')} UK",
            "",
            "## Skill Instructions",
            skill_content,
        ]

        if data:
            parts.extend([
                "",
                "## Pre-fetched Data",
                "```json",
                json.dumps(data, indent=2, default=str),
                "```",
            ])

        parts.extend([
            "",
            "## CRITICAL OUTPUT RULES",
            "- ONLY output the formatted response as specified in the skill instructions above",
            "- Do NOT show your reasoning, thinking, calculations, or explanations",
            "- Do NOT respond to any previous conversation or memory context",
            "- Do NOT add greetings, commentary, or anything outside the skill's output format",
            "- Start your response DIRECTLY with the emoji/header (e.g., 🌅 **09:00 Check-in**)",
            "- If there's nothing to report, respond with just: NO_REPLY",
            f"- Target channel: {job.channel}",
        ])

        return "\n".join(parts)

    async def _send_to_claude_code(self, context: str, retry_on_empty: bool = True) -> str:
        """Send context to Claude Code session and get response.

        Uses the same mechanism as peterbot router.
        Acquires session lock to prevent concurrent access with conversations.

        Args:
            context: Full context string to send
            retry_on_empty: If True, retry once if response is empty (default True)

        Returns:
            Extracted response string, or empty string on failure
        """
        # Import router module to modify _last_channel_id (not just the variable)
        from . import router as router_module
        from .router import (
            ensure_session,
            write_context_file,
            generate_context_filename,
            cleanup_context_file,
            send_to_session,
            wait_for_response,
            wait_for_clear,
            extract_new_response,
            get_session_screen,
            _session_lock,
        )
        from domains.claude_code.tools import _tmux
        from .config import PETERBOT_SESSION

        # Ensure session exists
        success, error = await ensure_session()
        if not success:
            logger.error(f"Failed to create Claude Code session: {error}")
            return ""

        # CRITICAL SECTION - acquire lock to prevent concurrent tmux access
        async with _session_lock:
            logger.debug("Acquired session lock for scheduled job")

            # Always clear context before scheduled jobs (prevents contamination from conversations)
            logger.debug("Clearing context for scheduled job isolation")
            _tmux("send-keys", "-t", PETERBOT_SESSION, "/clear", "Enter")
            # Wait for clear to actually complete (uses CLEAR_TIMEOUT from config, default 8s)
            if not await wait_for_clear():
                logger.warning("Clear may not have completed for scheduled job, proceeding anyway")

            # Capture before state
            screen_before = get_session_screen()

            # Write context to UNIQUE file (prevents cross-contamination with conversations)
            import uuid
            operation_id = uuid.uuid4().hex[:8]
            context_filepath = generate_context_filename(operation_id)
            context_filename = f"context_{operation_id}.md"

            written_path = write_context_file(context, context_filepath)
            if not written_path:
                logger.error("Failed to write context file for scheduled job")
                return ""

            # Use the same prompt marker as router for extract_new_response to work
            send_to_session(f"Read {context_filename} and respond")

            # Wait for response with content validation (prevents premature return after /clear timeout)
            raw_response = await wait_for_response(
                timeout=120,
                stable_threshold=5,
                expect_content=True,
                context_filename=context_filename,
            )

            # Extract response
            response = extract_new_response(screen_before, raw_response)

            # Retry once if response is empty (likely /clear didn't complete properly)
            if not response.strip() and retry_on_empty:
                logger.warning("Empty response detected for scheduled job, attempting retry...")

                # Cancel any stuck operation
                _tmux("send-keys", "-t", PETERBOT_SESSION, "C-c")
                await asyncio.sleep(0.5)

                # Clear with longer timeout
                _tmux("send-keys", "-t", PETERBOT_SESSION, "/clear", "Enter")
                if not await wait_for_clear(timeout=10.0):
                    logger.error("Clear failed on retry attempt")
                    # Continue anyway - try to send

                # Generate new context file for retry
                retry_id = uuid.uuid4().hex[:8]
                retry_filepath = generate_context_filename(retry_id)
                retry_filename = f"context_{retry_id}.md"

                write_context_file(context, retry_filepath)
                screen_before = get_session_screen()
                send_to_session(f"Read {retry_filename} and respond")

                raw_response = await wait_for_response(
                    timeout=120,
                    stable_threshold=5,
                    expect_content=True,
                    context_filename=retry_filename,
                )
                response = extract_new_response(screen_before, raw_response)

                # Cleanup retry context file
                cleanup_context_file(retry_filepath)

                if response.strip():
                    logger.info(f"Retry successful, got {len(response)} char response")
                else:
                    logger.error("Retry also returned empty response")

            # Cleanup original context file (prevents accumulation)
            cleanup_context_file(context_filepath)

        # CRITICAL: Reset channel tracking after scheduled job
        # This forces the next conversation to issue /clear (channel switch detection)
        router_module._last_channel_id = None
        logger.debug("Released session lock for scheduled job, reset _last_channel_id")
        return response

    async def _post_to_channel(self, job: JobConfig, message: str, files: list = None):
        """Post message to Discord channel (and optionally WhatsApp).

        Supports dual-channel routing via markers:
        - ---HEARTBEAT--- content goes to job's configured channel
        - ---PETERBOT--- content goes to #peterbot

        Args:
            job: Job configuration
            message: Message content
            files: Optional list of (filepath, filename) tuples for attachments
        """
        files = files or []

        # Check for dual-channel markers
        if "---HEARTBEAT---" in message and "---PETERBOT---" in message:
            await self._post_dual_channel(job, message, files=files)
            return

        # Standard single-channel post
        await self._post_single_channel(job.channel, message, job, files=files)

        # WhatsApp (if configured)
        if job.whatsapp:
            await self._send_whatsapp(message)

    async def _post_dual_channel(self, job: JobConfig, message: str, files: list = None):
        """Handle dual-channel output with markers.

        Format:
        ---HEARTBEAT---
        [status content]
        ---PETERBOT---
        [detailed content]

        Args:
            job: Job configuration
            message: Message content with markers
            files: Optional list of (filepath, filename) tuples for attachments
        """
        files = files or []
        try:
            # Split by markers
            parts = message.split("---PETERBOT---")
            heartbeat_part = parts[0].replace("---HEARTBEAT---", "").strip()
            peterbot_part = parts[1].strip() if len(parts) > 1 else ""

            # Post heartbeat status to configured channel (e.g., #peter-heartbeat)
            if heartbeat_part:
                await self._post_single_channel(job.channel, heartbeat_part, job)
                logger.info(f"Posted {job.name} status to {job.channel}")

            # Post detailed content to #peterbot (with file attachments)
            if peterbot_part:
                await self._post_single_channel("#peterbot", peterbot_part, job, files=files)
                logger.info(f"Posted {job.name} content to #peterbot")

        except Exception as e:
            logger.error(f"Dual-channel post failed: {e}")
            # Fallback: post everything to configured channel
            clean_message = message.replace("---HEARTBEAT---", "").replace("---PETERBOT---", "\n\n")
            await self._post_single_channel(job.channel, clean_message, job, files=files)

    async def _post_single_channel(self, channel_name: str, message: str, job: JobConfig, files: list = None):
        """Post message to a single Discord channel.

        Args:
            channel_name: Target channel name (e.g., "#peterbot")
            message: Message content
            job: Job configuration
            files: Optional list of (filepath, filename) tuples for attachments
        """
        import discord
        import os

        files = files or []

        channel_id = CHANNEL_IDS.get(channel_name)
        if not channel_id:
            logger.error(f"Unknown channel: {channel_name}")
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception as e:
                logger.error(f"Could not find channel {channel_name} ({channel_id}): {e}")
                return

        # Process through Response Pipeline (sanitise → classify → format → chunk)
        processed = process_response(message, {'user_prompt': f'[Scheduled: {job.skill}]'})

        # Build Discord file attachments
        discord_files = []
        for filepath, filename in files:
            if os.path.exists(filepath):
                try:
                    discord_files.append(discord.File(filepath, filename=filename))
                    logger.debug(f"Prepared file attachment: {filename}")
                except Exception as e:
                    logger.warning(f"Failed to prepare file {filepath}: {e}")

        # Send chunks (pipeline handles Discord 2000 char limit)
        for i, chunk in enumerate(processed.chunks):
            if not chunk.strip():
                continue

            # First chunk: include embed and file attachments
            if i == 0:
                kwargs = {}
                if processed.embed:
                    kwargs["embed"] = discord.Embed.from_dict(processed.embed)
                if discord_files:
                    kwargs["files"] = discord_files
                    discord_files = []  # Only attach to first chunk

                await channel.send(chunk, **kwargs)
            else:
                await channel.send(chunk)

        # Send additional embeds
        for embed_data in processed.embeds:
            embed_obj = discord.Embed.from_dict(embed_data)
            await channel.send(embed=embed_obj)

        logger.debug(f"Posted to {channel_name} (type={processed.response_type.value}, files={len(files)})")

    async def _capture_to_memory(self, job: JobConfig, response: str):
        """Capture scheduled job output to memory.

        Args:
            job: The job that was executed
            response: The output response (not NO_REPLY)
        """
        from . import memory

        # Session ID groups by skill for later retrieval
        # e.g., "What did hydration report yesterday?"
        session_id = f"scheduled-{job.skill}"

        # Prompt describes the scheduled execution
        prompt = f"[Scheduled job: {job.name}] Executed at {datetime.now(UK_TZ).strftime('%H:%M')}"

        try:
            await memory.capture_message_pair(session_id, prompt, response)
            logger.debug(f"Memory captured for scheduled job: {job.skill}")
        except Exception as e:
            logger.warning(f"Failed to capture scheduled job to memory: {e}")

    async def _send_whatsapp(self, message: str):
        """Send message via Twilio WhatsApp."""
        import asyncio

        try:
            from config import (
                TWILIO_ACCOUNT_SID,
                TWILIO_AUTH_TOKEN,
                TWILIO_WHATSAPP_FROM
            )

            if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM]):
                logger.debug("Twilio not configured, skipping WhatsApp")
                return

            # Convert Discord bold (**text**) to WhatsApp bold (*text*)
            whatsapp_message = message.replace("**", "*")

            from twilio.rest import Client as TwilioClient

            # Recipients for school run messages
            recipients = ["+447856182831", "+447855620978"]

            def send_to_recipients():
                """Sync function to send WhatsApp messages."""
                client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                results = []
                for recipient in recipients:
                    try:
                        client.messages.create(
                            body=whatsapp_message,
                            from_=f"whatsapp:{TWILIO_WHATSAPP_FROM}",
                            to=f"whatsapp:{recipient}"
                        )
                        results.append((recipient, True, None))
                    except Exception as e:
                        results.append((recipient, False, str(e)))
                return results

            # Run sync Twilio client in thread to avoid blocking event loop
            results = await asyncio.to_thread(send_to_recipients)

            for recipient, success, error in results:
                if success:
                    logger.info(f"Sent WhatsApp to {recipient}")
                else:
                    logger.error(f"WhatsApp send failed to {recipient}: {error}")

        except ImportError:
            logger.debug("Twilio not installed")
        except Exception as e:
            logger.error(f"WhatsApp error: {e}")

    def get_job_status(self) -> dict[str, bool]:
        """Get status of last job executions for heartbeat."""
        return self.last_job_status.copy()

    async def _execute_job_manual(self, job: JobConfig, channel_id: int):
        """Execute a job manually (bypasses quiet hours, posts to specified channel).

        Used by !skill command for manual testing.

        Args:
            job: JobConfig with skill info
            channel_id: Channel to post response to
        """
        logger.info(f"Manual skill execution: {job.skill}")

        try:
            # 1. Pre-fetch data if skill has a fetcher
            data = None
            files_to_attach = []  # List of (filepath, filename) tuples
            if job.skill in self.data_fetchers:
                try:
                    fetcher = self.data_fetchers[job.skill]
                    data = await fetcher()
                    logger.debug(f"Pre-fetched data for {job.skill}")

                    # Extract file attachments if present (same as scheduled jobs)
                    if isinstance(data, dict) and "files_to_attach" in data:
                        files_to_attach = data.pop("files_to_attach", [])
                        logger.debug(f"Found {len(files_to_attach)} files to attach")
                except Exception as e:
                    logger.warning(f"Data fetch failed for {job.skill}: {e}")

            # 2. Load skill
            skill_content = self._load_skill(job.skill)
            if not skill_content:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    await channel.send(f"❌ Skill not found: `{job.skill}`")
                return

            # 3. Build context (manual execution marker)
            context = self._build_skill_context_manual(job, skill_content, data)

            # 4. Send to Claude Code
            response = await self._send_to_claude_code(context)

            # 5. Get target channel
            channel = self.bot.get_channel(channel_id)
            if not channel:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except Exception as e:
                    logger.error(f"Could not find channel {channel_id}: {e}")
                    return

            # 6. Check for NO_REPLY
            if "NO_REPLY" in response:
                await channel.send(f"✅ Skill `{job.skill}` completed with NO_REPLY (nothing to report)")
                self.last_job_status[job.skill] = True
                return

            # 7. Post response with Phase 7 marker
            if response:
                import discord
                import os

                header = f"**[Phase 7 Skill: {job.skill}]**\n\n"

                # Process through Response Pipeline
                processed = process_response(response, {'user_prompt': f'[Manual: {job.skill}]'})

                # Prepare file attachments
                discord_files = []
                for filepath, filename in files_to_attach:
                    if os.path.exists(filepath):
                        discord_files.append(discord.File(filepath, filename=filename))
                        logger.debug(f"Attaching file: {filename}")

                # Send header first
                await channel.send(header.strip())

                # Send chunks (pipeline handles Discord 2000 char limit)
                for i, chunk in enumerate(processed.chunks):
                    if not chunk.strip():
                        continue

                    if i == 0 and processed.embed:
                        embed_obj = discord.Embed.from_dict(processed.embed)
                        # Attach files to first chunk
                        if discord_files:
                            await channel.send(chunk, embed=embed_obj, files=discord_files)
                            discord_files = []  # Clear after sending
                        else:
                            await channel.send(chunk, embed=embed_obj)
                    else:
                        # Attach files to first chunk if no embed
                        if i == 0 and discord_files:
                            await channel.send(chunk, files=discord_files)
                            discord_files = []
                        else:
                            await channel.send(chunk)

                # Send any remaining files if no chunks were sent
                if discord_files:
                    await channel.send(files=discord_files)

                # Send additional embeds
                for embed_data in processed.embeds:
                    embed_obj = discord.Embed.from_dict(embed_data)
                    await channel.send(embed=embed_obj)

                self.last_job_status[job.skill] = True
                logger.debug(f"Manual skill response: type={processed.response_type.value}")

                # 8. Capture to memory (async, fire-and-forget)
                asyncio.create_task(self._capture_to_memory(job, response))
            else:
                await channel.send(f"⚠️ Skill `{job.skill}` returned no response")
                self.last_job_status[job.skill] = False

        except Exception as e:
            logger.error(f"Manual skill execution failed for {job.skill}: {e}")
            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.send(f"❌ Skill `{job.skill}` failed: {e}")

    def _build_skill_context_manual(self, job: JobConfig, skill_content: str, data: Optional[dict]) -> str:
        """Build context for manual skill execution."""
        now = datetime.now(UK_TZ)

        parts = [
            f"# Manual Skill Execution: {job.skill}",
            f"Triggered manually via !skill command",
            f"Time: {now.strftime('%A, %d %B %Y %H:%M')} UK",
            "",
            "## Skill Instructions",
            skill_content,
        ]

        if data:
            parts.extend([
                "",
                "## Pre-fetched Data",
                "```json",
                json.dumps(data, indent=2, default=str),
                "```",
            ])

        parts.extend([
            "",
            "## CRITICAL OUTPUT RULES",
            "- ONLY output the formatted response as specified in the skill instructions above",
            "- Do NOT show your reasoning, thinking, calculations, or explanations",
            "- Do NOT respond to any previous conversation or memory context",
            "- Do NOT add greetings, commentary, or anything outside the skill's output format",
            "- Start your response DIRECTLY with the emoji/header (e.g., 🌅 **09:00 Check-in**)",
            "- If there's genuinely nothing to report, respond with just: NO_REPLY",
        ])

        return "\n".join(parts)
