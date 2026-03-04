"""Incremental Seed Import job.

Runs daily at 1am to load new calendar entries, emails, GitHub activity,
Garmin fitness data, and browser bookmarks into Second Brain.
Uses small limits for incremental updates.

Duplicates are automatically skipped by source_url check in runner.
"""

import asyncio
import os
from dataclasses import dataclass

from logger import logger

# Chrome's live Bookmarks file (JSON format, read directly — no export needed)
CHROME_BOOKMARKS_PATH = os.path.join(
    os.getenv("LOCALAPPDATA", ""),
    "Google", "Chrome", "User Data", "Default", "Bookmarks",
)

# Discord channel for seed job summaries
ALERTS_CHANNEL_ID = 1466019126194606286  # #alerts


# Display names for adapter_name → short label
ADAPTER_LABELS = {
    "calendar-events": "Calendar",
    "email-import": "Email",
    "github-projects": "GitHub",
    "garmin-activities": "Garmin",
    "bookmarks": "Bookmarks",
}


@dataclass
class _AdapterOutcome:
    """Per-adapter outcome for the summary table."""
    label: str
    validated: bool
    validate_error: str = ""
    found: int = 0
    imported: int = 0
    skipped: int = 0
    failed: int = 0


def _build_summary_message(outcomes: list[_AdapterOutcome]) -> str:
    """Build a Discord code-block table summarising the seed run."""
    # Column widths
    w_name = max(len(o.label) for o in outcomes)
    w_val = 8   # "Validate"
    w_fetch = 9  # "Fetch col"
    w_import = 0
    w_dedup = 5  # "Dedup"

    # Pre-compute import and fetch strings
    fetch_strs = []
    import_strs = []
    dedup_strs = []
    for o in outcomes:
        if not o.validated:
            fetch_strs.append("-")
            import_strs.append(o.validate_error[:30] or "FAIL")
            dedup_strs.append("-")
        else:
            n = o.found
            fetch_strs.append(f"{n} item{'s' if n != 1 else ''}")

            parts = []
            if o.imported:
                parts.append(f"{o.imported} imported")
            if o.skipped:
                parts.append(f"{o.skipped} dedup'd")
            if o.failed:
                parts.append(f"{o.failed} failed")
            import_strs.append(", ".join(parts) if parts else "0")

            dedup_strs.append("PASS" if o.validated else "-")

    w_fetch = max(w_fetch, max(len(s) for s in fetch_strs))
    w_import = max(6, max(len(s) for s in import_strs))
    w_dedup = max(w_dedup, max(len(s) for s in dedup_strs))

    def row(name, val, fetch, imp, dedup):
        return (
            f" {name:<{w_name}} | {val:<{w_val}} | "
            f"{fetch:<{w_fetch}} | {imp:<{w_import}} | {dedup:<{w_dedup}}"
        )

    def sep():
        return (
            f"-{'-'*w_name}-+-{'-'*w_val}-+-"
            f"{'-'*w_fetch}-+-{'-'*w_import}-+-{'-'*w_dedup}-"
        )

    lines = [
        row("Adapter", "Validate", "Fetch", "Import", "Dedup"),
        sep(),
    ]

    for o, fs, ims, ds in zip(outcomes, fetch_strs, import_strs, dedup_strs):
        val_str = "PASS" if o.validated else "FAIL"
        lines.append(row(o.label, val_str, fs, ims, ds))

    table = "\n".join(lines)

    total_imported = sum(o.imported for o in outcomes)
    total_skipped = sum(o.skipped for o in outcomes)
    total_failed = sum(o.failed for o in outcomes)
    all_pass = all(o.validated for o in outcomes) and total_failed == 0
    status_emoji = "\u2705" if all_pass else "\u26a0\ufe0f"

    header = f"{status_emoji} **Second Brain — Daily Seed Import**"
    summary = f"**{total_imported}** imported, **{total_skipped}** dedup'd, **{total_failed}** failed"

    return f"{header}\n```\n{table}\n```\n{summary}"


