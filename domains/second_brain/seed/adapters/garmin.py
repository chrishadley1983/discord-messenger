"""Garmin activities adapter.

Imports all activities from Garmin Connect using the garth library.
"""

import os
from datetime import datetime, timedelta, date
from typing import Any
from pathlib import Path

import garth

from config import GARMIN_EMAIL, GARMIN_PASSWORD
from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter


# Session storage directory (shared with nutrition service)
SESSION_DIR = Path(os.getenv("LOCALAPPDATA", ".")) / "discord-assistant" / "garmin_session"


def _get_garmin_client():
    """Get authenticated Garmin client."""
    if not GARMIN_EMAIL or not GARMIN_PASSWORD:
        raise ValueError("Garmin credentials not configured (GARMIN_EMAIL, GARMIN_PASSWORD)")

    # Try to load existing session
    if SESSION_DIR.exists():
        try:
            garth.resume(str(SESSION_DIR))
            return garth.client
        except Exception as e:
            logger.warning(f"Failed to load Garmin session: {e}")

    # Fresh login required
    logger.info("Authenticating with Garmin Connect...")
    garth.login(GARMIN_EMAIL, GARMIN_PASSWORD)

    # Save session for future use
    try:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        garth.save(str(SESSION_DIR))
    except Exception as e:
        logger.warning(f"Failed to save Garmin session: {e}")

    return garth.client


@register_adapter
class GarminActivitiesAdapter(SeedAdapter):
    """Import all Garmin activities."""

    name = "garmin-activities"
    description = "Import all activities from Garmin Connect"
    source_system = "seed:garmin"

    # Activity types to import
    ACTIVITY_TYPES = [
        "running",
        "trail_running",
        "treadmill_running",
        "cycling",
        "swimming",
        "hiking",
        "walking",
        "strength_training",
        "cardio",
        "yoga",
        "other",
    ]

    def __init__(self, config: dict = None):
        super().__init__(config)
        # Default to 5 years of history
        self.years_back = config.get("years_back", 5) if config else 5
        # Minimum distance filter (0 = all activities)
        self.min_distance_km = config.get("min_distance_km", 0) if config else 0

    async def validate(self) -> tuple[bool, str]:
        try:
            _get_garmin_client()
            return True, ""
        except ValueError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Garmin auth failed: {e}"

    async def fetch(self, limit: int = 2000) -> list[SeedItem]:
        """Fetch all activities from the last N years."""
        items = []

        try:
            _get_garmin_client()

            # Calculate date range
            end_date = date.today()
            start_date = end_date - timedelta(days=365 * self.years_back)

            logger.info(f"Fetching Garmin activities from {start_date} to {end_date}...")

            # Use garth.Activity.list() - it supports pagination via limit/start
            all_activities = []
            batch_start = 0
            batch_size = 100

            while len(all_activities) < limit:
                activities = garth.Activity.list(limit=batch_size, start=batch_start)

                if not activities:
                    break

                for activity in activities:
                    # Check date range
                    activity_date = activity.start_time_local.date() if activity.start_time_local else None
                    if activity_date and activity_date < start_date:
                        # We've gone past our date range
                        logger.info(f"Reached activities older than {start_date}, stopping.")
                        break

                    all_activities.append(activity)

                # Check if last activity is before our date range
                if activities:
                    last_date = activities[-1].start_time_local.date() if activities[-1].start_time_local else None
                    if last_date and last_date < start_date:
                        break

                batch_start += batch_size

                if len(activities) < batch_size:
                    break

                logger.info(f"Fetched {len(all_activities)} activities so far...")

            logger.info(f"Found {len(all_activities)} total activities in date range")

            # Convert to SeedItems
            for activity in all_activities:
                # Apply distance filter if set
                if self.min_distance_km > 0:
                    distance_km = (activity.distance or 0) / 1000
                    if distance_km < self.min_distance_km:
                        continue

                item = self._activity_to_item_from_garth(activity)
                if item:
                    items.append(item)

                if len(items) >= limit:
                    break

            logger.info(f"Returning {len(items)} activities for import")

        except Exception as e:
            logger.error(f"Failed to fetch Garmin activities: {e}")
            import traceback
            traceback.print_exc()

        return items

    def _activity_to_item_from_garth(self, activity) -> SeedItem | None:
        """Convert garth Activity object to SeedItem."""
        try:
            name = activity.activity_name or "Activity"
            activity_type = activity.activity_type.type_key if activity.activity_type else "unknown"
            start_time = activity.start_time_local

            # Parse metrics
            distance_km = (activity.distance or 0) / 1000
            duration_sec = activity.duration or 0
            duration_min = duration_sec / 60
            avg_hr = activity.average_hr
            calories = activity.calories

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
                f"**Date:** {start_time.strftime('%Y-%m-%d %H:%M') if start_time else 'Unknown'}",
                f"**Distance:** {distance_km:.2f} km",
                f"**Duration:** {int(duration_min)} minutes",
            ]

            if pace_str:
                content_parts.append(f"**Pace:** {pace_str}")
            if avg_hr:
                content_parts.append(f"**Avg HR:** {int(avg_hr)} bpm")
            if calories:
                content_parts.append(f"**Calories:** {int(calories)}")
            if activity.elevation_gain:
                content_parts.append(f"**Elevation:** +{int(activity.elevation_gain)}m")

            activity_id = activity.activity_id if hasattr(activity, 'activity_id') else None

            return SeedItem(
                title=name,
                content="\n".join(content_parts),
                source_url=f"https://connect.garmin.com/modern/activity/{activity_id}" if activity_id else None,
                source_id=str(activity_id) if activity_id else None,
                topics=self._extract_topics_from_garth(activity),
                created_at=start_time,
                metadata={
                    "distance_km": distance_km,
                    "duration_min": duration_min,
                    "activity_type": activity_type,
                    "avg_hr": avg_hr,
                    "calories": calories,
                },
            )

        except Exception as e:
            logger.warning(f"Failed to parse activity: {e}")
            return None

    def _extract_topics_from_garth(self, activity) -> list[str]:
        """Extract topics from garth Activity object."""
        topics = ["garmin", "fitness"]

        activity_type = activity.activity_type.type_key if activity.activity_type else ""

        if "running" in activity_type or "run" in activity_type:
            topics.extend(["running", "training"])
            # Check for race-like activities
            name = (activity.activity_name or "").lower()
            distance_km = (activity.distance or 0) / 1000
            if any(w in name for w in ["race", "parkrun", "marathon", "half", "ultra"]):
                topics.append("race")
            elif distance_km >= 21:
                topics.append("long-run")
            elif "ultra" in activity_type:
                topics.append("ultra")

        elif "cycling" in activity_type:
            topics.append("cycling")

        elif "swimming" in activity_type:
            topics.append("swimming")

        elif "hiking" in activity_type or "walking" in activity_type:
            topics.append("hiking")

        elif "strength" in activity_type:
            topics.append("strength")

        return list(set(topics))

    def get_default_topics(self) -> list[str]:
        return ["garmin", "fitness", "training"]
