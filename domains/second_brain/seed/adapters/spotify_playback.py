"""Spotify playback-log adapter — podcasts & audiobooks.

The spotify-listening adapter uses the recently-played API, which only
returns music. This adapter covers what that misses: it aggregates the
5-minute player snapshots from ``data/spotify_playback_log.jsonl``
(written by domains/peterbot/spotify_playback_log.py) into daily
podcast/audiobook listening summaries with progress positions, and imports
the saved-audiobook library as individual items.

Audiobooks surface as shows/episodes in the player API, so podcast entries
are reclassified as audiobooks when their parent_uri matches the saved
audiobook library.

Only completed days (yesterday and older) are emitted — the seed runner
dedupes by source_url and never updates, so a partial today-summary would
freeze mid-day.
"""

import json
from datetime import date, datetime
from pathlib import Path

from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter
from .spotify import _get_spotify_client

LOG_PATH = Path(__file__).resolve().parents[4] / "data" / "spotify_playback_log.jsonl"

POLL_INTERVAL_MIN = 5  # must match the poller's schedule in bot.py


def _fmt_hm(ms: int) -> str:
    total_min = ms // 60000
    return f"{total_min // 60}h{total_min % 60:02d}m"


@register_adapter
class SpotifyPlaybackAdapter(SeedAdapter):
    """Daily podcast/audiobook listening summaries + saved audiobook library."""

    name = "spotify-playback"
    description = "Spotify podcast & audiobook listening (playback log) and saved audiobooks"
    source_system = "seed:spotify"

    async def validate(self) -> tuple[bool, str]:
        return True, ""  # log file may simply not exist yet — fetch handles it

    async def fetch(self, limit: int = 100) -> list[SeedItem]:
        items: list[SeedItem] = []
        audiobook_uris, library = await self._load_audiobook_library()
        items.extend(library)

        if not LOG_PATH.exists():
            return items[:limit]

        # Group log entries by completed day, skipping music (covered by the
        # recently-played adapter) and today (runner never updates items).
        today = date.today().isoformat()
        by_day: dict[str, list[dict]] = {}
        for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            day = entry.get("ts", "")[:10]
            if not day or day >= today or entry.get("kind") == "music":
                continue
            by_day.setdefault(day, []).append(entry)

        for day, entries in sorted(by_day.items()):
            items.append(self._summarise_day(day, entries, audiobook_uris))

        return items[:limit]

    async def _load_audiobook_library(self) -> tuple[set[str], list[SeedItem]]:
        """Saved audiobook URIs (for reclassification) + one item per book."""
        import asyncio
        try:
            sp = await asyncio.to_thread(_get_spotify_client)
            results = await asyncio.to_thread(
                lambda: sp.current_user_saved_audiobooks(limit=50)
                if hasattr(sp, "current_user_saved_audiobooks")
                else sp._get("me/audiobooks", limit=50)
            )
        except Exception as e:
            logger.warning(f"Saved audiobooks unavailable: {e}")
            return set(), []

        uris: set[str] = set()
        items: list[SeedItem] = []
        for it in results.get("items", []):
            book = it.get("audiobook") or it
            uri = book.get("uri", "")
            if not uri:
                continue
            uris.add(uri)
            authors = ", ".join(a.get("name", "") for a in book.get("authors", []))
            narrators = ", ".join(n.get("name", "") for n in book.get("narrators", []))
            items.append(SeedItem(
                title=f"Spotify Audiobook: {book.get('name', 'Unknown')}",
                content="\n".join([
                    f"# {book.get('name', 'Unknown')}",
                    "",
                    f"**Author(s):** {authors}",
                    f"**Narrator(s):** {narrators}",
                    f"**Chapters:** {book.get('total_chapters', '?')}",
                    "",
                    "Saved in Chris's Spotify audiobook library.",
                    "",
                    (book.get("description") or "")[:500],
                ]),
                source_url=f"spotify://audiobook/{uri}",
                topics=["spotify", "audiobooks", "books", "library"],
                created_at=datetime.now().astimezone(),
                metadata={"uri": uri, "authors": authors, "narrators": narrators},
                content_type="listening_history",
            ))
        return uris, items

    def _summarise_day(self, day: str, entries: list[dict], audiobook_uris: set[str]) -> SeedItem:
        # Aggregate per item: poll count ≈ minutes listened, max progress.
        agg: dict[str, dict] = {}
        for e in entries:
            kind = e.get("kind", "podcast")
            if kind == "podcast" and e.get("parent_uri") in audiobook_uris:
                kind = "audiobook"
            key = f"{e.get('parent', '')}::{e.get('name', '')}"
            a = agg.setdefault(key, {
                "kind": kind,
                "name": e.get("name", "Unknown"),
                "parent": e.get("parent", ""),
                "creators": e.get("creators", []),
                "polls": 0,
                "max_progress_ms": 0,
                "duration_ms": e.get("duration_ms", 0),
            })
            a["polls"] += 1
            a["max_progress_ms"] = max(a["max_progress_ms"], e.get("progress_ms", 0))

        audiobooks = [a for a in agg.values() if a["kind"] == "audiobook"]
        podcasts = [a for a in agg.values() if a["kind"] != "audiobook"]

        content = [f"# Spotify Podcasts & Audiobooks — {day}", ""]
        for label, group in (("Audiobooks", audiobooks), ("Podcasts", podcasts)):
            if not group:
                continue
            content.extend([f"## {label}", ""])
            for a in sorted(group, key=lambda x: -x["polls"]):
                mins = a["polls"] * POLL_INTERVAL_MIN
                creators = ", ".join(a["creators"])
                line = f"- **{a['parent'] or a['name']}**"
                if a["parent"] and a["name"] != a["parent"]:
                    line += f" — {a['name']}"
                if creators:
                    line += f" ({creators})"
                line += f" — ~{mins} min listened"
                if a["max_progress_ms"] and a["duration_ms"]:
                    pct = round(100 * a["max_progress_ms"] / a["duration_ms"])
                    line += f", reached {_fmt_hm(a['max_progress_ms'])} of {_fmt_hm(a['duration_ms'])} ({pct}%)"
                content.append(line)
            content.append("")

        topics = ["spotify", "listening"]
        if audiobooks:
            topics += ["audiobooks", "books"]
        if podcasts:
            topics.append("podcasts")

        return SeedItem(
            title=f"Spotify Podcasts & Audiobooks — {day}",
            content="\n".join(content),
            source_url=f"spotify://playback/{day}",
            topics=topics,
            created_at=datetime.fromisoformat(f"{day}T21:00:00").astimezone(),
            metadata={
                "audiobook_count": len(audiobooks),
                "podcast_count": len(podcasts),
                "poll_entries": len(entries),
            },
            content_type="listening_history",
        )

    def get_default_topics(self) -> list[str]:
        return ["spotify", "music"]
