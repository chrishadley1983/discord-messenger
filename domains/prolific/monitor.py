"""Scheduled poll job: scrape Prolific, notify on new studies."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from logger import logger

from .config import (
    ACTIVE_END_HOUR,
    ACTIVE_END_MINUTE,
    ACTIVE_START_HOUR,
    ACTIVE_START_MINUTE,
    ACTIVE_TIMEZONE,
    POLL_INTERVAL_SECONDS,
    POLL_JITTER_SECONDS,
)
from .notifier import notify_new_study
from .scraper import fetch_studies
from .seen import is_new, mark_seen


def _within_active_hours() -> bool:
    now = datetime.now(ZoneInfo(ACTIVE_TIMEZONE))
    now_mins = now.hour * 60 + now.minute
    start_mins = ACTIVE_START_HOUR * 60 + ACTIVE_START_MINUTE
    end_mins = ACTIVE_END_HOUR * 60 + ACTIVE_END_MINUTE
    return start_mins <= now_mins < end_mins


async def poll_studies() -> None:
    if not _within_active_hours():
        return

    try:
        studies = await fetch_studies()
    except Exception as e:
        logger.error(f"Prolific scrape failed: {e}")
        return

    new_count = 0
    for study in studies:
        if not is_new(study.study_id):
            continue
        mark_seen(study.study_id)
        await notify_new_study(study)
        new_count += 1
        logger.info(
            f"Prolific new study: {study.title} ({study.hourly_str}, {study.places} places)"
        )

    if studies:
        logger.debug(f"Prolific poll: {len(studies)} visible, {new_count} new")


def register_prolific_monitor(scheduler: AsyncIOScheduler) -> None:
    """Register the polling job with the bot's APScheduler instance."""
    scheduler.add_job(
        poll_studies,
        "interval",
        seconds=POLL_INTERVAL_SECONDS,
        jitter=POLL_JITTER_SECONDS,
        id="prolific_monitor",
        name="Prolific studies monitor",
        max_instances=1,
        replace_existing=True,
    )
    logger.info(
        f"Prolific monitor registered "
        f"({POLL_INTERVAL_SECONDS}s ± {POLL_JITTER_SECONDS}s, "
        f"active {ACTIVE_START_HOUR:02d}:{ACTIVE_START_MINUTE:02d}-"
        f"{ACTIVE_END_HOUR:02d}:{ACTIVE_END_MINUTE:02d} {ACTIVE_TIMEZONE})"
    )
