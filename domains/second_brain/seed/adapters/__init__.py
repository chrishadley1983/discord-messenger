"""Seed import adapters for various sources."""

from .github import GitHubProjectsAdapter
from .bookmarks import BookmarksAdapter
from .garmin import GarminActivitiesAdapter
from .calendar import CalendarEventsAdapter
from .email import EmailImportAdapter
from .hadley_bricks_email import HadleyBricksEmailAdapter
from .claude_history import ClaudeHistoryAdapter
from .email_links import EmailLinkScraperAdapter
from .finance_summary import FinanceSummaryAdapter
from .recipes import RecipeAdapter

__all__ = [
    "GitHubProjectsAdapter",
    "BookmarksAdapter",
    "GarminActivitiesAdapter",
    "CalendarEventsAdapter",
    "EmailImportAdapter",
    "HadleyBricksEmailAdapter",
    "ClaudeHistoryAdapter",
    "EmailLinkScraperAdapter",
    "FinanceSummaryAdapter",
    "RecipeAdapter",
]
