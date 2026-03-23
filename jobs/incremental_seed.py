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
    "garmin-health": "Garmin Health",
    "bookmarks": "Bookmarks",
    "email-link-scraper": "Email Links",
    "hadley-bricks-email": "HB Email",
    "finance-summary": "Finance",
    "family-fuel-recipes": "Recipes",
    "spotify-listening": "Spotify",
    "netflix-viewing": "Netflix",
    "travel-bookings": "Travel",
    "withings-health": "Withings",
    "peter-interactions": "Peter Chat",
    "reddit-saved": "Reddit",
    "school-data": "School",
    "claude-code-history": "Claude Code",
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
    - Email Links: 10 items (Gousto recipes, Airbnb bookings scraped from email links)
    """
    from domains.second_brain.seed.runner import run_seed_import, run_seed_import_batched, get_available_adapters

    # Import adapters to register them
    from domains.second_brain.seed.adapters import (
        calendar, email, github, garmin, garmin_health, bookmarks, email_links,
        hadley_bricks_email, finance_summary, recipes, spotify, netflix, travel,
        withings, peter_interactions, reddit, school, claude_code_history,
    )

    adapters = get_available_adapters()

    # Define limits per adapter (incremental, not full backfill)
    adapter_limits = {
        "calendar-events": 50,
        "email-import": 100,
        "github-projects": 30,
        "garmin-activities": 30,
        "bookmarks": 50,
        "email-link-scraper": 10,
        "hadley-bricks-email": 100,
    }

    # Recipes: sync all (dedup handles repeats, low volume)
    adapter_limits["family-fuel-recipes"] = 500

    # Spotify: daily listening history + monthly top tracks
    adapter_limits["spotify-listening"] = 50

    # Netflix: viewing history (weekly scrape is enough, dedup handles repeats)
    adapter_limits["netflix-viewing"] = 100

    # Travel: booking confirmations + check-in instructions from Gmail
    adapter_limits["travel-bookings"] = 100

    # Finance summary runs monthly (2nd of month generates previous month's summary)
    from datetime import date
    if date.today().day <= 3:
        adapter_limits["finance-summary"] = 1

    # New adapters
    adapter_limits["garmin-health"] = 7       # 1 week of daily health summaries
    adapter_limits["withings-health"] = 30    # ~1 month of measurements
    adapter_limits["peter-interactions"] = 50  # Recent Peter chat exchanges
    adapter_limits["school-data"] = 50        # School events, newsletters, spellings
    adapter_limits["claude-code-history"] = 50 # Recent Claude Code conversations
    adapter_limits["reddit-saved"] = 20       # Saved/upvoted/commented posts

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
                config = {"days_back": 7, "auto_discover": True}
            elif adapter_name == "garmin-activities":
                config = {"years_back": 0.02}  # ~1 week of activities
            elif adapter_name == "bookmarks":
                config = {"file_path": CHROME_BOOKMARKS_PATH, "fetch_content": True}
            elif adapter_name == "email-link-scraper":
                config = {"years_back": 0.1, "per_scraper_limit": 10}
            elif adapter_name == "hadley-bricks-email":
                config = {"years_back": 0.1, "per_category_limit": 20}
            elif adapter_name == "spotify-listening":
                config = {"include_recent": True, "include_top": True, "recent_limit": 50}
            elif adapter_name == "netflix-viewing":
                config = {"max_pages": 2}
            elif adapter_name == "travel-bookings":
                config = {"years_back": 0.5, "per_provider_limit": 10, "include_checkin": True}
            elif adapter_name == "garmin-health":
                config = {}  # Defaults to 7 days
            elif adapter_name == "withings-health":
                config = {"days_back": 30}
            elif adapter_name == "peter-interactions":
                config = {"days_back": 7}
            elif adapter_name == "school-data":
                config = {}  # Defaults to 14-day lookback
            elif adapter_name == "claude-code-history":
                config = {"days_back": 7}
            elif adapter_name == "reddit-saved":
                config = {}

            adapter = adapter_class(config)

            # Validate first (tracked separately for summary)
            is_valid, val_err = await adapter.validate()
            if not is_valid:
                logger.warning(f"Adapter {adapter_name} validation failed: {val_err}")
                outcomes.append(_AdapterOutcome(label=label, validated=False, validate_error=val_err))
                continue

            # Use batched import for adapters with many items (saves embedding API calls)
            if limit > 10:
                result = await run_seed_import_batched(adapter, limit=limit, skip_validate=True)
            else:
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

    # --- Provider discovery: flag unknown travel providers ---
    provider_suggestions = []
    try:
        from domains.second_brain.seed.adapters.travel import TravelBookingAdapter
        travel_adapter = TravelBookingAdapter({"years_back": 1.0})
        provider_suggestions = await travel_adapter.discover_unknown_providers()
        if provider_suggestions:
            logger.info(f"Travel provider discovery: {len(provider_suggestions)} suggestions")
    except Exception as e:
        logger.warning(f"Travel provider discovery failed: {e}")

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

                # Post provider discovery suggestions
                if provider_suggestions:
                    lines = ["\U0001F50D **Travel Provider Discovery**", ""]
                    lines.append("Spotted repeat booking emails from providers we don't track yet:")
                    for s in provider_suggestions[:5]:
                        lines.append(f"- **{s['domain']}** ({s['count']} emails)")
                        for subj in s['sample_subjects'][:2]:
                            lines.append(f"  \u2022 {subj}")
                    lines.append("")
                    lines.append('Say "add X as a travel provider" to start tracking.')
                    await channel.send("\n".join(lines))
                    logger.info(f"Posted {len(provider_suggestions)} provider suggestions to #alerts")
            else:
                logger.warning(f"Could not find #alerts channel {ALERTS_CHANNEL_ID}")
        except Exception as e:
            logger.error(f"Failed to post seed summary to Discord: {e}")

    # Return dict for _tracked_job wrapper to interpret
    validation_failures = [o for o in outcomes if not o.validated]
    all_ok = len(validation_failures) == 0 and total_failed == 0
    failure_summary = "; ".join(
        f"{o.label}: {o.validate_error}" for o in validation_failures
    ) if validation_failures else ""
    if total_failed > 0:
        failure_summary += f"; {total_failed} items failed to import"

    return {
        "Incremental Seed": (
            all_ok,
            f"{total_imported} imported, {total_skipped} skipped, "
            f"{len(validation_failures)} adapters failed"
            + (f" ({failure_summary})" if failure_summary else "")
        )
    }


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
