"""Withings adapter for Second Brain.

Imports weight, body composition, and blood pressure measurements
from the Withings Health API. Reuses token management from
domains.nutrition.services.withings.
"""

from datetime import datetime, timedelta, timezone

import httpx

from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter


# Withings measure types
MEASURE_TYPES = {
    1: ("Weight", "kg"),
    6: ("Fat Ratio", "%"),
    76: ("Muscle Mass", "kg"),
    77: ("Hydration", "kg"),
    88: ("Bone Mass", "kg"),
    9: ("Diastolic BP", "mmHg"),
    10: ("Systolic BP", "mmHg"),
    11: ("Heart Pulse", "bpm"),
}


@register_adapter
class WithingsAdapter(SeedAdapter):
    """Import weight, body comp, and blood pressure from Withings."""

    name = "withings-health"
    description = "Weight, body composition, and blood pressure from Withings"
    source_system = "seed:withings"

    def get_default_topics(self) -> list[str]:
        return ["withings", "health"]

    async def validate(self) -> tuple[bool, str]:
        try:
            from domains.nutrition.services.withings import _tokens
            if not _tokens.get("access"):
                return False, "Withings access token not available"
            return True, ""
        except ImportError:
            return False, "Withings service module not found"

    async def fetch(self, limit: int = 30) -> list[SeedItem]:
        items = []
        try:
            from domains.nutrition.services.withings import _tokens, _refresh_token

            # Get measurements from the configured lookback period
            days_back = self.config.get("days_back", 30)
            start_date = int((datetime.now() - timedelta(days=days_back)).timestamp())
            end_date = int(datetime.now().timestamp())

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    "https://wbsapi.withings.net/measure",
                    data={
                        "action": "getmeas",
                        "category": 1,  # Real measurements only
                        "startdate": start_date,
                        "enddate": end_date,
                    },
                    headers={"Authorization": f"Bearer {_tokens['access']}"},
                )

                data = response.json()

                # Handle token expiry
                if data.get("status") != 0:
                    logger.warning(f"Withings API status {data.get('status')}, refreshing token...")
                    if await _refresh_token():
                        response = await client.post(
                            "https://wbsapi.withings.net/measure",
                            data={
                                "action": "getmeas",
                                "category": 1,
                                "startdate": start_date,
                                "enddate": end_date,
                            },
                            headers={"Authorization": f"Bearer {_tokens['access']}"},
                        )
                        data = response.json()
                    else:
                        logger.error("Withings token refresh failed")
                        return items

                if data.get("status") != 0:
                    logger.error(f"Withings API error: status {data.get('status')}")
                    return items

                # Group measurements by date
                measure_groups = data.get("body", {}).get("measuregrps", [])
                daily_measures: dict[str, dict] = {}

                for grp in measure_groups:
                    grp_id = grp.get("grpid")
                    timestamp = grp.get("date", 0)
                    date_str = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")

                    if date_str not in daily_measures:
                        daily_measures[date_str] = {
                            "timestamp": timestamp,
                            "grpid": grp_id,
                            "values": {},
                        }

                    for m in grp.get("measures", []):
                        mtype = m.get("type")
                        value = m.get("value", 0) * (10 ** m.get("unit", 0))
                        if mtype in MEASURE_TYPES:
                            name, unit = MEASURE_TYPES[mtype]
                            daily_measures[date_str]["values"][name] = (round(value, 1), unit)

                # Build SeedItems per day
                for date_str in sorted(daily_measures.keys(), reverse=True)[:limit]:
                    day_data = daily_measures[date_str]
                    values = day_data["values"]

                    if not values:
                        continue

                    content_parts = [f"# Body Measurements: {date_str}", ""]

                    # Weight & body comp
                    body_comp = {k: v for k, v in values.items()
                                 if k not in ("Systolic BP", "Diastolic BP", "Heart Pulse")}
                    if body_comp:
                        content_parts.append("## Body Composition")
                        for name, (val, unit) in body_comp.items():
                            content_parts.append(f"- {name}: {val} {unit}")
                        content_parts.append("")

                    # Blood pressure
                    bp_values = {k: v for k, v in values.items()
                                 if k in ("Systolic BP", "Diastolic BP", "Heart Pulse")}
                    if bp_values:
                        content_parts.append("## Blood Pressure")
                        for name, (val, unit) in bp_values.items():
                            content_parts.append(f"- {name}: {val} {unit}")
                        content_parts.append("")

                    content = "\n".join(content_parts)

                    topics = ["withings", "health"]
                    if body_comp:
                        topics.append("weight")
                    if bp_values:
                        topics.append("blood-pressure")

                    items.append(SeedItem(
                        title=f"Body Measurements: {date_str}",
                        content=content,
                        source_url=f"withings-measure://{day_data['grpid']}",
                        source_id=f"withings-{date_str}",
                        topics=topics,
                        created_at=datetime.fromtimestamp(day_data["timestamp"]),
                        content_type="health_activity",
                    ))

        except Exception as e:
            logger.error(f"Withings fetch failed: {e}")

        logger.info(f"Fetched {len(items)} Withings measurements")
        return items
