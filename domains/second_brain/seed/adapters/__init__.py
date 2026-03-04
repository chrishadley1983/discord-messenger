"""Seed import adapters for various sources."""

from .github import GitHubProjectsAdapter
from .bookmarks import BookmarksAdapter
from .garmin import GarminActivitiesAdapter
from .calendar import CalendarEventsAdapter
from .email import EmailImportAdapter
from .claude_history import ClaudeHistoryAdapter

__all__ = [
    "GitHubProjectsAdapter",
    "BookmarksAdapter",
    "GarminActivitiesAdapter",
    "CalendarEventsAdapter",
    "EmailImportAdapter",
    "ClaudeHistoryAdapter",
]
