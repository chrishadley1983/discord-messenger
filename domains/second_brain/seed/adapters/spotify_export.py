"""Spotify data export adapter.

Imports listening history from a Spotify account data export ZIP/folder.
This handles the standard export (not extended streaming history).

Fields per entry:
  - endTime: "YYYY-MM-DD HH:MM"
  - artistName / podcastName: str
  - trackName / episodeName: str
  - msPlayed: int

Creates weekly music summaries, a podcast summary, and a library snapshot.
"""

import json
import os
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter


def _ms_to_hm(ms: int) -> str:
    """Convert milliseconds to 'Xh Ym' format."""
    total_min = ms // 60_000
    hours = total_min // 60
    minutes = total_min % 60
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _ms_to_duration(ms: int) -> str:
    """Convert milliseconds to 'm:ss' format."""
    total_sec = ms // 1000
    minutes = total_sec // 60
    seconds = total_sec % 60
    return f"{minutes}:{seconds:02d}"


def _iso_week(date_str: str) -> str:
    """Get ISO week key 'YYYY-WNN' from 'YYYY-MM-DD HH:MM'."""
    dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _week_date_range(entries: list[dict]) -> tuple[str, str]:
    """Get earliest and latest date strings from entries."""
    dates = sorted(e["endTime"][:10] for e in entries)
    return dates[0], dates[-1]


