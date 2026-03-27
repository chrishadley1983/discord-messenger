"""Shared configuration for the Japan scraper pipeline."""

import os
from pathlib import Path

# Directories
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "scrape_output"
PROJECT_ROOT = BASE_DIR.parent

# Tabelog data
TABELOG_JSON = PROJECT_ROOT / "tabelog_combined.json"

# Hadley API
HADLEY_API = os.getenv("HADLEY_API_URL", "http://localhost:8100")

# Reddit config
REDDIT_SUBREDDITS = ["JapanTravel", "JapaneseFood", "Tokyo", "osaka"]
REDDIT_SEARCH_QUERIES = [
    "restaurant recommendation",
    "food recommendation",
    "hidden gem",
    "best ramen",
    "best sushi",
    "where to eat",
    "trip report food",
]
REDDIT_MIN_SCORE = 20
REDDIT_COMMENT_SCORE_THRESHOLD = 500
REDDIT_REQUEST_DELAY = 3.0  # seconds between requests
REDDIT_BACKOFF_DELAY = 90.0  # seconds on 429

# YouTube config
YOUTUBE_SEARCH_QUERIES = [
    "Tokyo restaurants 2025",
    "Tokyo food guide",
    "Kyoto restaurants 2025",
    "Kyoto food guide",
    "Osaka street food 2025",
    "Osaka food guide",
    "Japan hidden gem restaurants",
    "Japan travel food vlog 2025",
    "best ramen Tokyo",
    "best sushi Tokyo",
    "Japan travel tips food",
    "Yokohama food guide",
    "Hakone travel guide",
    "Nara travel food",
]
YOUTUBE_MAX_RESULTS_PER_QUERY = 10
YOUTUBE_MIN_DATE = "2024-01-01T00:00:00Z"

# Keyword filter for pre-filtering before Claude
JAPAN_PLACE_KEYWORDS = [
    # Food types
    "restaurant", "ramen", "sushi", "izakaya", "tempura", "yakiniku",
    "tonkatsu", "curry", "udon", "soba", "gyoza", "okonomiyaki",
    "takoyaki", "wagyu", "kaiseki", "donburi", "katsu", "yakitori",
    "onigiri", "matcha", "mochi", "cafe", "bakery", "depachika",
    "food hall", "street food", "conveyor belt", "omakase",
    # Place types
    "shrine", "temple", "onsen", "ryokan", "market", "park", "garden",
    "castle", "museum", "tower", "station", "arcade", "shopping",
    "department store",
    # Tokyo areas
    "shinjuku", "shibuya", "ginza", "asakusa", "akihabara", "harajuku",
    "roppongi", "ikebukuro", "ueno", "tsukiji", "toyosu", "nakameguro",
    "shimokitazawa", "yanaka", "koenji", "ebisu", "daikanyama",
    # Kyoto areas
    "gion", "arashiyama", "fushimi", "higashiyama", "pontocho",
    "nishiki", "kiyomizu",
    # Osaka areas
    "dotonbori", "shinsekai", "namba", "umeda", "kuromon",
    "amerikamura", "tennoji",
    # Other cities/areas
    "yokohama", "hakone", "nara", "kamakura", "nikko",
    # Generic signals
    "recommend", "must try", "must visit", "best", "favorite",
    "favourite", "amazing", "incredible", "worth", "queue", "line up",
    "reservation", "book ahead", "michelin", "tabelog",
]

# Additional web sources to scrape directly
WEB_SOURCES = [
    "https://zaraintokyo.com/",
]

# Claude extraction config
CLAUDE_MODEL = "claude-sonnet-4-20250514"
CLAUDE_BATCH_SIZE_REDDIT = 12  # posts per prompt
CLAUDE_BATCH_SIZE_YOUTUBE = 6  # transcript segments per prompt
