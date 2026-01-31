"""School Run Traffic Report scheduled job.

Morning Schedule:
- Monday, Tuesday, Wednesday, Friday: 8:10 AM (arrive 8:38)
- Thursday: 7:45 AM (arrive 7:58 - earlier start)

Afternoon Schedule:
- Monday, Tuesday, Thursday, Friday: 2:55 PM
- Wednesday: 4:50 PM

Sends via Discord AND WhatsApp with:
- Traffic data from Google Maps API
- Weather from Open-Meteo API
- Uniform requirements for Max and Emmie (morning only)
- Evening clubs (afternoon only)
"""

from datetime import datetime

import httpx

from config import (
    GOOGLE_MAPS_API_KEY,
    SUPABASE_URL,
    SUPABASE_KEY,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_WHATSAPP_FROM
)
from logger import logger

# Discord channel for school run reports
SCHOOL_RUN_CHANNEL_ID = 1466522078462083325  # #traffic-reports

# WhatsApp recipients (when Twilio is configured)
RECIPIENTS = [
    "+447856182831",  # Abby
    "+447855620978",  # Chris
]

# Route details
ORIGIN = "47 Correnden Road, TN10 3AU"
DESTINATION = "Stocks Green Primary School, Tonbridge"

# Target arrival times by weekday (Monday=0)
# Thursday (3) has earlier start for activities
TARGET_ARRIVALS = {
    0: (8, 38),   # Monday - arrive 8:38
    1: (8, 38),   # Tuesday - arrive 8:38
    2: (8, 38),   # Wednesday - arrive 8:38
    3: (7, 58),   # Thursday - arrive 7:58 (earlier)
    4: (8, 38),   # Friday - arrive 8:38
}

# Target pickup times by weekday (Monday=0)
# Wednesday (2) has later pickup due to afterschool club
TARGET_PICKUPS = {
    0: (15, 10),  # Monday - pickup 3:10 PM
    1: (15, 10),  # Tuesday - pickup 3:10 PM
    2: (17, 0),   # Wednesday - pickup 5:00 PM
    3: (15, 10),  # Thursday - pickup 3:10 PM
    4: (15, 10),  # Friday - pickup 3:10 PM
}

# Tonbridge coordinates for weather
TONBRIDGE_LAT = 51.1833
TONBRIDGE_LON = 0.2833

# Uniform schedules
# Max: PE on Monday, Thursday
# Emmie: PE on Wednesday, Friday; Gymnastics on Thursday
MAX_PE_DAYS = [0, 3]  # Monday=0, Thursday=3 (weekday() where Monday=0)
EMMIE_PE_DAYS = [2, 4]  # Wednesday=2, Friday=4
EMMIE_GYMNASTICS_DAYS = [3]  # Thursday=3

# Day names for display
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


async def _get_clubs(weekday: int, time_category: str) -> list[dict]:
    """Fetch clubs from Supabase for the given weekday and time category.

    Args:
        weekday: Monday=0, Tuesday=1, etc.
        time_category: 'morning' or 'afternoon'
    """
    try:
        if not SUPABASE_URL or not SUPABASE_KEY:
            logger.warning("Supabase not configured - skipping clubs")
            return []

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/evening_clubs",
                params={
                    "weekday": f"eq.{weekday}",
                    "is_active": "eq.true",
                    "time_category": f"eq.{time_category}",
                    "select": "child_name,club_name,pickup_time,pickup_location,notes"
                },
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}"
                },
                timeout=30
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Supabase API returned {response.status_code}: {response.text}")
                return []
    except Exception as e:
        logger.error(f"Error fetching clubs: {e}")
        return []


async def _get_evening_clubs(weekday: int) -> list[dict]:
    """Fetch afternoon/evening clubs for the given weekday."""
    return await _get_clubs(weekday, "afternoon")


async def _get_morning_activities(weekday: int) -> list[dict]:
    """Fetch morning/lunchtime activities for the given weekday."""
    return await _get_clubs(weekday, "morning")


