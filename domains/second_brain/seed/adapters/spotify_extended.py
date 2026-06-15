"""Spotify extended streaming history adapter.

Parses the GDPR "extended streaming history" export (master_metadata schema,
Streaming_History_Audio_*.json) — the full account lifetime, 2010 onwards,
including podcast and audiobook plays which the live recently-played API
never returns. Complements spotify_export.py, which handles the standard
1-year account-data export's older endTime/artistName schema.

Drop the export ZIP (my_spotify_data*.zip) or extracted JSON into
``data/spotify_export/``. Only the main account's "Spotify Extended
Streaming History" folder is read — Kids account folders are skipped so the
listening profile stays Chris's.

Aggregation keeps item volume sane:
- music      → one summary per month (hours, top artists/tracks)
- podcasts   → one item per show (hours, episodes, date range)
- audiobooks → one item per book (hours, chapters, date range)
"""

import json
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter

EXPORT_DIR = Path(__file__).resolve().parents[4] / "data" / "spotify_export"

MIN_LISTEN_MS = 30_000  # skip <30s skips
KIDS_MARKER = "Kids"


def _hours(ms: int) -> float:
    return round(ms / 3_600_000, 1)


def _load_records() -> list[dict]:
    """Extended-history records from ZIPs/JSON in EXPORT_DIR (main account only)."""
    records: list[dict] = []

    def _maybe_extend(name: str, raw: bytes):
        base = name.rsplit("/", 1)[-1]
        if KIDS_MARKER in name or not base.startswith("Streaming_History_Audio"):
            return
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                records.extend(data)
        except json.JSONDecodeError:
            logger.warning(f"Spotify extended export: could not parse {name}")

    if not EXPORT_DIR.exists():
        return records
    for path in sorted(EXPORT_DIR.glob("*")):
        if path.suffix == ".zip":
            with zipfile.ZipFile(path) as zf:
                for name in zf.namelist():
                    if name.endswith(".json"):
                        _maybe_extend(name, zf.read(name))
        elif path.suffix == ".json":
            _maybe_extend(path.name, path.read_bytes())
    return records


@register_adapter
class SpotifyExtendedAdapter(SeedAdapter):
    """Backfill full listening history from the extended streaming export."""

    name = "spotify-extended"
    description = "Backfill from Spotify extended streaming history in data/spotify_export/"
    source_system = "seed:spotify-export"

    async def validate(self) -> tuple[bool, str]:
        return True, ""  # empty dir is the normal steady state

    async def fetch(self, limit: int = 500) -> list[SeedItem]:
        import asyncio
        records = await asyncio.to_thread(_load_records)
        if not records:
            return []

        music_by_month: dict[str, dict] = defaultdict(lambda: {
            "ms": 0, "plays": 0, "artists": defaultdict(int), "tracks": defaultdict(int)})
        shows: dict[str, dict] = defaultdict(lambda: {
            "ms": 0, "episodes": set(), "first": None, "last": None})
        books: dict[str, dict] = defaultdict(lambda: {
            "ms": 0, "chapters": set(), "first": None, "last": None, "uri": ""})

        for r in records:
            ts = r.get("ts", "")
            ms = r.get("ms_played", 0) or 0
            if not ts or ms < MIN_LISTEN_MS:
                continue
            day = ts[:10]

            if r.get("audiobook_title"):
                b = books[r["audiobook_title"]]
                b["ms"] += ms
                b["uri"] = r.get("audiobook_uri") or b["uri"]
                if r.get("audiobook_chapter_title"):
                    b["chapters"].add(r["audiobook_chapter_title"])
                b["first"] = min(b["first"] or day, day)
                b["last"] = max(b["last"] or day, day)
            elif r.get("episode_show_name"):
                s = shows[r["episode_show_name"]]
                s["ms"] += ms
                if r.get("episode_name"):
                    s["episodes"].add(r["episode_name"])
                s["first"] = min(s["first"] or day, day)
                s["last"] = max(s["last"] or day, day)
            elif r.get("master_metadata_track_name"):
                m = music_by_month[ts[:7]]
                m["ms"] += ms
                m["plays"] += 1
                artist = r.get("master_metadata_album_artist_name") or "?"
                m["artists"][artist] += ms
                m["tracks"][f"{r['master_metadata_track_name']} — {artist}"] += 1

        items: list[SeedItem] = []

        for title, b in sorted(books.items(), key=lambda kv: -kv[1]["ms"]):
            items.append(SeedItem(
                title=f"Spotify Audiobook Listening: {title}",
                content="\n".join([
                    f"# {title} (Spotify audiobook)",
                    "",
                    f"**Total listened:** {_hours(b['ms'])}h",
                    f"**Chapters played:** {len(b['chapters'])}",
                    f"**Listened:** {b['first']} → {b['last']}",
                ]),
                source_url=f"spotify://export/audiobook/{b['uri'] or title}",
                topics=["spotify", "audiobooks", "books", "listening"],
                created_at=datetime.fromisoformat(f"{b['last']}T21:00:00+00:00"),
                metadata={"hours": _hours(b["ms"]), "first": b["first"], "last": b["last"],
                          "chapters": len(b["chapters"])},
                content_type="listening_history",
            ))

        for show, s in sorted(shows.items(), key=lambda kv: -kv[1]["ms"]):
            items.append(SeedItem(
                title=f"Spotify Podcast: {show}",
                content="\n".join([
                    f"# {show} (podcast)",
                    "",
                    f"**Total listened:** {_hours(s['ms'])}h across {len(s['episodes'])} episodes",
                    f"**Listened:** {s['first']} → {s['last']}",
                ]),
                source_url=f"spotify://export/podcast/{show}",
                topics=["spotify", "podcasts", "listening"],
                created_at=datetime.fromisoformat(f"{s['last']}T21:00:00+00:00"),
                metadata={"hours": _hours(s["ms"]), "episodes": len(s["episodes"])},
                content_type="listening_history",
            ))

        for month, m in sorted(music_by_month.items()):
            top_artists = sorted(m["artists"].items(), key=lambda kv: -kv[1])[:10]
            top_tracks = sorted(m["tracks"].items(), key=lambda kv: -kv[1])[:10]
            items.append(SeedItem(
                title=f"Spotify Music History — {month}",
                content="\n".join(
                    [f"# Spotify Music — {month}", "",
                     f"**Total:** {_hours(m['ms'])}h across {m['plays']} plays", "",
                     "## Top Artists", ""]
                    + [f"- {a} ({_hours(a_ms)}h)" for a, a_ms in top_artists]
                    + ["", "## Top Tracks", ""]
                    + [f"- {t} ({n} plays)" for t, n in top_tracks]
                ),
                source_url=f"spotify://export/music/{month}",
                topics=["spotify", "music", "listening", "monthly-summary"],
                created_at=datetime.fromisoformat(f"{month}-28T21:00:00+00:00"),
                metadata={"hours": _hours(m["ms"]), "plays": m["plays"]},
                content_type="listening_history",
            ))

        logger.info(
            f"Spotify extended export: {len(records)} plays → {len(books)} audiobooks, "
            f"{len(shows)} podcasts, {len(music_by_month)} music months"
        )
        return items[:limit]

    def get_default_topics(self) -> list[str]:
        return ["spotify", "listening"]
