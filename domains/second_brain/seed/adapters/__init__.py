"""Seed import adapters for various sources."""

from .github import GitHubStarsAdapter
from .bookmarks import BookmarksAdapter
from .garmin import GarminActivitiesAdapter
from .calendar import CalendarPatternsAdapter
from .email import EmailThreadsAdapter

__all__ = [
    "GitHubStarsAdapter",
    "BookmarksAdapter",
    "GarminActivitiesAdapter",
    "CalendarPatternsAdapter",
    "EmailThreadsAdapter",
]
