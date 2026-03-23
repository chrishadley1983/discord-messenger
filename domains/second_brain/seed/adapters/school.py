"""School newsletter adapter.

Imports events, newsletters, and spellings from the existing Stocks Green
school tables in Supabase.
"""

from datetime import datetime, timedelta, timezone

import httpx

from config import SUPABASE_URL, SUPABASE_KEY
from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter


def _get_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


@register_adapter
class SchoolAdapter(SeedAdapter):
    """Import school events, newsletters, and spellings from Supabase."""

    name = "school-data"
    description = "Stocks Green school events, newsletters, and spellings"
    source_system = "seed:school"

    def get_default_topics(self) -> list[str]:
        return ["school", "stocks-green"]

    async def validate(self) -> tuple[bool, str]:
        if not SUPABASE_URL or not SUPABASE_KEY:
            return False, "Supabase credentials not configured"
        return True, ""

    async def fetch(self, limit: int = 50) -> list[SeedItem]:
        items = []
        rest_url = f"{SUPABASE_URL}/rest/v1"
        lookback = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()

        async with httpx.AsyncClient(timeout=30) as client:
            # School events
            try:
                response = await client.get(
                    f"{rest_url}/school_events?order=event_date.desc&limit={limit}"
                    f"&created_at=gte.{lookback}",
                    headers=_get_headers(),
                )
                if response.status_code == 200:
                    for event in response.json():
                        event_id = event.get("id")
                        title = event.get("title", "School Event")
                        event_date = event.get("event_date", "")
                        child = event.get("child_name", "")
                        description = event.get("description", "")

                        content = f"# {title}\n\nDate: {event_date}\n"
                        if child:
                            content += f"Child: {child}\n"
                        if description:
                            content += f"\n{description}"

                        topics = ["school", "stocks-green"]
                        if child:
                            topics.append(child.lower())

                        items.append(SeedItem(
                            title=title,
                            content=content,
                            source_url=f"school-event://{event_id}",
                            source_id=str(event_id),
                            topics=topics,
                            created_at=_parse_dt(event.get("created_at")),
                            content_type="calendar_event",
                        ))
            except Exception as e:
                logger.warning(f"Failed to fetch school events: {e}")

            # School newsletters
            try:
                response = await client.get(
                    f"{rest_url}/school_newsletters?order=published_at.desc&limit={limit}"
                    f"&created_at=gte.{lookback}",
                    headers=_get_headers(),
                )
                if response.status_code == 200:
                    for nl in response.json():
                        nl_id = nl.get("id")
                        title = nl.get("title", "Newsletter")
                        content = nl.get("content", "")
                        published = nl.get("published_at", "")

                        items.append(SeedItem(
                            title=f"Newsletter: {title}",
                            content=f"# {title}\n\nPublished: {published}\n\n{content}",
                            source_url=f"school-newsletter://{nl_id}",
                            source_id=str(nl_id),
                            topics=["school", "stocks-green", "newsletter"],
                            created_at=_parse_dt(nl.get("created_at")),
                            content_type="document",
                        ))
            except Exception as e:
                logger.warning(f"Failed to fetch school newsletters: {e}")

            # School spellings
            try:
                response = await client.get(
                    f"{rest_url}/school_spellings?order=week_starting.desc&limit={limit}"
                    f"&created_at=gte.{lookback}",
                    headers=_get_headers(),
                )
                if response.status_code == 200:
                    for sp in response.json():
                        sp_id = sp.get("id")
                        child = sp.get("child_name", "")
                        week = sp.get("week_starting", "")
                        words = sp.get("words", [])

                        if not words:
                            continue

                        word_list = ", ".join(words) if isinstance(words, list) else str(words)
                        content = f"# Spellings: {child} — Week of {week}\n\nWords: {word_list}"

                        topics = ["school", "spellings"]
                        if child:
                            topics.append(child.lower())

                        items.append(SeedItem(
                            title=f"Spellings: {child} — {week}",
                            content=content,
                            source_url=f"school-spellings://{sp_id}",
                            source_id=str(sp_id),
                            topics=topics,
                            created_at=_parse_dt(sp.get("created_at")),
                            content_type="note",
                        ))
            except Exception as e:
                logger.warning(f"Failed to fetch school spellings: {e}")

        logger.info(f"Fetched {len(items)} school items")
        return items[:limit]


def _parse_dt(val) -> datetime | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
