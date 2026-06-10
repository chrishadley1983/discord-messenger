"""Helper libraries for skill data fetchers + bot.py infrastructure jobs.

Legacy register_* scheduler registration is deprecated — all scheduled
Discord output is defined in wsl_config/SCHEDULE.md and executed by
PeterbotScheduler. The modules here remain because data_fetchers.py imports
their fetch/format helpers, and bot.py registers a few infrastructure syncs
(incremental_seed, school_sync, energy_sync, whatsapp_sync).
"""

from .morning_briefing import register_morning_briefing
from .balance_monitor import register_balance_monitor
from .school_run import register_school_run
from .weekly_health import register_weekly_health
from .monthly_health import register_monthly_health
from .youtube_feed import register_youtube_feed

__all__ = [
    "register_morning_briefing",
    "register_balance_monitor",
    "register_school_run",
    "register_weekly_health",
    "register_monthly_health",
    "register_youtube_feed",
]
