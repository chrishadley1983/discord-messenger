"""Standalone scheduled jobs (not attached to a domain)."""

from .morning_briefing import register_morning_briefing
from .balance_monitor import register_balance_monitor
from .school_run import register_school_run
from .nutrition_morning import register_nutrition_morning
from .hydration_checkin import register_hydration_checkin
from .weekly_health import register_weekly_health
from .monthly_health import register_monthly_health
from .withings_sync import register_withings_sync
from .youtube_feed import register_youtube_feed

__all__ = [
    "register_morning_briefing",
    "register_balance_monitor",
    "register_school_run",
    "register_nutrition_morning",
    "register_hydration_checkin",
    "register_weekly_health",
    "register_monthly_health",
    "register_withings_sync",
    "register_youtube_feed"
]
