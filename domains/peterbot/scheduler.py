"""Peterbot scheduler - SCHEDULE.md parsing and job execution.

Parses SCHEDULE.md markdown tables and registers jobs with APScheduler.
Jobs execute by routing skill context to Claude Code session.
"""

import asyncio
import json
import re
import yaml
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable, Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from logger import logger
from .response.pipeline import process as process_response
from .config import SECOND_BRAIN_SAVE_SKILLS

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
    "#alerts": 1466019126194606286,
}

# UK timezone
UK_TZ = ZoneInfo("Europe/London")

# Quiet hours (no jobs)
QUIET_START = 23  # 11pm
QUIET_END = 6     # 6am


# --- Reasoning Leak Detection ---
# Detects when a scheduled skill's output is internal narration/reasoning
# instead of actual formatted content for Discord.

# Patterns that indicate the response is reasoning, not output
_REASONING_PREFIXES = re.compile(
    r"^(?:"
    r"(?:Now |OK,? |Alright,? )?(?:let me|I(?:'ll| will| need to| should| can))"
    r"|(?:First|Next|Then),? (?:let me|I(?:'ll| will| need to))"
    r"|I(?:'m going to|'ve (?:completed|finished|updated|downloaded|run))"
    r"|Let me (?:update|run|check|fetch|download|process|create|search|source)"
    r"|(?:Running|Processing|Downloading|Fetching|Checking|Searching|Updating)"
    r"|The (?:script|optimizer|image|download|search|API) "
    r")",
    re.IGNORECASE,
)

def is_reasoning_leak(response: str, min_length: int = 200) -> bool:
    """Detect if a response looks like leaked internal reasoning.

    Returns True if the response is short AND starts with narration patterns,
    which indicates the model described its process instead of producing output.

    Long responses (>min_length chars) are assumed to contain real content
    even if they start with a reasoning-like sentence.
    """
    if not response or len(response.strip()) > min_length:
        return False
    first_line = response.strip().split("\n")[0]
    return bool(_REASONING_PREFIXES.match(first_line))


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
    whatsapp_target: str = ""  # "group", "chris", "abby", or "" (= chris+abby)
    exempt_quiet_hours: bool = False  # Run even during quiet hours (23:00-06:00)


