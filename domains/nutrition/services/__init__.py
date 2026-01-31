"""Nutrition domain services."""

from .supabase_service import (
    insert_meal,
    insert_water,
    get_today_totals,
    get_today_meals,
    get_week_summary
)
from .garmin import get_steps, get_sleep, get_heart_rate, get_daily_summary
from .withings import get_weight, get_weight_history
from .goals_service import get_goals, update_goal
from .favourites_service import (
    save_favourite,
    get_favourite,
    list_favourites,
    delete_favourite
)

__all__ = [
    "insert_meal",
    "insert_water",
    "get_today_totals",
    "get_today_meals",
    "get_week_summary",
    "get_steps",
    "get_sleep",
    "get_heart_rate",
    "get_daily_summary",
    "get_weight",
    "get_weight_history",
    "get_goals",
    "update_goal",
    "save_favourite",
    "get_favourite",
    "list_favourites",
    "delete_favourite"
]
