"""Email link scrapers — import to register all available scrapers."""

from .gousto import GoustoRecipeScraper
from .airbnb import AirbnbBookingScraper

__all__ = ["GoustoRecipeScraper", "AirbnbBookingScraper"]