async def _get_traffic_return() -> dict:
    """Get traffic data for return journey (school → home)."""
    try:
        if not GOOGLE_MAPS_API_KEY:
            return {"error": "Google Maps API key not configured"}

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/directions/json",
                params={
                    "origin": DESTINATION,  # School
                    "destination": ORIGIN,  # Home
                    "departure_time": "now",
                    "traffic_model": "best_guess",
                    "key": GOOGLE_MAPS_API_KEY
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                if data["status"] == "OK" and data["routes"]:
                    route = data["routes"][0]
                    leg = route["legs"][0]

                    if "duration_in_traffic" in leg:
                        duration_seconds = leg["duration_in_traffic"]["value"]
                    else:
                        duration_seconds = leg["duration"]["value"]

                    duration_minutes = round(duration_seconds / 60)
                    route_name = route.get("summary", "main route")

                    normal_duration = leg["duration"]["value"]
                    delay_ratio = duration_seconds / normal_duration if normal_duration > 0 else 1

                    if delay_ratio < 1.1:
                        condition = "Clear ✅"
                    elif delay_ratio < 1.3:
                        condition = "Moderate 🟡"
                    else:
                        condition = "Heavy 🔴"

                    return {
                        "duration_in_minutes": duration_minutes,
                        "route_name": route_name,
                        "traffic_condition": condition
                    }
                else:
                    return {"error": f"No route found: {data.get('status')}"}
            else:
                return {"error": f"API returned {response.status_code}"}
    except Exception as e:
        logger.error(f"Google Maps API error (return): {e}")
        return {"error": str(e)}


async def _get_traffic() -> dict:
    """Get traffic data from Google Maps Directions API."""
    try:
        if not GOOGLE_MAPS_API_KEY:
            return {"error": "Google Maps API key not configured"}

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/directions/json",
                params={
                    "origin": ORIGIN,
                    "destination": DESTINATION,
                    "departure_time": "now",
                    "traffic_model": "best_guess",
                    "key": GOOGLE_MAPS_API_KEY
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                if data["status"] == "OK" and data["routes"]:
                    route = data["routes"][0]
                    leg = route["legs"][0]

                    # Get duration in traffic if available
                    if "duration_in_traffic" in leg:
                        duration_seconds = leg["duration_in_traffic"]["value"]
                    else:
                        duration_seconds = leg["duration"]["value"]

                    duration_minutes = round(duration_seconds / 60)

                    # Extract route name
                    route_name = route.get("summary", "main route")

                    # Determine traffic condition based on delay
                    normal_duration = leg["duration"]["value"]
                    delay_ratio = duration_seconds / normal_duration if normal_duration > 0 else 1

                    if delay_ratio < 1.1:
                        condition = "Clear ✅"
                    elif delay_ratio < 1.3:
                        condition = "Moderate 🟡"
                    else:
                        condition = "Heavy 🔴"

                    return {
                        "duration_in_minutes": duration_minutes,
                        "route_name": route_name,
                        "traffic_condition": condition
                    }
                else:
                    return {"error": f"No route found: {data.get('status')}"}
            else:
                return {"error": f"API returned {response.status_code}"}
    except Exception as e:
        logger.error(f"Google Maps API error: {e}")
        return {"error": str(e)}


async def _get_weather() -> dict:
    """Get weather from Open-Meteo API."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": TONBRIDGE_LAT,
                    "longitude": TONBRIDGE_LON,
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode",
                    "timezone": "Europe/London",
                    "forecast_days": 1
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                daily = data.get("daily", {})

                low_temp = daily.get("temperature_2m_min", [None])[0]
                high_temp = daily.get("temperature_2m_max", [None])[0]
                precip_prob = daily.get("precipitation_probability_max", [0])[0]
                weather_code = daily.get("weathercode", [0])[0]

                # Weather code to condition
                conditions = {
                    0: "Clear",
                    1: "Mainly clear",
                    2: "Partly cloudy",
                    3: "Overcast",
                    45: "Foggy",
                    48: "Foggy",
                    51: "Light drizzle",
                    53: "Drizzle",
                    55: "Heavy drizzle",
                    61: "Light rain",
                    63: "Rain",
                    65: "Heavy rain",
                    71: "Light snow",
                    73: "Snow",
                    75: "Heavy snow",
                    80: "Rain showers",
                    81: "Rain showers",
                    82: "Heavy showers",
                    95: "Thunderstorm",
                }
                condition = conditions.get(weather_code, "Unknown")

                return {
                    "low_temp": low_temp,
                    "high_temp": high_temp,
                    "precipitation_probability": precip_prob,
                    "condition": condition
                }
            else:
                return {"error": f"API returned {response.status_code}"}
    except Exception as e:
        logger.error(f"Open-Meteo API error: {e}")
        return {"error": str(e)}


def _get_uniform(weekday: int) -> dict:
    """Get uniform requirements for today.

    Args:
        weekday: Monday=0, Tuesday=1, etc.
    """
    max_uniform = "🏃 PE day – PE kit needed" if weekday in MAX_PE_DAYS else "School uniform ✅"

    if weekday in EMMIE_GYMNASTICS_DAYS:
        emmie_uniform = "🤸 Gymnastics kit needed"
    elif weekday in EMMIE_PE_DAYS:
        emmie_uniform = "🏃 PE day – PE kit needed"
    else:
        emmie_uniform = "School uniform ✅"

    return {
        "max": max_uniform,
        "emmie": emmie_uniform
    }


def _get_target_arrival(weekday: int) -> tuple[int, int]:
    """Get target arrival time for the given weekday."""
    return TARGET_ARRIVALS.get(weekday, (8, 38))


def _get_target_pickup(weekday: int) -> tuple[int, int]:
    """Get target pickup time for the given weekday."""
    return TARGET_PICKUPS.get(weekday, (15, 10))


def _calculate_leave_time(eta_minutes: int, weekday: int) -> tuple[str, str]:
    """Calculate leave time based on weekday's target arrival.

    Returns:
        Tuple of (leave_time, arrival_time) as formatted strings.
    """
    arrival_hour, arrival_minute = _get_target_arrival(weekday)

    # Leave time = arrival time - ETA - 2 minute buffer
    total_minutes = arrival_hour * 60 + arrival_minute - eta_minutes - 2
    leave_hour = total_minutes // 60
    leave_minute = total_minutes % 60

    leave_time = f"{leave_hour}:{leave_minute:02d}"
    arrival_time = f"{arrival_hour}:{arrival_minute:02d}"

    return leave_time, arrival_time


def _calculate_pickup_leave_time(eta_minutes: int, weekday: int) -> tuple[str, str]:
    """Calculate leave time for school pickup based on weekday's target.

    Returns:
        Tuple of (leave_time, pickup_time) as formatted strings.
    """
    pickup_hour, pickup_minute = _get_target_pickup(weekday)

    # Leave time = pickup time - ETA - 2 minute buffer
    total_minutes = pickup_hour * 60 + pickup_minute - eta_minutes - 2
    leave_hour = total_minutes // 60
    leave_minute = total_minutes % 60

    leave_time = f"{leave_hour}:{leave_minute:02d}"
    pickup_time = f"{pickup_hour}:{pickup_minute:02d}"

    return leave_time, pickup_time


def _is_twilio_configured() -> bool:
    """Check if Twilio credentials are configured."""
    return all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM])


async def _send_whatsapp(message: str):
    """Send WhatsApp message via Twilio."""
    try:
        if not _is_twilio_configured():
            logger.warning("Twilio credentials not configured - skipping WhatsApp")
            return False

        from twilio.rest import Client as TwilioClient
        client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

        for recipient in RECIPIENTS:
            try:
                client.messages.create(
                    body=message,
                    from_=f"whatsapp:{TWILIO_WHATSAPP_FROM}",
                    to=f"whatsapp:{recipient}"
                )
                logger.info(f"Sent WhatsApp to {recipient}")
            except Exception as e:
                logger.error(f"Failed to send WhatsApp to {recipient}: {e}")

        return True
    except Exception as e:
        logger.error(f"Twilio error: {e}")
        return False


async def _send_discord(bot, message: str):
    """Send message via Discord."""
    try:
        channel = bot.get_channel(SCHOOL_RUN_CHANNEL_ID)
        if channel:
            # Convert WhatsApp formatting (*bold*) to Discord (**bold**)
            discord_message = message.replace("*", "**")
            await channel.send(discord_message)
            logger.info("Sent school run report to Discord")
            return True
        else:
            logger.error(f"Discord channel {SCHOOL_RUN_CHANNEL_ID} not found")
            return False
    except Exception as e:
        logger.error(f"Discord send error: {e}")
        return False


async def school_run_report(bot):
    """Generate and send the school run report."""
    try:
        now = datetime.now()
        weekday = now.weekday()

        # Skip weekends
        if weekday >= 5:  # Saturday=5, Sunday=6
            logger.info("Skipping school run report - weekend")
            return

        # Get data
        traffic = await _get_traffic()
        weather = await _get_weather()
        uniform = _get_uniform(weekday)

        # Format date
        day_name = now.strftime("%a")
        date_str = now.strftime("%d %b")

        # Build message (WhatsApp format - *bold* not **bold**)
        lines = [
            f"🚗 *SCHOOL RUN* — {day_name} {date_str}",
            "━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            "🚦 *TRAFFIC*",
            f"📍 Correnden Rd → Stocks Green"
        ]

        if traffic.get("error"):
            lines.append(f"⚠️ Traffic data unavailable")
        else:
            eta = traffic["duration_in_minutes"]
            leave_time, arrival_time = _calculate_leave_time(eta, weekday)
            lines.extend([
                f"⏱️ {eta} mins via {traffic['route_name']}",
                f"🚦 {traffic['traffic_condition']}",
                f"➡️ 🎯 Leave by {leave_time} to arrive {arrival_time}"
            ])

        lines.extend(["", "🌤️ *WEATHER*"])

        if weather.get("error"):
            lines.append("⚠️ Weather data unavailable")
        else:
            lines.append(f"🌡️ {weather['low_temp']:.0f}°C → {weather['high_temp']:.0f}°C")
            lines.append(f"🌧️ {weather['precipitation_probability']}% chance of rain")

            # Clothing recommendation
            if weather['precipitation_probability'] > 50:
                lines.append("🧥 Coats needed!")
            elif weather['high_temp'] < 10:
                lines.append("🧥 Warm layers recommended")
            else:
                lines.append("☀️ Light jacket should be fine")

        lines.extend([
            "",
            "👕 *UNIFORM*",
            "",
            "Max 👦",
            uniform["max"],
            "",
            "Emmie 👧",
            uniform["emmie"]
        ])

        # Morning activities section (if any)
        morning_activities = await _get_morning_activities(weekday)
        if morning_activities:
            lines.extend(["", "📅 *TODAY'S ACTIVITIES*"])

            max_activities = [a for a in morning_activities if a["child_name"].lower() == "max"]
            emmie_activities = [a for a in morning_activities if a["child_name"].lower() == "emmie"]

            if max_activities:
                lines.extend(["", "Max 👦"])
                for act in max_activities:
                    act_line = f"📌 {act['club_name']}"
                    if act.get("pickup_time"):
                        act_line += f" @ {act['pickup_time']}"
                    lines.append(act_line)
                    if act.get("notes"):
                        lines.append(f"   📝 {act['notes']}")

            if emmie_activities:
                lines.extend(["", "Emmie 👧"])
                for act in emmie_activities:
                    act_line = f"📌 {act['club_name']}"
                    if act.get("pickup_time"):
                        act_line += f" @ {act['pickup_time']}"
                    lines.append(act_line)
                    if act.get("notes"):
                        lines.append(f"   📝 {act['notes']}")

        message = "\n".join(lines)

        # Send to both WhatsApp AND Discord
        if _is_twilio_configured():
            await _send_whatsapp(message)

        # Always send to Discord as well
        await _send_discord(bot, message)

        logger.info("Sent school run report")

    except Exception as e:
        logger.error(f"Failed to generate school run report: {e}")


async def school_pickup_report(bot):
    """Generate and send the afternoon school pickup report."""
    try:
        now = datetime.now()
        weekday = now.weekday()

        # Skip weekends
        if weekday >= 5:
            logger.info("Skipping school pickup report - weekend")
            return

        # Get data - use traffic TO school (home → school) for pickup planning
        traffic = await _get_traffic()
        clubs = await _get_evening_clubs(weekday)

        # Format date
        day_name = now.strftime("%a")
        date_str = now.strftime("%d %b")

        # Build message (WhatsApp format - *bold* not **bold**)
        lines = [
            f"🏫 *SCHOOL PICKUP* — {day_name} {date_str}",
            "━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            "🚦 *TRAFFIC TO SCHOOL*",
            f"📍 Correnden Rd → Stocks Green"
        ]

        if traffic.get("error"):
            lines.append("⚠️ Traffic data unavailable")
        else:
            eta = traffic["duration_in_minutes"]
            leave_time, pickup_time = _calculate_pickup_leave_time(eta, weekday)
            lines.extend([
                f"⏱️ {eta} mins via {traffic['route_name']}",
                f"🚦 {traffic['traffic_condition']}",
                f"➡️ 🎯 Leave by {leave_time} for {pickup_time} pickup"
            ])

        # Evening clubs section
        lines.extend(["", "🎯 *EVENING CLUBS*"])

        if not clubs:
            lines.append("No clubs this evening ✅")
        else:
            # Group by child
            max_clubs = [c for c in clubs if c["child_name"].lower() == "max"]
            emmie_clubs = [c for c in clubs if c["child_name"].lower() == "emmie"]

            if max_clubs:
                lines.extend(["", "Max 👦"])
                for club in max_clubs:
                    club_line = f"🏃 {club['club_name']}"
                    if club.get("pickup_time"):
                        club_line += f" — pickup {club['pickup_time']}"
                    if club.get("pickup_location"):
                        club_line += f" @ {club['pickup_location']}"
                    lines.append(club_line)
                    if club.get("notes"):
                        lines.append(f"   📝 {club['notes']}")

            if emmie_clubs:
                lines.extend(["", "Emmie 👧"])
                for club in emmie_clubs:
                    club_line = f"🏃 {club['club_name']}"
                    if club.get("pickup_time"):
                        club_line += f" — pickup {club['pickup_time']}"
                    if club.get("pickup_location"):
                        club_line += f" @ {club['pickup_location']}"
                    lines.append(club_line)
                    if club.get("notes"):
                        lines.append(f"   📝 {club['notes']}")

            # Show "no clubs" for child without any
            if not max_clubs:
                lines.extend(["", "Max 👦", "No clubs this evening ✅"])
            if not emmie_clubs:
                lines.extend(["", "Emmie 👧", "No clubs this evening ✅"])

        message = "\n".join(lines)

        # Send to both WhatsApp AND Discord
        if _is_twilio_configured():
            await _send_whatsapp(message)

        await _send_discord(bot, message)

        logger.info("Sent school pickup report")

    except Exception as e:
        logger.error(f"Failed to generate school pickup report: {e}")


def register_school_run(scheduler, bot):
    """Register the school run jobs with the scheduler.

    Morning Schedule:
    - Mon, Tue, Wed, Fri: 8:10 AM (arrive 8:38)
    - Thursday: 7:45 AM (arrive 7:58)

    Afternoon Schedule:
    - Mon, Tue, Thu, Fri: 2:55 PM
    - Wednesday: 4:50 PM
    """
    # === MORNING JOBS ===

    # Mon, Tue, Wed, Fri at 8:10 AM
    scheduler.add_job(
        school_run_report,
        'cron',
        args=[bot],
        hour=8,
        minute=10,
        day_of_week="mon,tue,wed,fri",
        timezone="Europe/London",
        id="school_run_report_standard"
    )

    # Thursday at 7:45 AM (earlier start)
    scheduler.add_job(
        school_run_report,
        'cron',
        args=[bot],
        hour=7,
        minute=45,
        day_of_week="thu",
        timezone="Europe/London",
        id="school_run_report_thursday"
    )

    # === AFTERNOON JOBS ===

    # Mon, Tue, Thu, Fri at 2:55 PM
    scheduler.add_job(
        school_pickup_report,
        'cron',
        args=[bot],
        hour=14,
        minute=55,
        day_of_week="mon,tue,thu,fri",
        timezone="Europe/London",
        id="school_pickup_report_standard"
    )

    # Wednesday at 4:50 PM
    scheduler.add_job(
        school_pickup_report,
        'cron',
        args=[bot],
        hour=16,
        minute=50,
        day_of_week="wed",
        timezone="Europe/London",
        id="school_pickup_report_wednesday"
    )

    logger.info("Registered school run jobs (Morning: Mon-Fri, Afternoon: Mon-Fri UK)")