async def incremental_seed_import(bot=None):
    """Run incremental seed import for key adapters.

    Imports:
    - Calendar: 50 items (new events)
    - Email: 100 items (new emails, filtered)
    - GitHub: 30 items (new commits/repos)
    - Garmin: 30 items (recent activities/health data)
    - Bookmarks: 50 items (from Chrome's live file — dedup handles repeats)
    """
    from domains.second_brain.seed.runner import run_seed_import, get_available_adapters

    # Import adapters to register them
    from domains.second_brain.seed.adapters import calendar, email, github, garmin, bookmarks

    adapters = get_available_adapters()

    # Define limits per adapter (incremental, not full backfill)
    adapter_limits = {
        "calendar-events": 50,
        "email-import": 100,
        "github-projects": 30,
        "garmin-activities": 30,
        "bookmarks": 50,
    }

    results = []
    outcomes: list[_AdapterOutcome] = []
    total_imported = 0
    total_skipped = 0
    total_failed = 0

    for adapter_name, limit in adapter_limits.items():
        label = ADAPTER_LABELS.get(adapter_name, adapter_name)

        if adapter_name not in adapters:
            logger.warning(f"Adapter {adapter_name} not found, skipping")
            outcomes.append(_AdapterOutcome(label=label, validated=False, validate_error="not registered"))
            continue

        adapter_class = adapters[adapter_name]

        try:
            logger.info(f"Running incremental import: {adapter_name} (limit={limit})")

            # Configure adapter for incremental (shorter time window)
            # Note: adapters auto-skip duplicates via source_url check
            config = {}
            if adapter_name == "calendar-events":
                config = {"years_back": 0.1}  # ~5 weeks back
            elif adapter_name == "email-import":
                config = {"years_back": 0.1}  # ~5 weeks back only
            elif adapter_name == "github-projects":
                config = {"days_back": 7}  # Last 7 days of commits
            elif adapter_name == "garmin-activities":
                config = {"years_back": 0.02}  # ~1 week of activities
            elif adapter_name == "bookmarks":
                config = {"file_path": CHROME_BOOKMARKS_PATH}

            adapter = adapter_class(config)

            # Validate first (tracked separately for summary)
            is_valid, val_err = await adapter.validate()
            if not is_valid:
                logger.warning(f"Adapter {adapter_name} validation failed: {val_err}")
                outcomes.append(_AdapterOutcome(label=label, validated=False, validate_error=val_err))
                continue

            result = await run_seed_import(adapter, limit=limit, skip_validate=True)

            results.append(result)
            total_imported += result.items_imported
            total_skipped += result.items_skipped
            total_failed += result.items_failed

            outcomes.append(_AdapterOutcome(
                label=label,
                validated=True,
                found=result.items_found,
                imported=result.items_imported,
                skipped=result.items_skipped,
                failed=result.items_failed,
            ))

            logger.info(
                f"  {adapter_name}: {result.items_imported} imported, "
                f"{result.items_skipped} skipped, {result.items_failed} failed"
            )

        except Exception as e:
            logger.error(f"Adapter {adapter_name} failed: {e}")
            outcomes.append(_AdapterOutcome(label=label, validated=False, validate_error=str(e)[:30]))

    logger.info(
        f"Incremental seed complete: {total_imported} imported, "
        f"{total_skipped} skipped, {total_failed} failed"
    )

    # Send Discord summary
    if bot and outcomes:
        try:
            channel = bot.get_channel(ALERTS_CHANNEL_ID)
            if not channel:
                channel = await bot.fetch_channel(ALERTS_CHANNEL_ID)
            if channel:
                message = _build_summary_message(outcomes)
                await channel.send(message)
                logger.info("Posted seed import summary to #alerts")
            else:
                logger.warning(f"Could not find #alerts channel {ALERTS_CHANNEL_ID}")
        except Exception as e:
            logger.error(f"Failed to post seed summary to Discord: {e}")

    return results


def register_incremental_seed(scheduler, bot=None):
    """Register the incremental seed job with the scheduler.

    Args:
        scheduler: APScheduler instance
        bot: Discord bot instance for posting summaries to #alerts
    """
    scheduler.add_job(
        incremental_seed_import,
        'cron',
        hour=1,
        minute=0,
        timezone="Europe/London",
        id="incremental_seed",
        max_instances=1,
        coalesce=True,
        args=[bot],
    )
    logger.info("Registered incremental seed job (daily at 1:00 AM UK)")