class PeterbotScheduler:
    """Scheduler that reads SCHEDULE.md and executes skills via Claude Code."""

    # Job execution configuration
    JOB_TIMEOUT_SECONDS = 1200  # 20 minutes max per job
    MAX_QUEUED_JOBS = 10  # Max jobs to queue when busy

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

        # Trigger files for API-initiated actions
        self._reload_trigger_path = Path(__file__).parent.parent.parent / "data" / "schedule_reload.trigger"
        self._skill_run_trigger_path = Path(__file__).parent.parent.parent / "data" / "skill_run.trigger"

        # News article history log for deduplication
        self._news_history_path = Path(__file__).parent.parent.parent / "data" / "news_history.jsonl"

        # Active skill context for cross-channel injection (conversational jobs)
        self._active_skill_context_path = Path(__file__).parent.parent.parent / "data" / "active_skill_context.json"

    def set_data_fetchers(self, fetchers: dict[str, Callable]):
        """Set data fetcher functions for skills."""
        self.data_fetchers = fetchers

    def _save_news_history(self, response: str) -> None:
        """Append a successful news response to the history log."""
        entry = {
            "timestamp": datetime.now(UK_TZ).isoformat(),
            "response": response,
        }
        try:
            self._news_history_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._news_history_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.debug(f"News history write failed: {e}")

    def _load_news_history(self, days: int = 7) -> str:
        """Load recent news history for deduplication context.

        Returns a markdown section listing previously covered articles,
        or empty string if no history exists.
        """
        if not self._news_history_path.exists():
            return ""

        cutoff = datetime.now(UK_TZ) - timedelta(days=days)
        recent_entries = []

        try:
            with open(self._news_history_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        ts = datetime.fromisoformat(entry["timestamp"])
                        if ts >= cutoff:
                            recent_entries.append(entry)
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue
        except Exception as e:
            logger.debug(f"News history read failed: {e}")
            return ""

        if not recent_entries:
            return ""

        parts = [
            "## Previously Covered Articles (last 7 days)",
            "Do NOT repeat these stories. Find fresh news instead.",
            "",
        ]
        for entry in recent_entries:
            ts = datetime.fromisoformat(entry["timestamp"])
            parts.append(f"### {ts.strftime('%A %d %b %H:%M')}")
            parts.append(entry["response"])
            parts.append("")

        return "\n".join(parts)

    def _is_conversational_skill(self, skill_name: str) -> bool:
        """Check if a skill is marked conversational (expects follow-up replies)."""
        skill_path = self.skills_path / skill_name / "SKILL.md"
        if not skill_path.exists():
            return False
        try:
            content = skill_path.read_text(encoding="utf-8")
            frontmatter = self._parse_skill_frontmatter(content)
            return bool(frontmatter and frontmatter.get("conversational", False))
        except Exception:
            return False

    def _write_active_skill_context(self, job: JobConfig, skill_content: str) -> None:
        """Write active skill context for cross-channel injection.

        When a conversational scheduled job posts output, peter-channel needs
        the skill instructions to handle follow-up replies from Chris.
        This file bridges that gap.
        """
        context = {
            "skill": job.skill,
            "channel": job.channel,
            "timestamp": datetime.now(UK_TZ).isoformat(),
            "ttl_minutes": 60,
            "skill_content": skill_content,
        }
        try:
            self._active_skill_context_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._active_skill_context_path, "w", encoding="utf-8") as f:
                json.dump(context, f, indent=2)
            logger.info(f"Wrote active skill context for {job.skill}")
        except Exception as e:
            logger.warning(f"Failed to write active skill context: {e}")

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

    def start_reload_watcher(self):
        """Register a periodic check for API-triggered reload requests."""
        self.scheduler.add_job(
            self._check_reload_trigger,
            IntervalTrigger(seconds=10),
            id="__reload_watcher",
            max_instances=1,
            replace_existing=True,
        )
        logger.info("Schedule reload watcher started (checks every 10s)")

    async def _check_reload_trigger(self):
        """Check for trigger files from Hadley API and process if found."""
        # Check for schedule reload
        if self._reload_trigger_path.exists():
            try:
                reason = self._reload_trigger_path.read_text(encoding="utf-8").strip()
                self._reload_trigger_path.unlink()
                logger.info(f"Schedule reload triggered via API: {reason}")
                job_count = self.reload_schedule()
                logger.info(f"Schedule reloaded: {job_count} jobs registered")
            except Exception as e:
                logger.error(f"Failed to process reload trigger: {e}")

        # Check for skill run trigger
        if self._skill_run_trigger_path.exists():
            try:
                content = self._skill_run_trigger_path.read_text(encoding="utf-8").strip()
                self._skill_run_trigger_path.unlink()
                # Format: skill_name|channel_name (e.g. "tutor-email-parser|#peterbot")
                parts = content.split("|", 1)
                skill_name = parts[0].strip()
                channel = parts[1].strip() if len(parts) > 1 else "#peterbot"
                logger.info(f"Skill run triggered via API: {skill_name} -> {channel}")

                # Build a job config and execute
                import re as _re
                whatsapp = False
                whatsapp_target = ""
                wa_match = _re.search(r'\+[Ww]hats[Aa]pp(?::(\w+))?', channel)
                if wa_match:
                    whatsapp = True
                    whatsapp_target = (wa_match.group(1) or "").lower()
                    channel = channel[:wa_match.start()] + channel[wa_match.end():]
                    channel = channel.strip()

                job = JobConfig(
                    name=f"Manual: {skill_name}",
                    skill=skill_name,
                    schedule="manual",
                    channel=channel,
                    enabled=True,
                    job_type="manual",
                    whatsapp=whatsapp,
                    whatsapp_target=whatsapp_target,
                    exempt_quiet_hours=True,  # Manual runs always bypass quiet hours
                )
                await self._execute_job_internal(job)
            except Exception as e:
                logger.error(f"Failed to process skill run trigger: {e}")

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
        # Format: +WhatsApp (both), +WhatsApp:group (group), +WhatsApp:chris (chris only)
        whatsapp = False
        whatsapp_target = ""
        if len(cols) > 5:
            whatsapp = cols[5].lower() in ("yes", "true", "1", "whatsapp")
        else:
            import re as _re
            wa_match = _re.search(r'\+[Ww]hats[Aa]pp(?::(\w+))?', channel)
            if wa_match:
                whatsapp = True
                whatsapp_target = (wa_match.group(1) or "").lower()
                channel = channel[:wa_match.start()] + channel[wa_match.end():]
                channel = channel.strip()

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
            whatsapp_target=whatsapp_target,
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
            replace_existing=True,
            max_instances=1,
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

    # --- Pause checking (cached 60s) ---
    _pause_cache: list | None = None
    _pause_cache_time: float = 0

    def _is_skill_paused(self, skill: str) -> bool:
        """Check if a skill is currently paused (cached for 60s)."""
        import time as _time

        now_mono = _time.monotonic()
        if self._pause_cache is None or (now_mono - self._pause_cache_time) > 60:
            self._pause_cache = self._load_pauses()
            self._pause_cache_time = now_mono

        now = datetime.now(UK_TZ)
        for pause in self._pause_cache:
            try:
                from dateutil.parser import parse as parse_dt
                resume = parse_dt(pause["resume_at"])
                if resume.tzinfo is None:
                    resume = resume.replace(tzinfo=UK_TZ)
                if resume <= now:
                    continue
                if "*" in pause.get("skills", []) or skill in pause.get("skills", []):
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    def _load_pauses() -> list:
        """Load active pauses from data/schedule_pauses.json."""
        pauses_file = Path(__file__).parent.parent.parent / "data" / "schedule_pauses.json"
        if not pauses_file.exists():
            return []
        try:
            data = json.loads(pauses_file.read_text(encoding="utf-8"))
            return data.get("pauses", [])
        except (json.JSONDecodeError, OSError):
            return []

    async def _execute_job(self, job: JobConfig):
        """Execute a scheduled job via Claude Code with overlap prevention.

        If another job is executing, queues this job (up to MAX_QUEUED_JOBS).
        After completion, processes any queued jobs.
        """
        # Skip during quiet hours (unless exempt)
        if self._is_quiet_hours() and not job.exempt_quiet_hours:
            logger.debug(f"Skipping {job.name} during quiet hours")
            return

        # Skip if skill is paused
        if self._is_skill_paused(job.skill):
            logger.debug(f"Skipping {job.name} — skill '{job.skill}' is paused")
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

                    # Check for __skip__ signal — fetcher says don't invoke Claude
                    if isinstance(data, dict) and data.get("__skip__"):
                        reason = data.get("reason", "skip requested")
                        logger.info(f"Job {job.name} skipped by fetcher: {reason}")
                        self.last_job_status[job.skill] = True
                        if JOB_HISTORY_ENABLED:
                            try:
                                record_job_complete(job_id, success=True, output=f"SKIP: {reason}", execution_id=execution_id)
                            except Exception:
                                pass
                        return

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
                # JOBS_USE_CHANNEL=1 routes through persistent jobs-channel session
                # JOBS_USE_CHANNEL=0 (default) uses independent CLI process via router_v2
                import os
                _jobs_use_channel = os.environ.get("JOBS_USE_CHANNEL", "0") == "1"
                if _jobs_use_channel:
                    response = await self._send_to_jobs_channel(context, job=job)
                else:
                    response = await self._send_to_claude_code_v2(context, job=job)
            except asyncio.TimeoutError:
                duration = time.time() - start_time
                logger.error(f"Job {job.name} timed out after {duration:.1f}s")

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

            # 6b. Check for reasoning leak (model narrated its process instead of producing output)
            if not is_garbage and response and is_reasoning_leak(response):
                logger.warning(f"Reasoning leak detected for {job.name}: {response[:120]!r}")
                response = f"⚠️ **{job.skill}** ran but didn't produce clean output. Will retry next run."
                is_garbage = False  # Post the fallback message, don't suppress

            # 7. Post to Discord channel (with optional file attachments)
            if response and not is_garbage:
                await self._post_to_channel(job, response, files=files_to_attach)
                self.last_job_status[job.skill] = True

                # 8. Capture to memory + Second Brain (async, fire-and-forget)
                asyncio.create_task(self._capture_to_memory(job, response))
                asyncio.create_task(self._capture_to_second_brain(job, response))

                # 8b. Save news history for deduplication
                if job.skill == "news":
                    self._save_news_history(response)

                # 8c. Write active skill context for conversational jobs
                # so peter-channel can inject skill instructions on follow-up replies
                if self._is_conversational_skill(job.skill):
                    self._write_active_skill_context(job, skill_content)

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

        # Inject news history for deduplication
        if job.skill == "news":
            news_history = self._load_news_history()
            if news_history:
                parts.extend(["", news_history])

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

    async def _send_to_claude_code_v2(self, context: str, job: JobConfig = None, retry_on_empty: bool = True) -> str:
        """Send context to LLM and get response. Routes via invoke_llm().

        Uses router_v2.invoke_llm() which auto-fails over to Kimi if Claude
        credits are exhausted.

        Args:
            context: Full context string to send
            job: Optional job config for cost logging
            retry_on_empty: If True, retry once if response is empty

        Returns:
            Response string, or empty string on failure
        """
        from .router_v2 import invoke_llm
        from .config import CLI_SCHEDULED_MAX_TURNS, CLI_SCHEDULED_MODEL

        skill_name = job.skill if job else "unknown"
        channel = job.channel if job else ""

        response, provider = await invoke_llm(
            context=context,
            append_prompt="Execute the skill instructions. Produce output for Discord.",
            timeout=self.JOB_TIMEOUT_SECONDS,
            cost_source=f"scheduled:{skill_name}",
            cost_channel=channel,
            cost_message=f"[Skill: {skill_name}]",
            max_turns=CLI_SCHEDULED_MAX_TURNS,
            model=CLI_SCHEDULED_MODEL,
        )

        # Retry once if empty (not an error message)
        if not response.strip() and retry_on_empty:
            logger.warning(f"Empty response from CLI, retrying...")
            response, provider = await invoke_llm(
                context=context,
                append_prompt="Execute the skill instructions. Produce output for Discord.",
                timeout=self.JOB_TIMEOUT_SECONDS,
                cost_source=f"scheduled:{skill_name}:retry",
                cost_channel=channel,
                cost_message=f"[Skill: {skill_name} RETRY]",
                max_turns=CLI_SCHEDULED_MAX_TURNS,
                model=CLI_SCHEDULED_MODEL,
            )

        # Prepend fallback indicator for non-primary providers
        if provider == "claude_cc2":
            response = f"> *cc2 account*\n\n{response}"
        elif provider == "kimi":
            response = f"> *Kimi 2.5 fallback*\n\n{response}"

        return response

    async def _send_to_jobs_channel(self, context: str, job: JobConfig) -> str:
        """Send job context to the jobs-channel MCP server and wait for response.

        The jobs-channel runs a persistent Claude Code session. This method
        POSTs the skill context, waits synchronously for Claude to process
        it and call the reply tool, then returns the response.

        Same interface as _send_to_claude_code_v2() — scheduler post-processing
        works identically regardless of which method is used.
        """
        import httpx

        skill_name = job.skill if job else "unknown"
        timeout = self.JOB_TIMEOUT_SECONDS + 30  # Extra buffer over channel's internal timeout

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "http://127.0.0.1:8103/job",
                    json={"context": context, "skill": skill_name},
                    timeout=timeout,
                )
                if resp.status_code == 200:
                    return resp.json().get("response", "")
                else:
                    logger.error(f"Jobs channel returned {resp.status_code}: {resp.text}")
                    return ""
        except httpx.TimeoutException:
            raise asyncio.TimeoutError(f"Jobs channel timed out after {timeout}s")
        except Exception as e:
            logger.error(f"Jobs channel error: {e}, falling back to CLI")
            # Fall back to direct CLI if channel is down
            return await self._send_to_claude_code_v2(context, job=job)

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
            await self._send_whatsapp(message, job.whatsapp_target)

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

    async def _post_via_peter_channel(self, channel_id: int, processed, files: list = None) -> bool:
        """Post pre-processed message via peter-channel's HTTP endpoint.

        Returns True on success, False on failure (caller should fallback).
        """
        import httpx
        import base64
        import os

        payload = {
            "channel_id": str(channel_id),
            "chunks": [c for c in processed.chunks if c.strip()],
        }

        if processed.embed:
            payload["embed"] = processed.embed
        if processed.embeds:
            payload["embeds"] = processed.embeds

        # Encode file attachments as base64
        if files:
            file_attachments = []
            for filepath, filename in files:
                if os.path.exists(filepath):
                    try:
                        with open(filepath, "rb") as f:
                            file_attachments.append({
                                "data": base64.b64encode(f.read()).decode("ascii"),
                                "filename": filename,
                            })
                    except Exception as e:
                        logger.warning(f"Failed to read file {filepath}: {e}")
            if file_attachments:
                payload["files"] = file_attachments

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "http://127.0.0.1:8104/post",
                    json=payload,
                    timeout=30,
                )
                if resp.status_code == 200:
                    return True
                else:
                    logger.warning(f"peter-channel returned {resp.status_code}: {resp.text}")
                    return False
        except Exception as e:
            logger.warning(f"peter-channel HTTP failed: {e}")
            return False

    async def _post_single_channel(self, channel_name: str, message: str, job: JobConfig, files: list = None):
        """Post message to a single Discord channel.

        Tries peter-channel HTTP first (Peter H bot), falls back to bot.py's
        discord.py client (legacy Peter) if peter-channel is unavailable.

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
            # Support raw channel IDs (e.g. "1466020068021240041" from SCHEDULE.md)
            try:
                channel_id = int(channel_name)
            except (ValueError, TypeError):
                logger.error(f"Unknown channel: {channel_name}")
                return

        # Process through Response Pipeline (sanitise → classify → format → chunk)
        # When using v2, output is clean JSON — skip sanitiser
        processed = process_response(
            message,
            {'user_prompt': f'[Scheduled: {job.skill}]'},
            pre_sanitised=True,
        )

        # Try peter-channel HTTP first (delivers via Peter H bot)
        success = await self._post_via_peter_channel(channel_id, processed, files=files)
        if success:
            logger.debug(f"Posted to {channel_name} via peter-channel (type={processed.response_type.value}, files={len(files)})")
            return

        # Fallback: use bot.py's discord.py client (legacy Peter)
        logger.warning(f"Falling back to bot.py for {channel_name}")

        channel = self.bot.get_channel(channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception as e:
                logger.error(f"Could not find channel {channel_name} ({channel_id}): {e}")
                return

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

        logger.debug(f"Posted to {channel_name} via bot.py fallback (type={processed.response_type.value}, files={len(files)})")

    async def _capture_to_memory(self, job: JobConfig, response: str):
        """Legacy scheduled job memory capture — disabled.

        Scheduled jobs are now saved to Second Brain via _capture_to_second_brain()
        which uses an allow-list. This method was polluting the DB with operational
        noise (heartbeat, hydration check-in, etc.) as conversation_extract items.
        """
        pass

    async def _capture_to_second_brain(self, job: JobConfig, response: str):
        """Auto-save scheduled skill output to Second Brain.

        Only saves for skills in the SECOND_BRAIN_SAVE_SKILLS allow-list.
        Tags with skill name and "scheduled" for easy filtering.

        Args:
            job: The job that was executed
            response: The output response
        """
        if job.skill not in SECOND_BRAIN_SAVE_SKILLS:
            return

        try:
            from domains.second_brain import process_capture, CaptureType

            now = datetime.now(UK_TZ)
            user_note = f"[Auto-saved from scheduled skill: {job.skill}] {now.strftime('%A, %d %B %Y %H:%M')}"
            user_tags = ["scheduled", job.skill]

            item = await process_capture(
                source=response,
                capture_type=CaptureType.EXPLICIT,
                user_note=user_note,
                user_tags=user_tags,
                source_system="peterbot:scheduler",
            )

            if item:
                logger.info(f"Second Brain saved for {job.skill}: {item.id}")
            else:
                logger.warning(f"Second Brain save returned None for {job.skill}")
        except Exception as e:
            logger.warning(f"Failed to save {job.skill} to Second Brain: {e}")

    async def _send_whatsapp(self, message: str, target: str = ""):
        """Send message via Evolution API WhatsApp.

        Pre-checks connection state, sends with retry (handled by client),
        and posts a Discord alert on failure so issues are visible immediately.

        Args:
            message: Message text
            target: Routing target — "group" (extended team), "chris", "abby",
                    or "" (default: chris + abby individually)
        """
        failures = []  # Collect failures for alerting

        try:
            from integrations.whatsapp import (
                send_to_recipients, send_to_chris, send_to_abby, send_to_group,
                is_connected,
            )

            # Pre-flight connection check
            if not await is_connected():
                error_msg = ("WhatsApp disconnected — Evolution API instance "
                             "is not in 'open' state. Messages will not be delivered.")
                logger.error(error_msg)
                failures.append(error_msg)
                await self._alert_whatsapp_failure(failures, target)
                return

            if target == "group":
                result = await send_to_group("extended-team", message)
                if "error" not in result:
                    logger.info("Sent WhatsApp to group: extended-team")
                else:
                    failures.append(f"group (extended-team): {result.get('error', result)}")
            elif target == "chris":
                result = await send_to_chris(message)
                if "error" not in result:
                    logger.info("Sent WhatsApp to Chris")
                else:
                    failures.append(f"chris: {result.get('error', result)}")
            elif target == "abby":
                result = await send_to_abby(message)
                if "error" not in result:
                    logger.info("Sent WhatsApp to Abby")
                else:
                    failures.append(f"abby: {result.get('error', result)}")
            else:
                # Default: send to both individually
                results = await send_to_recipients(message)
                for r in results:
                    if r["success"]:
                        logger.info(f"Sent WhatsApp to {r['number']}")
                    else:
                        failures.append(f"{r['number']}: {r['result'].get('error', r['result'])}")

            if failures:
                await self._alert_whatsapp_failure(failures, target)

        except ImportError:
            logger.debug("Evolution API client not available")
        except Exception as e:
            logger.error(f"WhatsApp error: {e}")
            await self._alert_whatsapp_failure([str(e)], target)

    async def _alert_whatsapp_failure(self, failures: list[str], target: str):
        """Post a visible alert to #alerts when WhatsApp sending fails."""
        error_detail = "\n".join(f"- {f}" for f in failures)
        alert_msg = (
            f"**WhatsApp Send Failed** (target: {target or 'chris+abby'})\n\n"
            f"{error_detail}\n\n"
            f"Check: `curl http://localhost:8085/instance/connectionState/peter-whatsapp "
            f'-H "apikey: peter-whatsapp-2026-hadley"`'
        )
        logger.error(f"WhatsApp failure alert: {failures}")
        try:
            alert_channel_id = CHANNEL_IDS.get("#alerts")
            if alert_channel_id:
                channel = self.bot.get_channel(alert_channel_id)
                if channel:
                    await channel.send(alert_msg)
        except Exception as e:
            logger.error(f"Failed to post WhatsApp failure alert: {e}")

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
            response = await self._send_to_claude_code_v2(context, job=job)

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
                processed = process_response(
                    response,
                    {'user_prompt': f'[Manual: {job.skill}]'},
                    pre_sanitised=True,
                )

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

                # 8. Capture to memory + Second Brain (async, fire-and-forget)
                asyncio.create_task(self._capture_to_memory(job, response))
                asyncio.create_task(self._capture_to_second_brain(job, response))
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

    # --- Nag Reminder Checker ---

    def start_nag_checker(self):
        """Register a 60-second interval job to check and fire nag reminders."""
        self.scheduler.add_job(
            self._nag_reminder_checker,
            IntervalTrigger(seconds=60),
            id="__nag_checker",
            max_instances=1,
            replace_existing=True,
        )
        logger.info("Nag reminder checker started (checks every 60s)")

    async def _nag_reminder_checker(self):
        """Check for due nag reminders and send WhatsApp messages."""
        import httpx

        API_BASE = "http://172.19.64.1:8100"
        now = datetime.now(UK_TZ)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{API_BASE}/reminders/active-nags")
                if resp.status_code != 200:
                    return
                nags = resp.json()
        except Exception as e:
            logger.debug(f"Nag checker: failed to fetch active nags: {e}")
            return

        for nag in nags:
            try:
                nag_id = nag["id"]
                task = nag.get("task", "")
                delivery = nag.get("delivery", "discord")
                interval = nag.get("interval_minutes") or 120
                nag_until = nag.get("nag_until")
                last_nagged = nag.get("last_nagged_at")

                # Check if past nag_until time — auto-acknowledge
                if nag_until:
                    try:
                        end_hour, end_min = map(int, nag_until.split(":"))
                        end_time = now.replace(hour=end_hour, minute=end_min, second=0)
                        if now >= end_time:
                            async with httpx.AsyncClient(timeout=10.0) as client:
                                await client.post(f"{API_BASE}/reminders/{nag_id}/acknowledge")
                            if delivery.startswith("whatsapp:"):
                                target = delivery.split(":", 1)[1]
                                await self._send_nag_whatsapp(
                                    target, f"Wrapping up nag for today: *{task}* — no more reminders until tomorrow 👋"
                                )
                            logger.info(f"Nag {nag_id} auto-acknowledged (past {nag_until})")
                            continue
                    except (ValueError, AttributeError):
                        pass

                # Check if it's time to nag again
                should_nag = False
                if last_nagged is None:
                    should_nag = True
                else:
                    from dateutil.parser import parse as parse_dt
                    last = parse_dt(last_nagged)
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=UK_TZ)
                    if (now - last).total_seconds() >= interval * 60:
                        should_nag = True

                if not should_nag:
                    continue

                # Send the nag via WhatsApp
                if delivery.startswith("whatsapp:"):
                    target = delivery.split(":", 1)[1]
                    await self._send_nag_whatsapp(target, f"Hey — {task} 💪\nReply *done* when you've finished.")
                    logger.info(f"Nag sent via WhatsApp to {target}: {task[:50]}")
                else:
                    logger.debug(f"Nag {nag_id}: delivery={delivery} not handled by checker")
                    continue

                # Update last_nagged_at and fired_at
                try:
                    update_fields = {"last_nagged_at": now.isoformat()}
                    if not nag.get("fired_at"):
                        update_fields["fired_at"] = now.isoformat()
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        await client.patch(
                            f"{API_BASE}/reminders/{nag_id}",
                            json=update_fields,
                        )
                except Exception:
                    pass

            except Exception as e:
                logger.debug(f"Nag checker error for {nag.get('id', '?')}: {e}")

    @staticmethod
    async def _send_nag_whatsapp(target: str, message: str):
        """Send a WhatsApp nag message to a target (chris, abby, group)."""
        from integrations.whatsapp import send_text, send_to_chris, send_to_abby, send_to_group

        if target == "chris":
            await send_to_chris(message)
        elif target == "abby":
            await send_to_abby(message)
        elif target == "group":
            await send_to_group("extended-team", message)
        else:
            await send_text(target, message)
