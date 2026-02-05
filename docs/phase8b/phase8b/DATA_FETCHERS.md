# Phase 8b Data Fetchers

Add these to `domains/peterbot/data_fetchers.py`:

```python
# ============================================================
# PHASE 8b: Smart Home Data Fetchers
# ============================================================

import os
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from config import (
    WEATHER_LAT, WEATHER_LON, WEATHER_LOCATION_NAME,
    OHME_EMAIL, OHME_PASSWORD,
    RING_EMAIL, RING_PASSWORD, RING_2FA_TOKEN,
    HOME_ASSISTANT_URL, HOME_ASSISTANT_TOKEN,
    GOOGLE_MAPS_API_KEY, HOME_ADDRESS, SAVED_ROUTES
)


# === WEATHER (Open-Meteo) ===

WEATHER_CODES = {
    0: ("Clear sky", "☀️"),
    1: ("Mainly clear", "🌤️"),
    2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁️"),
    45: ("Foggy", "🌫️"),
    48: ("Depositing rime fog", "🌫️"),
    51: ("Light drizzle", "🌦️"),
    53: ("Moderate drizzle", "🌦️"),
    55: ("Dense drizzle", "🌧️"),
    61: ("Slight rain", "🌧️"),
    63: ("Moderate rain", "🌧️"),
    65: ("Heavy rain", "🌧️"),
    71: ("Slight snow", "❄️"),
    73: ("Moderate snow", "❄️"),
    75: ("Heavy snow", "❄️"),
    77: ("Snow grains", "❄️"),
    80: ("Slight showers", "🌦️"),
    81: ("Moderate showers", "🌧️"),
    82: ("Violent showers", "🌧️"),
    85: ("Slight snow showers", "🌨️"),
    86: ("Heavy snow showers", "🌨️"),
    95: ("Thunderstorm", "⛈️"),
    96: ("Thunderstorm with hail", "⛈️"),
    99: ("Thunderstorm with heavy hail", "⛈️"),
}


def get_weather_data(lat: float = None, lon: float = None, location: str = None) -> Dict[str, Any]:
    """Fetch current weather from Open-Meteo."""
    lat = lat or WEATHER_LAT
    lon = lon or WEATHER_LON
    location = location or WEATHER_LOCATION_NAME
    
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m,wind_direction_10m",
        "timezone": "Europe/London"
    }
    
    response = requests.get("https://api.open-meteo.com/v1/forecast", params=params)
    
    if response.status_code != 200:
        return {"error": f"Weather API error: {response.status_code}"}
    
    data = response.json()
    current = data.get("current", {})
    
    weather_code = current.get("weather_code", 0)
    condition, icon = WEATHER_CODES.get(weather_code, ("Unknown", "❓"))
    
    return {
        "location": location,
        "temperature": current.get("temperature_2m"),
        "feels_like": current.get("apparent_temperature"),
        "humidity": current.get("relative_humidity_2m"),
        "precipitation": current.get("precipitation"),
        "wind_speed": current.get("wind_speed_10m"),
        "wind_direction": current.get("wind_direction_10m"),
        "weather_code": weather_code,
        "condition": condition,
        "icon": icon,
        "fetched_at": datetime.now().isoformat()
    }


def get_weather_forecast_data(lat: float = None, lon: float = None, days: int = 7) -> Dict[str, Any]:
    """Fetch multi-day forecast from Open-Meteo."""
    lat = lat or WEATHER_LAT
    lon = lon or WEATHER_LON
    
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset",
        "timezone": "Europe/London",
        "forecast_days": days
    }
    
    response = requests.get("https://api.open-meteo.com/v1/forecast", params=params)
    
    if response.status_code != 200:
        return {"error": f"Weather API error: {response.status_code}"}
    
    data = response.json()
    daily = data.get("daily", {})
    
    forecast = []
    for i in range(len(daily.get("time", []))):
        weather_code = daily["weather_code"][i]
        condition, icon = WEATHER_CODES.get(weather_code, ("Unknown", "❓"))
        
        forecast.append({
            "date": daily["time"][i],
            "temp_max": daily["temperature_2m_max"][i],
            "temp_min": daily["temperature_2m_min"][i],
            "precipitation_prob": daily["precipitation_probability_max"][i],
            "weather_code": weather_code,
            "condition": condition,
            "icon": icon,
            "sunrise": daily["sunrise"][i],
            "sunset": daily["sunset"][i]
        })
    
    return {
        "location": WEATHER_LOCATION_NAME,
        "forecast": forecast,
        "fetched_at": datetime.now().isoformat()
    }


# === OHME EV CHARGER ===

_ohme_token = None

def _get_ohme_token() -> Optional[str]:
    """Get Ohme auth token."""
    global _ohme_token
    if _ohme_token:
        return _ohme_token
    
    if not OHME_EMAIL or not OHME_PASSWORD:
        return None
    
    # Ohme auth endpoint (may need adjustment based on actual API)
    response = requests.post(
        "https://api.ohme.io/v1/auth/login",
        json={"email": OHME_EMAIL, "password": OHME_PASSWORD}
    )
    
    if response.status_code == 200:
        _ohme_token = response.json().get("token")
        return _ohme_token
    return None


def get_ev_charging_data() -> Dict[str, Any]:
    """Fetch EV charging status from Ohme."""
    token = _get_ohme_token()
    if not token:
        return {"error": "Ohme auth not configured"}
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get charger status
    response = requests.get("https://api.ohme.io/v1/charger/status", headers=headers)
    
    if response.status_code != 200:
        return {"error": f"Ohme API error: {response.status_code}"}
    
    data = response.json()
    
    return {
        "status": data.get("status"),  # charging, idle, scheduled, disconnected
        "battery_level": data.get("batteryLevel"),
        "target_level": data.get("targetLevel", 80),
        "charge_rate_kw": data.get("chargeRateKw"),
        "time_to_target": data.get("timeToTarget"),
        "energy_added_kwh": data.get("energyAddedKwh"),
        "estimated_cost": data.get("estimatedCost"),
        "scheduled_start": data.get("scheduledStart"),
        "fetched_at": datetime.now().isoformat()
    }


# === RING ===

def get_ring_status_data() -> Dict[str, Any]:
    """Fetch Ring doorbell status and recent events."""
    # Ring requires complex auth with 2FA
    # Using ring_doorbell Python library is recommended
    
    if not RING_EMAIL or not RING_PASSWORD:
        return {"error": "Ring auth not configured"}
    
    try:
        from ring_doorbell import Ring, Auth
        
        auth = Auth("PeterBot/1.0", None, None)
        auth.fetch_token(RING_EMAIL, RING_PASSWORD)
        
        ring = Ring(auth)
        ring.update_data()
        
        devices = ring.devices()
        doorbells = devices.get("doorbells", [])
        
        if not doorbells:
            return {"error": "No Ring doorbells found"}
        
        doorbell = doorbells[0]
        
        # Get recent events
        events = []
        for event in doorbell.history(limit=10):
            events.append({
                "type": event.get("kind"),  # ding, motion
                "time": event.get("created_at"),
                "answered": event.get("answered", False)
            })
        
        return {
            "device_name": doorbell.name,
            "status": "online" if doorbell.is_connected else "offline",
            "battery": doorbell.battery_life,
            "events": events,
            "fetched_at": datetime.now().isoformat()
        }
    
    except ImportError:
        return {"error": "ring_doorbell library not installed"}
    except Exception as e:
        return {"error": f"Ring error: {str(e)}"}


# === HOME ASSISTANT (Smart Home) ===

def get_smart_home_status() -> Dict[str, Any]:
    """Fetch smart home status from Home Assistant."""
    if not HOME_ASSISTANT_URL or not HOME_ASSISTANT_TOKEN:
        return {"error": "Home Assistant not configured"}
    
    headers = {
        "Authorization": f"Bearer {HOME_ASSISTANT_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Get all states
    response = requests.get(
        f"{HOME_ASSISTANT_URL}/api/states",
        headers=headers
    )
    
    if response.status_code != 200:
        return {"error": f"Home Assistant error: {response.status_code}"}
    
    states = response.json()
    
    # Filter to relevant devices
    lights = []
    climate = []
    media = []
    
    for entity in states:
        entity_id = entity.get("entity_id", "")
        state = entity.get("state")
        attrs = entity.get("attributes", {})
        
        if entity_id.startswith("light."):
            lights.append({
                "name": attrs.get("friendly_name", entity_id),
                "state": state,
                "brightness": attrs.get("brightness")
            })
        elif entity_id.startswith("climate."):
            climate.append({
                "name": attrs.get("friendly_name", entity_id),
                "state": state,
                "current_temp": attrs.get("current_temperature"),
                "target_temp": attrs.get("temperature")
            })
        elif entity_id.startswith("media_player."):
            media.append({
                "name": attrs.get("friendly_name", entity_id),
                "state": state
            })
    
    return {
        "lights": lights,
        "climate": climate,
        "media": media,
        "fetched_at": datetime.now().isoformat()
    }


# === GOOGLE MAPS TRAFFIC ===

def get_traffic_data(route_name: str = "school") -> Dict[str, Any]:
    """Fetch traffic data for a saved route."""
    if not GOOGLE_MAPS_API_KEY:
        return {"error": "Google Maps API not configured"}
    
    route = SAVED_ROUTES.get(route_name)
    if not route:
        return {"error": f"Unknown route: {route_name}"}
    
    # Use Routes API
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": "routes.duration,routes.staticDuration,routes.distanceMeters,routes.legs.steps.navigationInstruction"
    }
    
    body = {
        "origin": {"address": route["origin"]},
        "destination": {"address": route["destination"]},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
        "departureTime": datetime.utcnow().isoformat() + "Z"
    }
    
    response = requests.post(
        "https://routes.googleapis.com/directions/v2:computeRoutes",
        headers=headers,
        json=body
    )
    
    if response.status_code != 200:
        return {"error": f"Routes API error: {response.status_code}"}
    
    data = response.json()
    
    if not data.get("routes"):
        return {"error": "No route found"}
    
    route_data = data["routes"][0]
    
    # Parse durations (format: "1234s")
    duration_str = route_data.get("duration", "0s")
    duration_mins = int(duration_str.rstrip("s")) // 60
    
    static_duration_str = route_data.get("staticDuration", "0s")
    static_duration_mins = int(static_duration_str.rstrip("s")) // 60
    
    delay = duration_mins - static_duration_mins
    
    # Determine traffic level
    if delay <= 0:
        traffic_level = "light"
        traffic_icon = "🟢"
    elif delay <= 5:
        traffic_level = "moderate"
        traffic_icon = "🟡"
    elif delay <= 15:
        traffic_level = "heavy"
        traffic_icon = "🔴"
    else:
        traffic_level = "severe"
        traffic_icon = "⚠️"
    
    return {
        "route_name": route_name,
        "origin": route["origin"],
        "destination": route["destination"],
        "duration_mins": duration_mins,
        "typical_mins": route.get("typical_time", static_duration_mins),
        "delay_mins": delay,
        "distance_km": route_data.get("distanceMeters", 0) / 1000,
        "traffic_level": traffic_level,
        "traffic_icon": traffic_icon,
        "fetched_at": datetime.now().isoformat()
    }


def get_directions_data(destination: str, origin: str = None, mode: str = "DRIVE") -> Dict[str, Any]:
    """Get directions to a destination."""
    if not GOOGLE_MAPS_API_KEY:
        return {"error": "Google Maps API not configured"}
    
    origin = origin or HOME_ADDRESS
    
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": "routes.duration,routes.staticDuration,routes.distanceMeters,routes.polyline,routes.legs"
    }
    
    body = {
        "origin": {"address": origin},
        "destination": {"address": destination},
        "travelMode": mode,  # DRIVE, WALK, BICYCLE, TRANSIT
        "routingPreference": "TRAFFIC_AWARE" if mode == "DRIVE" else None,
        "departureTime": datetime.utcnow().isoformat() + "Z"
    }
    
    response = requests.post(
        "https://routes.googleapis.com/directions/v2:computeRoutes",
        headers=headers,
        json=body
    )
    
    if response.status_code != 200:
        return {"error": f"Routes API error: {response.status_code}"}
    
    data = response.json()
    
    if not data.get("routes"):
        return {"error": f"No route found to {destination}"}
    
    route = data["routes"][0]
    
    duration_str = route.get("duration", "0s")
    duration_mins = int(duration_str.rstrip("s")) // 60
    
    return {
        "origin": origin,
        "destination": destination,
        "mode": mode,
        "duration_mins": duration_mins,
        "distance_km": route.get("distanceMeters", 0) / 1000,
        "fetched_at": datetime.now().isoformat()
    }


# === REGISTER IN SKILL_DATA_FETCHERS ===

# Add to existing SKILL_DATA_FETCHERS dict:
#
# SKILL_DATA_FETCHERS = {
#     ... existing entries ...
#     
#     # Phase 8b
#     "weather": get_weather_data,
#     "weather-forecast": get_weather_forecast_data,
#     "ev-charging": get_ev_charging_data,
#     "ring-status": get_ring_status_data,
#     "smart-home": get_smart_home_status,
#     "traffic-check": get_traffic_data,
# }
```

## Dependencies

Add to requirements.txt:
```
ring_doorbell>=0.8.0  # For Ring integration
```

Note: Most integrations use `requests` which should already be installed.
