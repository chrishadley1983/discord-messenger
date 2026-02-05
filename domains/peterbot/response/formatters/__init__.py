"""Formatters for different response types.

Each formatter transforms classified content into Discord-native format.
Based on RESPONSE.md Section 5.
"""

from .conversational import format_conversational
from .table import format_table, parse_markdown_table
from .search import (
    format_search_results,
    format_news_results,
    format_image_results,
    format_local_results,
)
from .code import format_code
from .proactive import (
    format_morning_briefing,
    format_reminder,
    format_alert,
)
from .nutrition import (
    format_nutrition_summary,
    format_nutrition_log,
    format_water_log,
)
from .error import format_error
from .schedule import format_schedule
from .list_formatter import format_list

__all__ = [
    'format_conversational',
    'format_table',
    'parse_markdown_table',
    'format_search_results',
    'format_news_results',
    'format_image_results',
    'format_local_results',
    'format_code',
    'format_morning_briefing',
    'format_reminder',
    'format_alert',
    'format_nutrition_summary',
    'format_nutrition_log',
    'format_water_log',
    'format_error',
    'format_schedule',
    'format_list',
]
