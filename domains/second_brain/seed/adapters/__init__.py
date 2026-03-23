"""Seed import adapters for various sources."""

from .github import GitHubProjectsAdapter
from .bookmarks import BookmarksAdapter
from .garmin import GarminActivitiesAdapter
from .garmin_health import GarminHealthAdapter
from .calendar import CalendarEventsAdapter
from .email import EmailImportAdapter
from .hadley_bricks_email import HadleyBricksEmailAdapter
from .claude_history import ClaudeHistoryAdapter
from .claude_code_history import ClaudeCodeHistoryAdapter
from .email_links import EmailLinkScraperAdapter
from .finance_summary import FinanceSummaryAdapter
from .recipes import RecipeAdapter
from .spotify import SpotifyListeningAdapter
from .netflix import NetflixViewingAdapter
from .travel import TravelBookingAdapter
from .withings import WithingsAdapter
from .peter_interactions import PeterInteractionsAdapter
from .reddit import RedditAdapter
from .school import SchoolAdapter

__all__ = [
    "GitHubProjectsAdapter",
    "BookmarksAdapter",
    "GarminActivitiesAdapter",
    "GarminHealthAdapter",
    "CalendarEventsAdapter",
    "EmailImportAdapter",
    "HadleyBricksEmailAdapter",
    "ClaudeHistoryAdapter",
    "ClaudeCodeHistoryAdapter",
    "EmailLinkScraperAdapter",
    "FinanceSummaryAdapter",
    "RecipeAdapter",
    "SpotifyListeningAdapter",
    "NetflixViewingAdapter",
    "TravelBookingAdapter",
    "WithingsAdapter",
    "PeterInteractionsAdapter",
    "RedditAdapter",
    "SchoolAdapter",
]
