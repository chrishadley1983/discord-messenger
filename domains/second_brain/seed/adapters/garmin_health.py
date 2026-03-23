"""Garmin daily health dashboard adapter.

Imports daily health summaries (sleep, steps, stress, HR, HRV, body battery)
from Garmin Connect using the garth library. Separate from garmin.py which
handles individual activities.
"""

import asyncio
from datetime import date, timedelta
from typing import Any

import garth

from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter
from .garmin import _get_garmin_client


@register_adapter
class GarminHealthAdapter(SeedAdapter):
    """Imports daily health summaries from Garmin Connect."""

    name = "garmin-health"
    description = "Daily health dashboard (sleep, steps, stress, HR, HRV)"
    source_system = "seed:garmin-health"

    def get_default_topics(self) -> list[str]:
        return ["garmin", "health"]

    async def validate(self) -> tuple[bool, str]:
        try:
            _get_garmin_client()
            return True, ""
        except Exception as e:
            return False, str(e)

    async def fetch(self, limit: int = 7) -> list[SeedItem]:
        items = []
        try:
            client = _get_garmin_client()

            # Fetch last N days of health data
            end_date = date.today()
            start_date = end_date - timedelta(days=limit)

            for day_offset in range(limit):
                current_date = end_date - timedelta(days=day_offset)
                try:
                    item = await asyncio.to_thread(
                        self._build_day_summary, current_date
                    )
                    if item:
                        items.append(item)
                except Exception as e:
                    logger.warning(f"Failed to build health summary for {current_date}: {e}")

        except Exception as e:
            logger.error(f"Garmin health fetch failed: {e}")

        return items

    def _build_day_summary(self, day: date) -> SeedItem | None:
        """Build a health summary SeedItem for a single day."""
        date_str = day.isoformat()
        content_parts = [f"# Health Summary: {date_str}", ""]
        has_data = False

        # Sleep data
        try:
            sleep = garth.DailySleep.get(day)
            if sleep and hasattr(sleep, 'sleep_score'):
                has_data = True
                content_parts.append("## Sleep")
                if sleep.sleep_score:
                    content_parts.append(f"- Sleep score: {sleep.sleep_score}")
                if hasattr(sleep, 'duration_in_seconds') and sleep.duration_in_seconds:
                    hours = sleep.duration_in_seconds / 3600
                    content_parts.append(f"- Duration: {hours:.1f} hours")
                if hasattr(sleep, 'deep_sleep_seconds') and sleep.deep_sleep_seconds:
                    content_parts.append(f"- Deep sleep: {sleep.deep_sleep_seconds / 60:.0f} min")
                if hasattr(sleep, 'light_sleep_seconds') and sleep.light_sleep_seconds:
                    content_parts.append(f"- Light sleep: {sleep.light_sleep_seconds / 60:.0f} min")
                if hasattr(sleep, 'rem_sleep_seconds') and sleep.rem_sleep_seconds:
                    content_parts.append(f"- REM sleep: {sleep.rem_sleep_seconds / 60:.0f} min")
                if hasattr(sleep, 'awake_seconds') and sleep.awake_seconds:
                    content_parts.append(f"- Awake: {sleep.awake_seconds / 60:.0f} min")
                content_parts.append("")
        except Exception as e:
            logger.debug(f"No sleep data for {date_str}: {e}")

        # Daily summary (steps, calories, etc.)
        try:
            summary = garth.DailySteps.get(day)
            if summary and hasattr(summary, 'total_steps') and summary.total_steps:
                has_data = True
                content_parts.append("## Activity")
                content_parts.append(f"- Steps: {summary.total_steps:,}")
                if hasattr(summary, 'total_distance_meters') and summary.total_distance_meters:
                    km = summary.total_distance_meters / 1000
                    content_parts.append(f"- Distance: {km:.1f} km")
                content_parts.append("")
        except Exception as e:
            logger.debug(f"No steps data for {date_str}: {e}")

        # Stress data
        try:
            stress = garth.DailyStress.get(day)
            if stress and hasattr(stress, 'overall_stress_level') and stress.overall_stress_level:
                has_data = True
                content_parts.append("## Stress")
                content_parts.append(f"- Overall stress: {stress.overall_stress_level}")
                if hasattr(stress, 'rest_stress_duration') and stress.rest_stress_duration:
                    content_parts.append(f"- Rest duration: {stress.rest_stress_duration / 60:.0f} min")
                if hasattr(stress, 'high_stress_duration') and stress.high_stress_duration:
                    content_parts.append(f"- High stress: {stress.high_stress_duration / 60:.0f} min")
                content_parts.append("")
        except Exception as e:
            logger.debug(f"No stress data for {date_str}: {e}")

        # Heart rate
        try:
            hr = garth.DailyHeartRate.get(day)
            if hr and hasattr(hr, 'resting_heart_rate') and hr.resting_heart_rate:
                has_data = True
                content_parts.append("## Heart Rate")
                content_parts.append(f"- Resting HR: {hr.resting_heart_rate} bpm")
                if hasattr(hr, 'max_heart_rate') and hr.max_heart_rate:
                    content_parts.append(f"- Max HR: {hr.max_heart_rate} bpm")
                content_parts.append("")
        except Exception as e:
            logger.debug(f"No HR data for {date_str}: {e}")

        # HRV
        try:
            hrv = garth.DailyHRV.get(day)
            if hrv and hasattr(hrv, 'weekly_avg') and hrv.weekly_avg:
                has_data = True
                content_parts.append("## HRV")
                content_parts.append(f"- Weekly avg: {hrv.weekly_avg} ms")
                if hasattr(hrv, 'last_night') and hrv.last_night:
                    content_parts.append(f"- Last night: {hrv.last_night} ms")
                if hasattr(hrv, 'status') and hrv.status:
                    content_parts.append(f"- Status: {hrv.status}")
                content_parts.append("")
        except Exception as e:
            logger.debug(f"No HRV data for {date_str}: {e}")

        if not has_data:
            return None

        content = "\n".join(content_parts)

        topics = ["garmin", "health"]
        # Add specific topics based on content
        if "Sleep" in content:
            topics.append("sleep")
        if "Steps" in content or "Activity" in content:
            topics.append("fitness")

        return SeedItem(
            title=f"Health Summary: {date_str}",
            content=content,
            source_url=f"garmin-daily://{date_str}",
            source_id=f"garmin-daily-{date_str}",
            topics=topics,
            created_at=None,  # Use current time
            metadata={"date": date_str},
            content_type="health_activity",
        )
