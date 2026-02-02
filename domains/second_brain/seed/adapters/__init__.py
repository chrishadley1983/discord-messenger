"""Seed import adapters for various sources."""

from .github import GitHubProjectsAdapter
from .bookmarks import BookmarksAdapter
from .garmin import GarminActivitiesAdapter
from .calendar import CalendarEventsAdapter
from .email import EmailThreadsAdapter

__all__ = [
    "GitHubProjectsAdapter",
    "BookmarksAdapter",
    "GarminActivitiesAdapter",
    "CalendarEventsAdapter",
    "EmailThreadsAdapter",
]