def _load_json(path: Path) -> Any:
    """Load JSON file with UTF-8 encoding."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _resolve_export_dir(export_path: str) -> Path:
    """Resolve the export path — can be a ZIP or extracted directory."""
    p = Path(export_path)
    if p.suffix == ".zip":
        extract_dir = p.parent / p.stem
        if not extract_dir.exists():
            with zipfile.ZipFile(p) as zf:
                zf.extractall(extract_dir)
        p = extract_dir

    # Look for "Spotify Account Data" subfolder
    account_dir = p / "Spotify Account Data"
    if account_dir.exists():
        return account_dir
    return p


# Minimum ms to count as a real listen (skip <30s skips)
MIN_LISTEN_MS = 30_000


@register_adapter
class SpotifyExportAdapter(SeedAdapter):
    """Import listening history from a Spotify data export."""

    name = "spotify-export"
    description = "Import listening history from Spotify account data export"
    source_system = "seed:spotify-export"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.export_path = (
            (config or {}).get("export_path")
            or os.getenv("SPOTIFY_EXPORT_PATH")
            or ""
        )

    async def validate(self) -> tuple[bool, str]:
        if not self.export_path:
            return False, "No export_path configured and SPOTIFY_EXPORT_PATH not set"
        p = Path(self.export_path)
        if not p.exists():
            return False, f"Export path does not exist: {self.export_path}"
        return True, ""

    async def fetch(self, limit: int = 1000) -> list[SeedItem]:
        import asyncio
        return await asyncio.to_thread(self._fetch_sync, limit)

    def _fetch_sync(self, limit: int) -> list[SeedItem]:
        export_dir = _resolve_export_dir(self.export_path)
        items: list[SeedItem] = []

        # Music streaming history — weekly summaries
        music_files = sorted(export_dir.glob("StreamingHistory_music_*.json"))
        if music_files:
            all_music = []
            for f in music_files:
                all_music.extend(_load_json(f))
            items.extend(self._build_weekly_music_summaries(all_music))

        # Podcast streaming history — monthly summaries
        podcast_files = sorted(export_dir.glob("StreamingHistory_podcast_*.json"))
        if podcast_files:
            all_podcasts = []
            for f in podcast_files:
                all_podcasts.extend(_load_json(f))
            items.extend(self._build_podcast_summary(all_podcasts))

        # Audiobook streaming history — single summary
        audiobook_files = sorted(export_dir.glob("StreamingHistory_audiobook_*.json"))
        if audiobook_files:
            all_audiobooks = []
            for f in audiobook_files:
                all_audiobooks.extend(_load_json(f))
            items.extend(self._build_audiobook_summary(all_audiobooks))

        # Library snapshot
        library_file = export_dir / "YourLibrary.json"
        if library_file.exists():
            items.extend(self._build_library_snapshot(_load_json(library_file)))

        # Playlists
        playlist_file = export_dir / "Playlist1.json"
        if playlist_file.exists():
            pl_data = _load_json(playlist_file)
            # Can be {"playlists": [...]} or [...]
            if isinstance(pl_data, dict):
                pl_data = pl_data.get("playlists", [])
            items.extend(self._build_playlist_items(pl_data))

        # Search queries (interesting for recall)
        search_file = export_dir / "SearchQueries.json"
        if search_file.exists():
            items.extend(self._build_search_summary(_load_json(search_file)))

        logger.info(
            f"Spotify export: {len(items)} items from {export_dir}"
        )
        return items[:limit]

    def _build_weekly_music_summaries(self, entries: list[dict]) -> list[SeedItem]:
        """Group music plays by ISO week and create summary items."""
        # Filter out very short plays (skips)
        entries = [e for e in entries if e.get("msPlayed", 0) >= MIN_LISTEN_MS]

        by_week: dict[str, list[dict]] = defaultdict(list)
        for e in entries:
            week = _iso_week(e["endTime"])
            by_week[week].append(e)

        items = []
        for week_key in sorted(by_week.keys()):
            week_entries = by_week[week_key]
            start_date, end_date = _week_date_range(week_entries)

            total_ms = sum(e["msPlayed"] for e in week_entries)
            artist_ms: Counter = Counter()
            artist_plays: Counter = Counter()
            track_plays: Counter = Counter()

            for e in week_entries:
                artist = e["artistName"]
                track = f"{e['trackName']} — {artist}"
                artist_ms[artist] += e["msPlayed"]
                artist_plays[artist] += 1
                track_plays[track] += 1

            # Build content
            parts = [
                f"# Spotify Listening — {week_key} ({start_date} to {end_date})",
                "",
                f"**Total listening time:** {_ms_to_hm(total_ms)}",
                f"**Tracks played:** {len(week_entries)}",
                f"**Unique artists:** {len(artist_plays)}",
                "",
                "## Top Artists",
                "",
                "| # | Artist | Plays | Time |",
                "|---|--------|-------|------|",
            ]

            for i, (artist, ms) in enumerate(artist_ms.most_common(10), 1):
                plays = artist_plays[artist]
                parts.append(
                    f"| {i} | {artist} | {plays} | {_ms_to_hm(ms)} |"
                )

            parts.extend(["", "## Most Played Tracks", ""])
            parts.extend([
                "| # | Track | Plays |",
                "|---|-------|-------|",
            ])
            for i, (track, count) in enumerate(track_plays.most_common(10), 1):
                parts.append(f"| {i} | {track} | {count} |")

            # Determine dominant genre/mood from top artists
            top_artists = [a for a, _ in artist_ms.most_common(3)]
            topics = ["spotify", "music", "listening", "weekly-summary"]

            dt = datetime.strptime(start_date, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )

            items.append(SeedItem(
                title=f"Spotify Listening — {week_key}",
                content="\n".join(parts),
                source_url=f"spotify://export/weekly/{week_key}",
                topics=topics,
                created_at=dt,
                metadata={
                    "track_count": len(week_entries),
                    "total_ms": total_ms,
                    "listening_hours": round(total_ms / 3_600_000, 1),
                    "unique_artists": len(artist_plays),
                    "top_artists": top_artists,
                    "week": week_key,
                    "date_range": f"{start_date} to {end_date}",
                },
            ))

        return items

    def _build_podcast_summary(self, entries: list[dict]) -> list[SeedItem]:
        """Create monthly podcast listening summaries."""
        entries = [e for e in entries if e.get("msPlayed", 0) >= MIN_LISTEN_MS]
        if not entries:
            return []

        by_month: dict[str, list[dict]] = defaultdict(list)
        for e in entries:
            month = e["endTime"][:7]  # YYYY-MM
            by_month[month].append(e)

        items = []
        for month_key in sorted(by_month.keys()):
            month_entries = by_month[month_key]
            total_ms = sum(e["msPlayed"] for e in month_entries)

            show_ms: Counter = Counter()
            show_eps: Counter = Counter()
            for e in month_entries:
                show = e.get("podcastName", "Unknown")
                show_ms[show] += e["msPlayed"]
                show_eps[show] += 1

            parts = [
                f"# Spotify Podcasts — {month_key}",
                "",
                f"**Total listening time:** {_ms_to_hm(total_ms)}",
                f"**Episodes played:** {len(month_entries)}",
                f"**Shows:** {len(show_ms)}",
                "",
                "| # | Show | Episodes | Time |",
                "|---|------|----------|------|",
            ]

            for i, (show, ms) in enumerate(show_ms.most_common(15), 1):
                eps = show_eps[show]
                parts.append(f"| {i} | {show} | {eps} | {_ms_to_hm(ms)} |")

            # List individual episodes
            parts.extend(["", "## Episodes", ""])
            for e in month_entries:
                show = e.get("podcastName", "Unknown")
                ep = e.get("episodeName", "Unknown")
                parts.append(f"- **{show}**: {ep} ({_ms_to_hm(e['msPlayed'])})")

            dt = datetime.strptime(f"{month_key}-01", "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )

            items.append(SeedItem(
                title=f"Spotify Podcasts — {month_key}",
                content="\n".join(parts),
                source_url=f"spotify://export/podcasts/{month_key}",
                topics=["spotify", "podcasts", "listening", "monthly-summary"],
                created_at=dt,
                metadata={
                    "episode_count": len(month_entries),
                    "total_ms": total_ms,
                    "shows": list(show_ms.keys()),
                },
            ))

        return items

    def _build_audiobook_summary(self, entries: list[dict]) -> list[SeedItem]:
        """Create a single audiobook listening summary."""
        entries = [e for e in entries if e.get("msPlayed", 0) >= MIN_LISTEN_MS]
        if not entries:
            return []

        total_ms = sum(e["msPlayed"] for e in entries)

        # Group by "artistName" (author) or "trackName" (chapter/title)
        # Audiobook entries use same schema as music
        by_book: dict[str, int] = Counter()
        for e in entries:
            book_key = e.get("artistName", "Unknown")
            by_book[book_key] += e["msPlayed"]

        parts = [
            "# Spotify Audiobooks — Listening Summary",
            "",
            f"**Total listening time:** {_ms_to_hm(total_ms)}",
            f"**Chapters/sections played:** {len(entries)}",
            "",
            "| # | Title/Author | Time |",
            "|---|-------------|------|",
        ]

        for i, (book, ms) in enumerate(by_book.most_common(20), 1):
            parts.append(f"| {i} | {book} | {_ms_to_hm(ms)} |")

        date_range = sorted(e["endTime"][:10] for e in entries)
        dt = datetime.strptime(date_range[0], "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )

        return [SeedItem(
            title="Spotify Audiobooks — Listening Summary",
            content="\n".join(parts),
            source_url="spotify://export/audiobooks/summary",
            topics=["spotify", "audiobooks", "listening"],
            created_at=dt,
            metadata={
                "total_ms": total_ms,
                "entry_count": len(entries),
                "date_range": f"{date_range[0]} to {date_range[-1]}",
            },
        )]

    def _build_library_snapshot(self, library: dict) -> list[SeedItem]:
        """Create a snapshot of the saved library."""
        parts = ["# Spotify Library Snapshot", ""]

        tracks = library.get("tracks", [])
        if tracks:
            parts.extend([
                f"## Saved Tracks ({len(tracks)})",
                "",
                "| Track | Artist | Album |",
                "|-------|--------|-------|",
            ])
            for t in tracks:
                parts.append(
                    f"| {t.get('track', '?')} | {t.get('artist', '?')} "
                    f"| {t.get('album', '?')} |"
                )
            parts.append("")

        artists = library.get("artists", [])
        if artists:
            parts.extend([
                f"## Followed Artists ({len(artists)})",
                "",
            ])
            for a in artists:
                parts.append(f"- {a.get('name', a.get('artist', '?'))}")
            parts.append("")

        shows = library.get("shows", [])
        if shows:
            parts.extend([
                f"## Followed Podcasts ({len(shows)})",
                "",
            ])
            for s in shows:
                parts.append(
                    f"- **{s.get('name', '?')}** by {s.get('publisher', '?')}"
                )
            parts.append("")

        albums = library.get("albums", [])
        if albums:
            parts.extend([
                f"## Saved Albums ({len(albums)})",
                "",
            ])
            for a in albums:
                parts.append(
                    f"- {a.get('album', '?')} — {a.get('artist', '?')}"
                )

        return [SeedItem(
            title="Spotify Library Snapshot",
            content="\n".join(parts),
            source_url="spotify://export/library/snapshot",
            topics=["spotify", "music", "library"],
            created_at=datetime.now(timezone.utc),
            metadata={
                "track_count": len(tracks),
                "artist_count": len(artists),
                "show_count": len(shows),
                "album_count": len(albums),
            },
        )]

    def _build_playlist_items(self, playlists: list[dict]) -> list[SeedItem]:
        """Create an item for each playlist."""
        items = []
        for pl in playlists:
            name = pl.get("name", "Untitled Playlist")
            tracks = pl.get("items", [])
            if not tracks:
                continue

            parts = [
                f"# Spotify Playlist: {name}",
                "",
                f"**Tracks:** {len(tracks)}",
                "",
                "| # | Track | Artist | Album |",
                "|---|-------|--------|-------|",
            ]

            artists_seen = set()
            for i, t in enumerate(tracks, 1):
                track_info = t.get("track", t)
                track_name = track_info.get("trackName", track_info.get("track", "?"))
                artist = track_info.get("artistName", track_info.get("artist", "?"))
                album = track_info.get("albumName", track_info.get("album", "?"))
                parts.append(f"| {i} | {track_name} | {artist} | {album} |")
                artists_seen.add(artist)

            items.append(SeedItem(
                title=f"Spotify Playlist: {name}",
                content="\n".join(parts),
                source_url=f"spotify://export/playlist/{name}",
                topics=["spotify", "music", "playlist"],
                created_at=datetime.now(timezone.utc),
                metadata={
                    "track_count": len(tracks),
                    "unique_artists": len(artists_seen),
                    "playlist_name": name,
                },
            ))

        return items

    def _build_search_summary(self, queries: list[dict]) -> list[SeedItem]:
        """Summarise search queries as a single item."""
        if not queries:
            return []

        parts = [
            "# Spotify Search History",
            "",
            f"**Total searches:** {len(queries)}",
            "",
            "| Date | Query | Platform |",
            "|------|-------|----------|",
        ]

        for q in queries[-100:]:  # Last 100
            search_time = q.get("searchTime", q.get("timestamp", "?"))
            query = q.get("searchQuery", q.get("query", "?"))
            platform = q.get("platform", "?")
            parts.append(f"| {search_time} | {query} | {platform} |")

        return [SeedItem(
            title="Spotify Search History",
            content="\n".join(parts),
            source_url="spotify://export/searches/summary",
            topics=["spotify", "search-history"],
            created_at=datetime.now(timezone.utc),
            metadata={"query_count": len(queries)},
        )]

    def get_default_topics(self) -> list[str]:
        return ["spotify", "music"]
