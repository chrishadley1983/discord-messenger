"""Garmin activities adapter.

Imports notable training activities from Garmin Connect.
"""

import os
from datetime import datetime, timedelta
from typing import Any

import httpx

from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter


@register_adapter
class GarminActivitiesAdapter(SeedAdapter):
    """Import notable Garmin activities (races, long runs, PRs)."""

    name = "garmin-activities"
    description = "Import notable training activities from Garmin"
    source_system = "seed:garmin"

    # Activity types worth importing
    NOTABLE_TYPES = [
        "running",
        "trail_running",
        "treadmill_running",
        "cycling",
        "swimming",
        "hiking",
    ]

    def __init__(self, config: dict = None):
        super().__init__(config)
        # Use Hadley API for Garmin data
        self.api_base = config.get("api_base", "http://172.19.64.1:8100") if config else "http://172.19.64.1:8100"
        self.min_distance_km = config.get("min_distance_km", 10) if config else 10  # Only import runs > 10km

    async def validate(self) -> tuple[bool, str]:
        # Check if Hadley API is reachable
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_base}/health",
                    timeout=5,
                )
                if response.status_code == 200:
                    return True, ""
                return False, f"Hadley API returned {response.status_code}"
        except Exception as e:
            return False, f"Cannot reach Hadley API: {e}"

    async def fetch(self, limit: int = 100) -> list[SeedItem]:
        items = []

        try:
            async with httpx.AsyncClient() as client:
                # Get recent activities
                response = await client.get(
                    f"{self.api_base}/garmin/activities",
                    params={"limit": limit * 2},  # Fetch more, filter later
                    timeout=30,
                )

                if response.status_code != 200:
                    logger.error(f"Garmin API error: {response.status_code}")
                    return items

                activities = response.json()

                for activity in activities:
                    # Filter for notable activities
                    if not self._is_notable(activity):
                        continue

                    item = self._activity_to_item(activity)
                    if item:
                        items.append(item)

                    if len(items) >= limit:
                        break

        except Exception as e:
            logger.error(f"Failed to fetch Garmin activities: {e}")

        return items

    def _is_notable(self, activity: dict) -> bool:
        """Check if activity is worth importing."""
        activity_type = activity.get("activityType", {}).get("typeKey", "").lower()

        # Must be a relevant activity type
        if activity_type not in self.NOTABLE_TYPES:
            return False

        # For running, must be > min distance
        if "running" in activity_type:
            distance_m = activity.get("distance", 0)
            if distance_m / 1000 < self.min_distance_km:
                return False

        return True

    def _activity_to_item(self, activity: dict) -> SeedItem | None:
        """Convert Garmin activity to SeedItem."""
        try:
            name = activity.get("activityName", "Activity")
            activity_type = activity.get("activityType", {}).get("typeKey", "unknown")
            start_time = activity.get("startTimeLocal", "")

            # Parse metrics
            distance_km = activity.get("distance", 0) / 1000
            duration_sec = activity.get("duration", 0)
            duration_min = duration_sec / 60
            avg_hr = activity.get("averageHR", 0)
            calories = activity.get("calories", 0)

            # Calculate pace for running
            pace_str = ""
            if "running" in activity_type.lower() and distance_km > 0:
                pace_min_per_km = duration_min / distance_km
                pace_min = int(pace_min_per_km)
                pace_sec = int((pace_min_per_km - pace_min) * 60)
                pace_str = f"{pace_min}:{pace_sec:02d}/km"

            # Build content
            content_parts = [
                f"# {name}",
                "",
                f"**Type:** {activity_type.replace('_', ' ').title()}",
                f"**Date:** {start_time}",
                f"**Distance:** {distance_km:.2f} km",
                f"**Duration:** {int(duration_min)} minutes",
            ]

            if pace_str:
                content_parts.append(f"**Pace:** {pace_str}")
            if avg_hr:
                content_parts.append(f"**Avg HR:** {avg_hr} bpm")
            if calories:
                content_parts.append(f"**Calories:** {calories}")

            # Parse date
            created_at = None
            if start_time:
                try:
                    created_at = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                except ValueError:
                    pass

            return SeedItem(
                title=name,
                content="\n".join(content_parts),
                source_url=f"https://connect.garmin.com/modern/activity/{activity.get('activityId')}",
                source_id=str(activity.get("activityId")),
                topics=self._extract_topics(activity),
                created_at=created_at,
                metadata={
                    "distance_km": distance_km,
                    "duration_min": duration_min,
                    "activity_type": activity_type,
                },
            )

        except Exception as e:
            logger.warning(f"Failed to parse activity: {e}")
            return None

    def _extract_topics(self, activity: dict) -> list[str]:
        """Extract topics from activity."""
        topics = ["garmin", "fitness"]

        activity_type = activity.get("activityType", {}).get("typeKey", "").lower()

        if "running" in activity_type:
            topics.extend(["running", "training"])
            # Check for race-like activities
            name = activity.get("activityName", "").lower()
            distance_km = activity.get("distance", 0) / 1000
            if any(w in name for w in ["race", "parkrun", "marathon", "half"]):
                topics.append("race")
            elif distance_km >= 21:
                topics.append("long-run")

        elif "cycling" in activity_type:
            topics.append("cycling")

        return list(set(topics))

    def get_default_topics(self) -> list[str]:
        return ["garmin", "fitness", "training"]
