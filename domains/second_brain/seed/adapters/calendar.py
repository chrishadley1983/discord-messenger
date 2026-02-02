"""Calendar patterns adapter.

Imports recurring patterns and key dates from Google Calendar.
"""

from datetime import datetime, timedelta
from collections import Counter

import httpx

from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter


@register_adapter
class CalendarPatternsAdapter(SeedAdapter):
    """Import calendar patterns and key dates."""

    name = "calendar-patterns"
    description = "Import recurring events and key dates from calendar"
    source_system = "seed:gcal"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.api_base = config.get("api_base", "http://172.19.64.1:8100") if config else "http://172.19.64.1:8100"
        # Default to 2 years of history for better pattern detection
        self.days_back = config.get("days_back", 730) if config else 730

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

    async def fetch(self, limit: int = 100) -> list[SeedItem]:
        items = []

        try:
            # Fetch events from the past N days to find patterns
            async with httpx.AsyncClient() as client:
                end_date = datetime.now().strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=self.days_back)).strftime("%Y-%m-%d")

                response = await client.get(
                    f"{self.api_base}/calendar/range",
                    params={"start_date": start_date, "end_date": end_date},
                    timeout=30,
                )

                if response.status_code != 200:
                    logger.error(f"Calendar API error: {response.status_code}")
                    return items

                data = response.json()
                events = data.get("events", [])

                # Find recurring patterns
                patterns = self._find_patterns(events)
                for pattern in patterns[:limit // 2]:
                    items.append(pattern)

                # Find key dates (birthdays, anniversaries, etc.)
                key_dates = self._find_key_dates(events)
                for key_date in key_dates[:limit // 2]:
                    items.append(key_date)

        except Exception as e:
            logger.error(f"Failed to fetch calendar data: {e}")

        return items[:limit]

    def _find_patterns(self, events: list[dict]) -> list[SeedItem]:
        """Find recurring event patterns."""
        items = []

        # Count event names to find recurring ones
        name_counts = Counter()
        event_details = {}

        for event in events:
            name = event.get("summary", "").strip()
            if name:
                name_counts[name] += 1
                if name not in event_details:
                    event_details[name] = event

        # Import events that occur 2+ times
        for name, count in name_counts.most_common(20):
            if count < 2:
                break

            event = event_details[name]

            # Determine pattern frequency
            frequency = "recurring"
            if count >= self.days_back / 7:
                frequency = "weekly"
            elif count >= self.days_back / 30:
                frequency = "monthly"

            content = f"""# {name}

**Pattern:** {frequency} ({count} occurrences in {self.days_back} days)
**Type:** Calendar event

This is a recurring event in the calendar, indicating an important routine or commitment.
"""

            items.append(SeedItem(
                title=f"Pattern: {name}",
                content=content,
                topics=self._extract_topics(name, event),
                metadata={
                    "frequency": frequency,
                    "count": count,
                    "event_type": "pattern",
                },
            ))

        return items

    def _find_key_dates(self, events: list[dict]) -> list[SeedItem]:
        """Find key dates (birthdays, anniversaries, etc.)."""
        items = []

        key_phrases = ["birthday", "anniversary", "holiday", "appointment", "deadline"]

        seen = set()

        for event in events:
            name = event.get("summary", "").lower()

            # Check for key date indicators
            if any(phrase in name for phrase in key_phrases):
                original_name = event.get("summary", "")
                if original_name in seen:
                    continue
                seen.add(original_name)

                # Handle both string and dict formats for start
                start = event.get("start", "")
                if isinstance(start, str):
                    date_str = start[:10]  # "2024-08-05" or "2024-08-05T10:00:00Z"
                else:
                    date_str = start.get("date") or start.get("dateTime", "")[:10]

                content = f"""# {original_name}

**Date:** {date_str}
**Type:** Key date

This is an important date marked in the calendar.
"""

                items.append(SeedItem(
                    title=original_name,
                    content=content,
                    topics=["calendar", "key-date"] + self._extract_topics(name, event),
                    metadata={
                        "date": date_str,
                        "event_type": "key_date",
                    },
                ))

        return items

    def _extract_topics(self, name: str, event: dict) -> list[str]:
        """Extract topics from event."""
        topics = ["calendar"]
        name_lower = name.lower()

        if "birthday" in name_lower:
            topics.append("family")
        if any(w in name_lower for w in ["school", "pickup", "drop"]):
            topics.extend(["family", "school"])
        if any(w in name_lower for w in ["dentist", "doctor", "appointment"]):
            topics.append("health")
        if any(w in name_lower for w in ["run", "gym", "training", "parkrun"]):
            topics.extend(["fitness", "running"])
        if any(w in name_lower for w in ["meeting", "call", "work"]):
            topics.append("business")

        return list(set(topics))

    def get_default_topics(self) -> list[str]:
        return ["calendar"]
