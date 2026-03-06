"""Google Maps Location Sharing integration.

Uses locationsharinglib to get real-time location of family members
who share their location via Google Maps, then calculates distance/ETA
to home using Google Maps Distance Matrix API.

Setup:
  1. Ensure Abby shares location with Chris's Google account in Google Maps
  2. Export cookies from Chrome after logging into google.com/maps
     (use "Get cookies.txt LOCALLY" Chrome extension)
  3. Save as data/google_maps_cookies.txt
"""

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from config import GOOGLE_MAPS_API_KEY

logger = logging.getLogger(__name__)

# Paths
COOKIES_FILE = Path(__file__).parent.parent / "data" / "google_maps_cookies.txt"
GOOGLE_EMAIL = "chrishadley1983@gmail.com"

# Home coordinates (47 Correnden Road, Tonbridge, TN10 3AU)
HOME_LAT = 51.2034
HOME_LNG = 0.2643
HOME_ADDRESS = "47 Correnden Road, Tonbridge, TN10 3AU"

# Known family members — maps name variants to Google account names
FAMILY = {
    "chris": "Chris Hadley",
    "abby": "Abby Hadley",
}

# Cache: avoid hammering Google on repeated requests
_cache: dict[str, tuple[float, dict]] = {}  # name -> (timestamp, data)
_CACHE_TTL = 60  # seconds


@dataclass
class LocationResult:
    """Result of a location lookup."""
    name: str
    latitude: float
    longitude: float
    address: Optional[str]
    battery_level: Optional[int]
    charging: Optional[bool]
    location_age_seconds: Optional[float]
    distance_km: Optional[float]
    distance_miles: Optional[float]
    duration_text: Optional[str]
    duration_seconds: Optional[int]
    error: Optional[str] = None


def _get_person_location(name_key: str) -> Optional[dict]:
    """Get a person's location from Google Maps location sharing.

    Returns dict with lat, lng, address, battery_level, charging, timestamp
    or None if not found.
    """
    # Check cache
    now = time.monotonic()
    if name_key in _cache:
        cached_time, cached_data = _cache[name_key]
        if now - cached_time < _CACHE_TTL:
            logger.debug(f"Location cache hit for {name_key}")
            return cached_data

    if not COOKIES_FILE.exists():
        logger.error(f"Cookies file not found: {COOKIES_FILE}")
        return None

    full_name = FAMILY.get(name_key.lower())
    if not full_name:
        logger.error(f"Unknown person: {name_key}")
        return None

    try:
        from locationsharinglib import Service

        service = Service(
            cookies_file=str(COOKIES_FILE),
            authenticating_account=GOOGLE_EMAIL,
        )

        person = service.get_person_by_full_name(full_name)
        if not person:
            logger.warning(f"Person not found in location sharing: {full_name}")
            return None

        data = {
            "name": person.full_name,
            "latitude": person.latitude,
            "longitude": person.longitude,
            "address": person.address,
            "battery_level": person.battery_level,
            "charging": person.charging,
            "timestamp": person.datetime,
        }

        # Update cache
        _cache[name_key] = (now, data)
        return data

    except Exception as e:
        logger.error(f"Location sharing error for {name_key}: {e}")
        return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate straight-line distance between two points in km."""
    import math
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def _get_distance_to_home(lat: float, lng: float, address: Optional[str] = None) -> Optional[dict]:
    """Calculate driving distance and ETA to home.

    Uses Google Maps Directions API with the person's address as origin
    for accurate route-based distance/time. Falls back to haversine if
    the API call fails.
    """
    # Try Directions API first (uses address for accurate routing)
    if GOOGLE_MAPS_API_KEY:
        origin = address if address else f"{lat},{lng}"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://maps.googleapis.com/maps/api/directions/json",
                    params={
                        "origin": origin,
                        "destination": HOME_ADDRESS,
                        "mode": "driving",
                        "key": GOOGLE_MAPS_API_KEY,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            if data.get("status") == "OK":
                leg = data["routes"][0]["legs"][0]
                distance_m = leg["distance"]["value"]
                duration_s = leg["duration"]["value"]
                return {
                    "distance_km": round(distance_m / 1000, 1),
                    "distance_miles": round(distance_m / 1609.34, 1),
                    "duration_text": leg["duration"]["text"],
                    "duration_seconds": duration_s,
                }
            else:
                logger.warning(f"Directions API status: {data.get('status')} — falling back to haversine")
        except Exception as e:
            logger.warning(f"Directions API error: {e} — falling back to haversine")

    # Fallback: haversine straight-line distance with estimated drive time
    km = _haversine_km(lat, lng, HOME_LAT, HOME_LNG)
    miles = km / 1.60934
    # Estimate ~30 mph average for UK driving
    est_minutes = int((miles / 30) * 60)
    return {
        "distance_km": round(km, 1),
        "distance_miles": round(miles, 1),
        "duration_text": f"~{est_minutes} mins (est.)",
        "duration_seconds": est_minutes * 60,
    }


async def get_location(name_key: str) -> LocationResult:
    """Get a person's location and distance from home.

    Args:
        name_key: "chris" or "abby"

    Returns:
        LocationResult with all available data
    """
    # Get location from Google Maps sharing
    location = _get_person_location(name_key)
    if not location:
        return LocationResult(
            name=FAMILY.get(name_key.lower(), name_key),
            latitude=0, longitude=0,
            address=None, battery_level=None, charging=None,
            location_age_seconds=None,
            distance_km=None, distance_miles=None,
            duration_text=None, duration_seconds=None,
            error=f"Could not get location for {name_key}. Check cookies file and location sharing.",
        )

    # Calculate location age
    location_age = None
    if location.get("timestamp"):
        try:
            loc_time = location["timestamp"]
            if loc_time.tzinfo is None:
                loc_time = loc_time.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - loc_time
            location_age = age.total_seconds()
        except Exception:
            pass

    # Get distance to home — pass address for accurate Directions API routing
    distance = await _get_distance_to_home(location["latitude"], location["longitude"], location.get("address"))

    return LocationResult(
        name=location["name"],
        latitude=location["latitude"],
        longitude=location["longitude"],
        address=location.get("address"),
        battery_level=location.get("battery_level"),
        charging=location.get("charging"),
        location_age_seconds=location_age,
        distance_km=distance["distance_km"] if distance else None,
        distance_miles=distance["distance_miles"] if distance else None,
        duration_text=distance["duration_text"] if distance else None,
        duration_seconds=distance["duration_seconds"] if distance else None,
    )


def format_location_response(result: LocationResult) -> str:
    """Format a LocationResult into a human-readable string for Peter."""
    if result.error:
        return f"❌ {result.error}"

    lines = [f"📍 **{result.name}**"]

    if result.address:
        lines.append(f"📌 {result.address}")

    if result.distance_miles is not None and result.duration_text is not None:
        lines.append(f"🏠 **{result.distance_miles} miles** from home ({result.duration_text} drive)")
    elif result.distance_km is not None:
        lines.append(f"🏠 {result.distance_km} km from home")

    if result.location_age_seconds is not None:
        age = result.location_age_seconds
        if age < 60:
            age_str = "just now"
        elif age < 3600:
            age_str = f"{int(age // 60)} min ago"
        else:
            age_str = f"{int(age // 3600)}h {int((age % 3600) // 60)}m ago"
        lines.append(f"🕐 Location updated {age_str}")

    if result.battery_level is not None:
        charging = " ⚡" if result.charging else ""
        lines.append(f"🔋 {result.battery_level}%{charging}")

    return "\n".join(lines)
