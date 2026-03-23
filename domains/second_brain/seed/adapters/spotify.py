"""Spotify listening history adapter.

Imports recently played tracks and top artists/tracks from Spotify
using the spotipy library with OAuth refresh token auth.
"""

import os
from datetime import datetime, timezone
from typing import Any

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter


def _get_spotify_client() -> spotipy.Spotify:
    """Get authenticated Spotify client using refresh token."""
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    refresh_token = os.getenv("SPOTIFY_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        raise ValueError(
            "Spotify credentials not configured "
            "(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REFRESH_TOKEN)"
        )

    auth_manager = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri="http://127.0.0.1:8765/callback",
        scope=" ".join([
            "user-read-recently-played", "user-top-read",
            "user-library-read", "user-library-modify",
            "user-read-playback-state", "user-modify-playback-state",
            "user-read-currently-playing",
            "playlist-read-private", "playlist-read-collaborative",
            "playlist-modify-public", "playlist-modify-private",
            "user-follow-read", "user-follow-modify",
            "user-read-private", "user-read-email",
        ]),
    )

    # Inject the refresh token and force a token refresh
    auth_manager.refresh_access_token(refresh_token)

    return spotipy.Spotify(auth_manager=auth_manager)


def _ms_to_duration(ms: int) -> str:
    """Convert milliseconds to 'm:ss' format."""
    total_sec = ms // 1000
    minutes = total_sec // 60
    seconds = total_sec % 60
    return f"{minutes}:{seconds:02d}"


@register_adapter
class SpotifyListeningAdapter(SeedAdapter):
    """Import Spotify listening history and top tracks/artists."""

    name = "spotify-listening"
    description = "Import listening history and top tracks from Spotify"
    source_system = "seed:spotify"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.include_recent = config.get("include_recent", True) if config else True
        self.include_top = config.get("include_top", True) if config else True
        self.recent_limit = config.get("recent_limit", 50) if config else 50

    async def validate(self) -> tuple[bool, str]:
        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        refresh_token = os.getenv("SPOTIFY_REFRESH_TOKEN")
        if not all([client_id, client_secret, refresh_token]):
            return False, "Spotify credentials not configured (SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REFRESH_TOKEN)"
        return True, ""

    async def fetch(self, limit: int = 100) -> list[SeedItem]:
        """Fetch recently played tracks and top artists/tracks."""
        import asyncio
        items = []

        try:
            sp = await asyncio.to_thread(_get_spotify_client)

            if self.include_recent:
                recent = await self._fetch_recently_played(sp)
                items.extend(recent)

            if self.include_top:
                top = await self._fetch_top_summary(sp)
                items.extend(top)

        except Exception as e:
            logger.exception(f"Failed to fetch Spotify data: {e}")

        return items[:limit]

    async def _fetch_recently_played(self, sp: spotipy.Spotify) -> list[SeedItem]:
        """Fetch recently played tracks as a daily summary."""
        import asyncio
        items = []

        try:
            results = await asyncio.to_thread(
                sp.current_user_recently_played, limit=self.recent_limit
            )

            if not results or not results.get("items"):
                return items

            # Group by date for daily summaries
            by_date: dict[str, list[dict]] = {}
            for item in results["items"]:
                played_at = item.get("played_at", "")
                if played_at:
                    date_str = played_at[:10]  # YYYY-MM-DD
                else:
                    continue
                by_date.setdefault(date_str, []).append(item)

            for date_str, tracks in by_date.items():
                content_parts = [
                    f"# Spotify Listening — {date_str}",
                    "",
                    f"**Tracks played:** {len(tracks)}",
                    "",
                    "| # | Track | Artist | Duration |",
                    "|---|-------|--------|----------|",
                ]

                artists_seen = set()
                for i, item in enumerate(tracks, 1):
                    track = item["track"]
                    name = track.get("name", "Unknown")
                    artist = ", ".join(a["name"] for a in track.get("artists", []))
                    duration = _ms_to_duration(track.get("duration_ms", 0))
                    content_parts.append(f"| {i} | {name} | {artist} | {duration} |")
                    for a in track.get("artists", []):
                        artists_seen.add(a["name"])

                # Derive topics from genres (not available on track, but tag by artist count)
                topics = ["spotify", "music", "listening"]
                if len(tracks) >= 10:
                    topics.append("heavy-listening")

                played_dt = datetime.fromisoformat(
                    tracks[0]["played_at"].replace("Z", "+00:00")
                )

                items.append(SeedItem(
                    title=f"Spotify Listening — {date_str}",
                    content="\n".join(content_parts),
                    source_url=f"spotify://daily/{date_str}",
                    topics=topics,
                    created_at=played_dt,
                    metadata={
                        "track_count": len(tracks),
                        "unique_artists": len(artists_seen),
                        "artists": list(artists_seen)[:10],
                    },
                    content_type="listening_history",
                ))

        except Exception as e:
            logger.warning(f"Failed to fetch recently played: {e}")

        return items

    async def _fetch_top_summary(self, sp: spotipy.Spotify) -> list[SeedItem]:
        """Fetch top artists and tracks as a periodic summary."""
        import asyncio
        items = []

        try:
            # Top tracks (short term = last 4 weeks)
            top_tracks = await asyncio.to_thread(
                sp.current_user_top_tracks, limit=20, time_range="short_term"
            )
            # Top artists (short term)
            top_artists = await asyncio.to_thread(
                sp.current_user_top_artists, limit=10, time_range="short_term"
            )

            if not top_tracks.get("items") and not top_artists.get("items"):
                return items

            now = datetime.now(timezone.utc)
            month_str = now.strftime("%Y-%m")

            content_parts = [
                f"# Spotify Top Tracks & Artists — {month_str}",
                "",
            ]

            if top_artists.get("items"):
                content_parts.extend([
                    "## Top Artists (Last 4 Weeks)",
                    "",
                    "| # | Artist | Genres |",
                    "|---|--------|--------|",
                ])
                genres_seen = set()
                for i, artist in enumerate(top_artists["items"], 1):
                    name = artist.get("name", "Unknown")
                    genres = ", ".join(artist.get("genres", [])[:3]) or "—"
                    content_parts.append(f"| {i} | {name} | {genres} |")
                    genres_seen.update(artist.get("genres", []))

                content_parts.append("")

            if top_tracks.get("items"):
                content_parts.extend([
                    "## Top Tracks (Last 4 Weeks)",
                    "",
                    "| # | Track | Artist | Duration |",
                    "|---|-------|--------|----------|",
                ])
                for i, track in enumerate(top_tracks["items"], 1):
                    name = track.get("name", "Unknown")
                    artist = ", ".join(a["name"] for a in track.get("artists", []))
                    duration = _ms_to_duration(track.get("duration_ms", 0))
                    content_parts.append(f"| {i} | {name} | {artist} | {duration} |")

            topics = ["spotify", "music", "top-tracks", "monthly-summary"]

            items.append(SeedItem(
                title=f"Spotify Top Tracks & Artists — {month_str}",
                content="\n".join(content_parts),
                source_url=f"spotify://top/{month_str}",
                topics=topics,
                created_at=now,
                metadata={
                    "top_track_count": len(top_tracks.get("items", [])),
                    "top_artist_count": len(top_artists.get("items", [])),
                },
                content_type="listening_history",
            ))

        except Exception as e:
            logger.warning(f"Failed to fetch top tracks/artists: {e}")

        return items

    def get_default_topics(self) -> list[str]:
        return ["spotify", "music"]
