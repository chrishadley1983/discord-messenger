"""Calendar events adapter.

Imports all events from Google Calendar for the past 5 years.
"""

from datetime import datetime, timedelta

import httpx

from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter


@register_adapter
class CalendarEventsAdapter(SeedAdapter):
    """Import all calendar events."""

    name = "calendar-events"
    description = "Import all events from Google Calendar"
    source_system = "seed:gcal"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.api_base = config.get("api_base", "http://172.19.64.1:8100") if config else "http://172.19.64.1:8100"
        # Default to 5 years of history
        self.years_back = config.get("years_back", 5) if config else 5

    async def validate(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_base}/calendar/today",
                    timeout=5,
                )
                if response.status_code == 200:
                    return True, ""
                return False, f"Calendar API returned {response.status_code}"
        except Exception as e:
            return False, f"Cannot reach calendar API: {e}"

    async def fetch(self, limit: int = 5000) -> list[SeedItem]:
        """Fetch all calendar events from the last N years."""
        items = []

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                end_date = datetime.now().strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=365 * self.years_back)).strftime("%Y-%m-%d")

                logger.info(f"Fetching calendar events from {start_date} to {end_date}...")

                response = await client.get(
                    f"{self.api_base}/calendar/range",
                    params={"start_date": start_date, "end_date": end_date},
                    timeout=60,
                )

                if response.status_code != 200:
                    logger.error(f"Calendar API error: {response.status_code}")
                    return items

                data = response.json()
                events = data.get("events", [])

                logger.info(f"Found {len(events)} calendar events")

                # Convert all events to SeedItems
                for event in events:
                    item = self._event_to_item(event)
                    if item:
                        items.append(item)

                    if len(items) >= limit:
                        break

                logger.info(f"Returning {len(items)} calendar events for import")

        except Exception as e:
            logger.error(f"Failed to fetch calendar data: {e}")
            import traceback
            traceback.print_exc()

        return items[:limit]

    def _event_to_item(self, event: dict) -> SeedItem | None:
        """Convert a calendar event to SeedItem."""
        try:
            summary = event.get("summary", "").strip()
            if not summary:
                return None

            # Parse start date/time
            start = event.get("start", "")
            if isinstance(start, str):
                date_str = start[:10]
                time_str = start[11:16] if len(start) > 10 and "T" in start else ""
            else:
                date_str = start.get("date") or start.get("dateTime", "")[:10]
                time_str = start.get("dateTime", "")[11:16] if start.get("dateTime") else ""

            # Parse end date/time
            end = event.get("end", "")
            if isinstance(end, str):
                end_date_str = end[:10]
            else:
                end_date_str = end.get("date") or end.get("dateTime", "")[:10]

            # Determine if all-day event
            is_all_day = not time_str

            # Get location and description
            location = event.get("location", "")
            description = event.get("description", "")

            # Build content
            content_parts = [f"# {summary}", ""]

            if is_all_day:
                if date_str != end_date_str:
                    content_parts.append(f"**Date:** {date_str} to {end_date_str}")
                else:
                    content_parts.append(f"**Date:** {date_str}")
            else:
                content_parts.append(f"**Date:** {date_str} at {time_str}")

            if location:
                content_parts.append(f"**Location:** {location}")

            if description:
                # Truncate long descriptions
                desc = description[:1000] + "..." if len(description) > 1000 else description
                content_parts.extend(["", desc])

            # Parse created_at from date
            created_at = None
            try:
                if time_str:
                    created_at = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
                else:
                    created_at = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                pass

            return SeedItem(
                title=summary,
                content="\n".join(content_parts),
                source_id=event.get("id"),
                topics=self._extract_topics(summary, event),
                created_at=created_at,
                metadata={
                    "date": date_str,
                    "time": time_str or None,
                    "location": location or None,
                    "is_all_day": is_all_day,
                },
            )

        except Exception as e:
            logger.warning(f"Failed to parse calendar event: {e}")
            return None

    def _extract_topics(self, name: str, event: dict) -> list[str]:
        """Extract topics from event."""
        topics = ["calendar"]
        name_lower = name.lower()

        # Family/personal
        if "birthday" in name_lower or "anniversary" in name_lower:
            topics.extend(["family", "key-date"])
        if any(w in name_lower for w in ["school", "pickup", "drop", "parents evening"]):
            topics.extend(["family", "school"])

        # Health
        if any(w in name_lower for w in ["dentist", "doctor", "gp", "hospital", "appointment", "optician"]):
            topics.append("health")

        # Fitness
        if any(w in name_lower for w in ["run", "running", "gym", "training", "parkrun", "race", "marathon"]):
            topics.extend(["fitness", "running"])

        # Work/business
        if any(w in name_lower for w in ["meeting", "call", "work", "interview", "conference"]):
            topics.append("business")

        # Travel
        if any(w in name_lower for w in ["flight", "train", "hotel", "stay at", "travel", "trip"]):
            topics.append("travel")

        # Hadley Bricks
        if any(w in name_lower for w in ["lego", "brick", "bricklink", "hb finances", "hadley bricks"]):
            topics.extend(["lego", "hadley-bricks"])

        # Social
        if any(w in name_lower for w in ["dinner", "lunch", "party", "bbq", "wedding", "reservation"]):
            topics.append("social")

        return list(set(topics))

    def get_default_topics(self) -> list[str]:
        return ["calendar"]
