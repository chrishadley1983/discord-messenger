"""Japan 2026 Day Plans API Routes.

Provides day plan CRUD and daily digest email generation:
- GET /japan/day-plans — all day plans
- GET /japan/day-plans/{date} — single day plan
- PUT /japan/day-plans/{date} — update a day plan
- POST /japan/digest/send — generate & send daily digest email
"""

import asyncio
import json
import os
import platform
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/japan", tags=["Japan 2026"])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
JAPAN_TZ = ZoneInfo("Asia/Tokyo")

# City coordinates for weather lookups
CITY_COORDS = {
    "Tokyo": {"lat": 35.6762, "lng": 139.6503},
    "Osaka": {"lat": 34.6937, "lng": 135.5023},
    "Kyoto": {"lat": 35.0116, "lng": 135.7681},
    "Himeji": {"lat": 34.8394, "lng": 134.6939},
}

# Festival data scraped from festivals-guide.html (keyed by MM-DD)
FESTIVAL_DATA = {
    "04-03": "Seiryu-e in Kyoto (miss — you'll be on a plane)",
    "04-04": "Tohoku Food Festival near accommodation",
    "04-05": "Tohoku Food Festival (last day). Chidorigafuchi Illuminations evening (6-10pm)",
    "04-06": "Travel to Osaka. Kanamara Festival in Kawasaki (quirky, if interested)",
    "04-07": "USJ Cool Japan 2026 running",
    "04-08": "Nara day trip. Hana Matsuri at temples (check Shitennoji)",
    "04-09": "Osaka exploring. Watch mint.go.jp for Mint Bureau announcement",
    "04-10": "Himeji to Kyoto. HIRANO SHRINE OKA-SAI (Procession 1pm, Illuminations 6-9pm)",
    "04-11": "Kyoto exploring. Consider Miyako Odori evening show",
    "04-12": "Kyoto exploring",
    "04-13": "teamLab Biovortex 9am THEN Yasurai Festival noon — Can do BOTH!",
    "04-14": "Travel to Tokyo 2 accommodation",
    "04-15": "DisneySea 25th Sparkling Jubilee LAUNCHES",
    "04-16": "Flex day. Nezu Shrine azaleas (steps from stay)",
    "04-17": "Craft Sake Week opens. Nezu Shrine continues",
    "04-18": "Tohoku Food Festival (second run!). Craft Sake Week. Pack. LAST FULL DAY.",
    "04-19": "Red-eye departure 01:30",
}

# WMO weather code descriptions
WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Slight showers", 81: "Moderate showers", 82: "Violent showers",
    95: "Thunderstorm", 96: "Thunderstorm + hail", 99: "Thunderstorm + heavy hail",
}

WMO_EMOJI = {
    0: "☀️", 1: "🌤️", 2: "⛅", 3: "☁️",
    45: "🌫️", 48: "🌫️",
    51: "🌦️", 53: "🌦️", 55: "🌧️",
    61: "🌧️", 63: "🌧️", 65: "🌧️",
    71: "❄️", 73: "❄️", 75: "❄️",
    80: "🌦️", 81: "🌧️", 82: "⛈️",
    95: "⛈️", 96: "⛈️", 99: "⛈️",
}


def _supabase_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
        "Accept-Profile": "japan",
        "Content-Profile": "japan",
    }


def _load_smtp_config() -> dict:
    config_path = Path.home() / ".skills" / "skills" / "amazon-delivery-performance" / "smtp_config.json"
    with open(config_path) as f:
        return json.load(f)


# ============================================================
# Day Plans CRUD
# ============================================================


@router.get("/day-plans")
async def get_all_day_plans():
    """Get all day plans."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/japan_day_plans",
            headers=_supabase_headers(),
            params={"select": "*", "order": "day_date.asc"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.get("/day-plans/{date}")
async def get_day_plan(date: str):
    """Get plan for a specific date (YYYY-MM-DD)."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/japan_day_plans",
            headers=_supabase_headers(),
            params={"select": "*", "day_date": f"eq.{date}"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    rows = resp.json()
    if not rows:
        raise HTTPException(status_code=404, detail=f"No plan found for {date}")
    return rows[0]


@router.put("/day-plans/{date}")
async def update_day_plan(date: str, request: Request):
    """Update plan for a specific date. Body can include: city, stay_name, plan_data, notes."""
    body = await request.json()
    body["updated_at"] = datetime.now(JAPAN_TZ).isoformat()

    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{SUPABASE_URL}/rest/v1/japan_day_plans",
            headers=_supabase_headers(),
            params={"day_date": f"eq.{date}"},
            json=body,
        )
    if resp.status_code not in (200, 204):
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    rows = resp.json() if resp.status_code == 200 else []
    if not rows:
        raise HTTPException(status_code=404, detail=f"No plan found for {date}")
    return rows[0]


# ============================================================
# Daily Digest
# ============================================================


async def _fetch_weather(city: str, date: str) -> Optional[dict]:
    """Fetch weather forecast from Open-Meteo for a city and date."""
    coords = CITY_COORDS.get(city)
    if not coords:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": coords["lat"],
                    "longitude": coords["lng"],
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode",
                    "hourly": "temperature_2m,weathercode",
                    "timezone": "Asia/Tokyo",
                    "start_date": date,
                    "end_date": date,
                },
            )
        if resp.status_code != 200:
            return None
        data = resp.json()
        daily = data.get("daily", {})
        hourly = data.get("hourly", {})
        code = daily.get("weathercode", [None])[0]
        return {
            "temp_max": daily.get("temperature_2m_max", [None])[0],
            "temp_min": daily.get("temperature_2m_min", [None])[0],
            "precip_chance": daily.get("precipitation_probability_max", [None])[0],
            "weathercode": code,
            "description": WMO_CODES.get(code, "Unknown"),
            "emoji": WMO_EMOJI.get(code, ""),
            "hourly_temps": hourly.get("temperature_2m", []),
            "hourly_codes": hourly.get("weathercode", []),
            "hourly_times": hourly.get("time", []),
        }
    except Exception:
        return None


STAY_DETAILS = {
    "Kitashinjuku": {
        "address": "Kitashinjuku, Shinjuku-ku (10 min walk from Okubo Station)",
        "lat": 35.6983, "lng": 139.6980,
        "maps_url": "https://www.google.com/maps/@35.6983,139.6980,17z",
        "airbnb_url": "https://www.airbnb.co.uk/rooms/1435090176758958325",
        "dates": "Apr 3-6", "checkin": "15:00", "checkout": "11:00",
        "host": "Tokyo Look In",
    },
    "Nezu": {
        "address": "Taito-ku, near Nezu Station (5 min walk)",
        "lat": 35.7206, "lng": 139.7631,
        "maps_url": "https://www.google.com/maps/@35.7206,139.7631,17z",
        "airbnb_url": "https://www.airbnb.co.uk/rooms/38715469",
        "dates": "Apr 14-19", "checkin": "15:00", "checkout": "11:00",
        "host": "Toshiko",
    },
    "Dotonbori": {
        "address": "2-8-29 Nishishinsaibashi, Chuo-ku, Osaka 542-0086, Room 505",
        "lat": 34.6687, "lng": 135.5013,
        "maps_url": "https://www.google.com/maps/search/2-8-29+Nishishinsaibashi+Chuo-ku+Osaka+Japan",
        "airbnb_url": "https://www.airbnb.co.uk/rooms/1021422103080497459",
        "dates": "Apr 6-10", "checkin": "16:00", "checkout": "10:00",
        "host": "Yoko & Nobu",
    },
    "Kyoto Stay": {
        "address": "Shimogyo Ward, Kyoto (7 min to subway)",
        "lat": 35.0116, "lng": 135.7681,
        "maps_url": "https://www.google.com/maps/@35.0116,135.7681,17z",
        "airbnb_url": "https://www.airbnb.co.uk/rooms/17870822",
        "dates": "Apr 10-14", "checkin": "15:00", "checkout": "11:00",
        "host": "Team LUX",
    },
    "Travel Day": {"address": "On the move!", "lat": None, "lng": None, "maps_url": None, "airbnb_url": None},
}

# Nearby picks per stay — curated recommendations
NEARBY_PICKS = {
    "Kitashinjuku": [
        {"name": "Shin-Okubo KoreaTown", "desc": "Korean BBQ & cheese hotdogs. 10 min walk!", "emoji": "🇰🇷", "cat": "activity"},
        {"name": "Omoide Yokocho", "desc": "Atmospheric yakitori alley under the tracks", "emoji": "🏮", "cat": "activity"},
        {"name": "Fuunji Tsukemen", "desc": "Shinjuku's best dipping ramen. Worth the queue", "emoji": "🍜", "cat": "food"},
        {"name": "Shogun Burger", "desc": "100% wagyu double cheese. 6 min from station", "emoji": "🍔", "cat": "food"},
        {"name": "Chatei Hatou", "desc": "Moody kissaten. Charcoal-roasted coffee", "emoji": "☕", "cat": "coffee"},
        {"name": "Shinjuku Gyoen", "desc": "200 cherry trees, perfect morning walk", "emoji": "🌸", "cat": "activity"},
        {"name": "Samurai Museum", "desc": "Dress-up & sword demos. Open until 9pm", "emoji": "⚔️", "cat": "activity"},
        {"name": "Godaime Hanayama Udon", "desc": "Famous thick udon. Kid-friendly. From Y800", "emoji": "🍜", "cat": "food"},
    ],
    "Nezu": [
        {"name": "Nezu Shrine", "desc": "Torii tunnel + April azaleas. 5 min walk!", "emoji": "⛩️", "cat": "activity"},
        {"name": "Ueno Park & Museums", "desc": "Science Museum, Zoo (pandas!), cherry blossoms", "emoji": "🌳", "cat": "activity"},
        {"name": "Ameyoko Market", "desc": "Chaotic market — fruit sticks, seafood, bargains", "emoji": "🏪", "cat": "activity"},
        {"name": "ANDRA burger", "desc": "Cheese-griddle burger. Near our stay. Closed Sun", "emoji": "🍔", "cat": "food"},
        {"name": "Senso-ji at 7am", "desc": "Lanterns lit, empty Nakamise. 15 min walk", "emoji": "🏮", "cat": "activity"},
        {"name": "Grill GRAND", "desc": "Bib Gourmand omurice. Near Senso-ji. Kids love it", "emoji": "🍳", "cat": "food"},
        {"name": "Cafe de l'Ambre", "desc": "Since 1948. Only aged coffee beans. Ginza", "emoji": "☕", "cat": "coffee"},
        {"name": "Matcha Stand Maruni", "desc": "Gorgeous matcha lattes. Tsukiji pit stop", "emoji": "🍵", "cat": "coffee"},
    ],
    "Dotonbori": [
        {"name": "Dotonbori street food", "desc": "Takoyaki, gyoza, kushikatsu — just step outside", "emoji": "🐙", "cat": "food"},
        {"name": "Hozenji Temple", "desc": "Moss-covered statue, 2 min walk. Best at night", "emoji": "⛩️", "cat": "activity"},
        {"name": "Kushikatsu Daruma", "desc": "Since 1929. The original. No double-dipping!", "emoji": "🍢", "cat": "food"},
        {"name": "Ikura Shinsaibashi", "desc": "Viral omuburg. Near our stay. Kids will devour", "emoji": "🍳", "cat": "food"},
        {"name": "Den Den Town", "desc": "Osaka's Akihabara. Walk south from Namba", "emoji": "🎮", "cat": "activity"},
        {"name": "Namba Yasaka Shrine", "desc": "Giant lion head. 10 min walk", "emoji": "🦁", "cat": "activity"},
        {"name": "Ult Coffee", "desc": "World's 100 Best Coffee Shops 2026", "emoji": "☕", "cat": "coffee"},
    ],
    "Kyoto Stay": [
        {"name": "Nishiki Market", "desc": "Kyoto's Kitchen. 130+ stalls. Go before 10am", "emoji": "🏮", "cat": "activity"},
        {"name": "Gion District", "desc": "Spot maiko at 5:30-6:30pm along Hanami-koji", "emoji": "🎭", "cat": "activity"},
        {"name": "Chao Chao Gyoza", "desc": "National champion gyoza. Chocolate gyoza for kids!", "emoji": "🥟", "cat": "food"},
        {"name": "A Happy Pancake", "desc": "Kyoto-exclusive souffle pancakes. Book 2 wks ahead", "emoji": "🥞", "cat": "food"},
        {"name": "% Arabica Arashiyama", "desc": "World-famous latte art. Stunning river views", "emoji": "☕", "cat": "coffee"},
        {"name": "Gokago", "desc": "Premium Uji matcha latte on route to Kiyomizu", "emoji": "🍵", "cat": "coffee"},
        {"name": "Weekenders Coffee", "desc": "Kyoto's best independent roaster", "emoji": "☕", "cat": "coffee"},
        {"name": "Nijo Castle", "desc": "Nightingale floors + 400 cherry trees", "emoji": "🏯", "cat": "activity"},
    ],
}

# Monday closure warnings
MONDAY_CLOSURES = [
    "Most Ueno Park museums (National Museum, Western Art, Science Museum)",
    "Edo-Tokyo Museum",
    "Miraikan Science Museum",
    "Many smaller museums and galleries",
]

TUESDAY_CLOSURES = [
    "Miraikan Science Museum",
    "Cup Noodles Museum (Ikeda)",
]


def _build_digest_html(plan: dict, weather: Optional[dict], festivals: Optional[str],
                       tomorrow_plan: Optional[dict] = None) -> str:
    """Build a comprehensive styled HTML email for the daily digest."""
    date_str = plan["day_date"]
    city = plan["city"]
    stay = plan.get("stay_name", "")
    notes = plan.get("notes", "")
    items = plan.get("plan_data", [])

    dt = datetime.strptime(date_str, "%Y-%m-%d")
    day_label = dt.strftime("%A, %B %#d" if platform.system() == "Windows" else "%A, %B %-d")
    trip_day = (dt - datetime(2026, 4, 3)).days + 1
    day_of_week = dt.strftime("%A")

    # ============ WEATHER SECTION ============
    weather_html = ""
    if weather and weather.get("temp_max") is not None:
        precip = weather.get("precip_chance", 0) or 0
        verdict = "☂️ Bring an umbrella!" if precip >= 50 else ("🌂 Might drizzle" if precip >= 30 else "☀️ Perfect day!")
        verdict_bg = "#fff3cd" if precip >= 50 else ("#e8f4fd" if precip >= 30 else "#e8f5e9")
        verdict_color = "#856404" if precip >= 50 else ("#1a5276" if precip >= 30 else "#2e7d32")

        # Hourly breakdown for key hours (9am, 12pm, 3pm, 6pm)
        hourly_html = ""
        key_hours = [9, 12, 15, 18]
        hourly_temps = weather.get("hourly_temps", [])
        hourly_codes = weather.get("hourly_codes", [])
        if len(hourly_temps) >= 19:
            hourly_cells = ""
            for h in key_hours:
                temp = hourly_temps[h] if h < len(hourly_temps) else "?"
                code = hourly_codes[h] if h < len(hourly_codes) else 0
                h_emoji = WMO_EMOJI.get(code, "")
                label = f"{h}:00" if h < 12 else (f"{h}:00" if h > 12 else "12:00")
                hourly_cells += f"""
                <td style="text-align:center;padding:8px 4px;width:25%">
                    <div style="font-size:11px;color:#777">{label}</div>
                    <div style="font-size:18px;margin:4px 0">{h_emoji}</div>
                    <div style="font-size:14px;font-weight:600;color:#333">{temp:.0f}°</div>
                </td>"""
            hourly_html = f"""
            <table style="width:100%;border-collapse:collapse;margin-top:12px;border-top:1px solid #d4e6f1;padding-top:8px">
                <tr>{hourly_cells}</tr>
            </table>"""

        weather_html = f"""
        <div style="background:#e8f4fd;border-radius:12px;padding:20px;margin-bottom:16px">
            <div style="font-size:16px;font-weight:700;color:#1a5276;margin-bottom:12px">🌤️ Weather in {city}</div>
            <div style="display:flex;align-items:center;gap:16px;margin-bottom:8px">
                <div style="font-size:40px">{weather['emoji']}</div>
                <div>
                    <div style="font-size:16px;font-weight:600;color:#1a5276">{weather['description']}</div>
                    <div style="font-size:14px;color:#2c3e50;margin-top:2px">High {weather['temp_max']}° / Low {weather['temp_min']}° · Rain {precip}%</div>
                </div>
            </div>
            {hourly_html}
        </div>
        <div style="background:{verdict_bg};border-radius:8px;padding:12px 16px;margin-bottom:24px;text-align:center;font-size:14px;font-weight:600;color:{verdict_color}">
            {verdict}
        </div>
        """
    elif not weather:
        weather_html = """
        <div style="background:#f5f5f5;border-radius:12px;padding:16px;margin-bottom:24px;text-align:center;font-size:13px;color:#999">
            🌤️ Weather forecast not yet available (shows ~14 days before trip)
        </div>
        """

    # ============ FESTIVALS & EVENTS ============
    festival_html = ""
    if festivals:
        festival_html = f"""
        <div style="background:#fff8e1;border-left:4px solid #f9a825;border-radius:0 12px 12px 0;padding:16px 20px;margin-bottom:16px">
            <div style="font-weight:700;color:#f57f17;font-size:14px;margin-bottom:4px">🎌 What's Happening Today</div>
            <div style="font-size:14px;color:#5d4037">{festivals}</div>
        </div>
        """

    # ============ CLOSURES WARNING ============
    closures_html = ""
    if day_of_week == "Monday":
        closure_list = "".join(f"<li style='margin-bottom:4px'>{c}</li>" for c in MONDAY_CLOSURES)
        closures_html = f"""
        <div style="background:#ffebee;border-left:4px solid #c41e3a;border-radius:0 12px 12px 0;padding:16px 20px;margin-bottom:16px">
            <div style="font-weight:700;color:#c41e3a;font-size:14px;margin-bottom:4px">🚫 Monday Closures</div>
            <ul style="font-size:13px;color:#8b1a2b;margin:0;padding-left:20px">{closure_list}</ul>
        </div>
        """
    elif day_of_week == "Tuesday":
        closure_list = "".join(f"<li style='margin-bottom:4px'>{c}</li>" for c in TUESDAY_CLOSURES)
        closures_html = f"""
        <div style="background:#ffebee;border-left:4px solid #c41e3a;border-radius:0 12px 12px 0;padding:16px 20px;margin-bottom:16px">
            <div style="font-weight:700;color:#c41e3a;font-size:14px;margin-bottom:4px">🚫 Tuesday Closures</div>
            <ul style="font-size:13px;color:#8b1a2b;margin:0;padding-left:20px">{closure_list}</ul>
        </div>
        """

    # ============ NOTES ============
    notes_html = ""
    if notes:
        notes_html = f"""
        <div style="background:#f3e5f5;border-left:4px solid #8e24aa;border-radius:0 12px 12px 0;padding:16px 20px;margin-bottom:16px">
            <div style="font-weight:700;color:#6a1b9a;font-size:14px;margin-bottom:4px">📝 Notes</div>
            <div style="font-size:14px;color:#4a148c">{notes}</div>
        </div>
        """

    # ============ TIMELINE ============
    timeline_html = ""
    if items:
        type_colors = {
            "attraction": "#c41e3a", "food": "#d4760a", "transport": "#4a90d9",
            "logistics": "#7b68ae", "shopping": "#5b8c5a", "rest": "#f0a0b0",
        }
        for item in items:
            color = type_colors.get(item.get("type", ""), "#8b6914")
            emoji = item.get("emoji", "")
            time_str = item.get("time", "")
            end_time = item.get("end_time", "")
            title = item.get("title", "")
            location = item.get("location", "")
            item_notes = item.get("notes", "")
            price = item.get("price_jpy", 0)
            booked = item.get("booked", False)

            time_display = f"{time_str}–{end_time}" if end_time else time_str

            meta_parts = []
            if location:
                meta_parts.append(f"📍 {location}")
            if item_notes:
                meta_parts.append(item_notes)
            if price and price > 0:
                gbp = round(price / 200)
                meta_parts.append(f"\u00a5{price:,} (~\u00a3{gbp})")
            meta = " · ".join(meta_parts)

            booked_badge = ""
            if booked:
                booked_badge = '<span style="display:inline-block;background:#e8f5e9;color:#2e7d32;font-size:10px;font-weight:700;padding:2px 8px;border-radius:4px;margin-left:8px;text-transform:uppercase;letter-spacing:0.5px">Booked</span>'

            timeline_html += f"""
            <tr>
                <td style="padding:10px 12px 10px 0;vertical-align:top;width:80px;font-size:12px;font-weight:700;color:{color};white-space:nowrap">{time_display}</td>
                <td style="padding:10px 0;vertical-align:top;border-bottom:1px solid #f0ece4">
                    <div style="font-size:15px;font-weight:600;color:#1c1c1c">{emoji} {title}{booked_badge}</div>
                    <div style="font-size:12px;color:#777;margin-top:3px">{meta}</div>
                </td>
            </tr>
            """

    plan_section = ""
    if timeline_html:
        booked_count = sum(1 for i in items if i.get("booked"))
        plan_subtitle = f"{len(items)} activities" + (f" · {booked_count} booked" if booked_count else "")
        plan_section = f"""
        <div style="margin-bottom:24px">
            <div style="font-size:16px;font-weight:700;color:#1c1c1c;margin-bottom:4px">🗓️ Today's Plan</div>
            <div style="font-size:12px;color:#777;margin-bottom:12px;padding-bottom:8px;border-bottom:2px solid #e0d8cc">{plan_subtitle}</div>
            <table style="width:100%;border-collapse:collapse">{timeline_html}</table>
        </div>
        """
    else:
        plan_section = """
        <div style="background:#f5f5f5;border-radius:12px;padding:24px;text-align:center;margin-bottom:24px;color:#999;font-size:14px">
            No activities planned yet — free day! Check the nearby picks below.
        </div>
        """

    # ============ NEARBY QUICK PICKS ============
    nearby_html = ""
    # Try stay name first, then city, then map common city names to stay keys
    city_to_stay = {"Tokyo": "Kitashinjuku", "Osaka": "Dotonbori", "Kyoto": "Kyoto Stay", "Himeji": "Kyoto Stay"}
    stay_key = stay if stay in NEARBY_PICKS else (city if city in NEARBY_PICKS else city_to_stay.get(city, ""))
    picks = NEARBY_PICKS.get(stay_key, [])
    if picks:
        # Split into activities and food/coffee
        activity_picks = [p for p in picks if p.get("cat") == "activity"]
        food_picks = [p for p in picks if p.get("cat") in ("food", "coffee")]

        def _render_picks(pick_list):
            rows = ""
            for p in pick_list:
                rows += f"""
                <tr>
                    <td style="padding:8px 12px 8px 0;vertical-align:top;font-size:18px;width:30px">{p['emoji']}</td>
                    <td style="padding:8px 0;vertical-align:top;border-bottom:1px solid #f0ece4">
                        <div style="font-size:14px;font-weight:600;color:#1c1c1c">{p['name']}</div>
                        <div style="font-size:12px;color:#777;margin-top:2px">{p['desc']}</div>
                    </td>
                </tr>"""
            return rows

        sections = ""
        if activity_picks:
            sections += f"""
            <div style="font-size:13px;font-weight:700;color:#5b8c5a;margin:12px 0 8px;text-transform:uppercase;letter-spacing:1px">🎯 Activities</div>
            <table style="width:100%;border-collapse:collapse">{_render_picks(activity_picks)}</table>"""
        if food_picks:
            sections += f"""
            <div style="font-size:13px;font-weight:700;color:#d4760a;margin:16px 0 8px;text-transform:uppercase;letter-spacing:1px">🍽️ Food, Coffee & Treats</div>
            <table style="width:100%;border-collapse:collapse">{_render_picks(food_picks)}</table>"""

        nearby_html = f"""
        <div style="margin-bottom:24px">
            <div style="font-size:16px;font-weight:700;color:#1c1c1c;margin-bottom:4px">💡 If You Have a Spare Hour...</div>
            <div style="font-size:12px;color:#777;margin-bottom:8px;padding-bottom:8px;border-bottom:2px solid #e0d8cc">Near {stay}</div>
            {sections}
        </div>
        """

    # ============ PRACTICAL FOOTER ============
    stay_info = STAY_DETAILS.get(stay, STAY_DETAILS.get("Kitashinjuku", {}))
    stay_address = stay_info.get("address", "")
    maps_url = stay_info.get("maps_url", "")
    airbnb_url = stay_info.get("airbnb_url", "")

    # Check if moving stays tomorrow
    moving_html = ""
    if tomorrow_plan and tomorrow_plan.get("stay_name") != stay:
        checkout_time = stay_info.get("checkout", "11:00") if stay_info else "11:00"
        next_stay = tomorrow_plan.get("stay_name", "next stay")
        next_info = STAY_DETAILS.get(next_stay, {})
        checkin_time = next_info.get("checkin", "15:00")
        moving_html = f"""
        <div style="background:#fff3cd;border-radius:8px;padding:10px 14px;margin-bottom:8px;font-size:13px;color:#856404">
            📦 <strong>Moving tomorrow!</strong> Check-out by {checkout_time} → head to {next_stay} ({tomorrow_plan.get('city', '')}) · Check-in from {checkin_time}
        </div>"""

    tomorrow_preview = ""
    if tomorrow_plan:
        t_city = tomorrow_plan.get("city", "")
        t_items = tomorrow_plan.get("plan_data", [])
        t_count = len(t_items)
        if t_count == 0:
            t_summary = "No plans yet — free to explore!"
        elif t_count == 1:
            t_summary = t_items[0].get("title", "1 activity")
        else:
            t_first = t_items[0].get("title", "")
            t_summary = f"{t_first} + {t_count - 1} more"
        tomorrow_preview = f"""
        <div style="font-size:13px;color:#555;margin-top:8px">
            <strong>Tomorrow:</strong> {t_city} — {t_summary}
        </div>"""

    footer_html = f"""
        <div style="background:#f5f5f5;border-radius:12px;padding:20px;margin-bottom:16px">
            <div style="font-size:14px;font-weight:700;color:#333;margin-bottom:8px">🏠 Tonight's Stay</div>
            <div style="font-size:13px;color:#555;margin-bottom:6px">{stay} — {stay_address}</div>
            <div style="font-size:12px">{'<a href="' + maps_url + '" style="color:#4a90d9;text-decoration:none;margin-right:12px">📍 Google Maps</a>' if maps_url else ''}{'<a href="' + airbnb_url + '" style="color:#FF5A5F;text-decoration:none">🏡 Airbnb Listing</a>' if airbnb_url else ''}</div>
            {moving_html}
            {tomorrow_preview}
        </div>
        <div style="background:#ffebee;border-radius:12px;padding:16px;margin-bottom:16px">
            <div style="font-size:13px;color:#c41e3a;text-align:center">
                🚨 <strong>Emergency:</strong> Police 110 · Ambulance 119 · Fire 119 · Tourist helpline 050-3816-2787
            </div>
        </div>
        <div style="text-align:center;font-size:11px;color:#999;padding:16px 0">
            <a href="https://hadley-japan-2026.surge.sh/day-planner.html" style="color:#c41e3a;text-decoration:none;font-weight:600">Edit Day Plans</a>
            · <a href="https://hadley-japan-2026.surge.sh" style="color:#c41e3a;text-decoration:none">All Guides</a>
            · Hadley Family Japan 2026
        </div>
    """

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f7f3eb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
    <div style="max-width:600px;margin:0 auto;padding:20px">
        <div style="background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);border-radius:16px;padding:32px 24px;text-align:center;color:white;margin-bottom:24px">
            <div style="font-size:40px;margin-bottom:8px">🇯🇵</div>
            <div style="font-size:24px;font-weight:900;letter-spacing:1px">{day_label}</div>
            <div style="font-size:14px;opacity:0.7;margin-top:6px">Day {trip_day} of 17 · {city}{f" · staying {stay}" if stay and stay != city else ""}</div>
        </div>
        {weather_html}
        {festival_html}
        {closures_html}
        {notes_html}
        {plan_section}
        {nearby_html}
        {footer_html}
    </div>
</body>
</html>"""
    return html


@router.post("/digest/send")
async def send_digest(request: Request):
    """Generate and send daily digest email for a specific date.

    Body: {"date": "2026-04-10", "recipient": "optional@email.com"}
    """
    body = await request.json()
    date = body.get("date")
    if not date:
        raise HTTPException(status_code=400, detail="date is required (YYYY-MM-DD)")

    # Validate date format
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format, use YYYY-MM-DD")

    # 1. Fetch day plan from Supabase
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/japan_day_plans",
            headers=_supabase_headers(),
            params={"select": "*", "day_date": f"eq.{date}"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Supabase error: {resp.text}")
    rows = resp.json()
    if not rows:
        raise HTTPException(status_code=404, detail=f"No plan found for {date}")
    plan = rows[0]

    # 2. Fetch weather
    weather = await _fetch_weather(plan["city"], date)

    # 3. Check festivals
    mm_dd = date[5:]  # "04-10"
    festivals = FESTIVAL_DATA.get(mm_dd)

    # 4. Fetch tomorrow's plan for preview
    from datetime import timedelta as _td
    tomorrow_dt = datetime.strptime(date, "%Y-%m-%d") + _td(days=1)
    tomorrow_str = tomorrow_dt.strftime("%Y-%m-%d")
    tomorrow_plan = None
    try:
        async with httpx.AsyncClient() as client:
            resp2 = await client.get(
                f"{SUPABASE_URL}/rest/v1/japan_day_plans",
                headers=_supabase_headers(),
                params={"select": "*", "day_date": f"eq.{tomorrow_str}"},
            )
        if resp2.status_code == 200 and resp2.json():
            tomorrow_plan = resp2.json()[0]
    except Exception:
        pass

    # 5. Build HTML
    html = _build_digest_html(plan, weather, festivals, tomorrow_plan)

    # 6. Send via SMTP
    smtp_config = _load_smtp_config()
    recipient = body.get("recipient", smtp_config["default_recipient"])

    dt = datetime.strptime(date, "%Y-%m-%d")
    day_label = dt.strftime("%A %B %#d" if platform.system() == "Windows" else "%A %B %-d")
    trip_day = (dt - datetime(2026, 4, 3)).days + 1
    subject = f"🇯🇵 Japan Day {trip_day}: {plan['city']} \u2014 {day_label}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_config["sender_email"]
    msg["To"] = recipient
    msg.attach(MIMEText(f"Japan Day {trip_day}: {plan['city']} - {day_label}", "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(smtp_config["smtp_host"], smtp_config["smtp_port"]) as server:
            server.starttls()
            server.login(smtp_config["sender_email"], smtp_config["app_password"])
            server.send_message(msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")

    return {
        "status": "sent",
        "date": date,
        "city": plan["city"],
        "recipient": recipient,
        "items_count": len(plan.get("plan_data", [])),
        "weather": weather is not None,
        "festivals": festivals is not None,
    }


# ============================================================
# Japan Sim Mode (for testing concierge from UK)
# ============================================================

SIM_FILE = Path(__file__).parent.parent / "data" / "japan_sim_date.txt"


@router.get("/sim")
async def get_sim_date():
    """Get current Japan sim date."""
    if SIM_FILE.exists():
        val = SIM_FILE.read_text().strip()
        return {"sim_date": val if val else None, "active": bool(val)}
    return {"sim_date": None, "active": False}


@router.post("/sim")
async def set_sim_date(request: Request):
    """Set Japan sim date for testing. Body: {"date": "2026-04-09"} or {"date": ""} to clear.

    This makes Peter's WhatsApp responses include Japan trip context for the given date.
    """
    body = await request.json()
    date_val = body.get("date", "")

    if date_val:
        try:
            datetime.strptime(date_val, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format, use YYYY-MM-DD")

    SIM_FILE.write_text(date_val)

    if date_val:
        return {"status": "sim_active", "date": date_val, "message": f"Peter will now respond as if it's {date_val} in Japan"}
    else:
        return {"status": "sim_cleared", "message": "Japan sim mode deactivated"}


# ============================================================
# Photo Book Pipeline
# ============================================================

# Google Drive folder IDs for each trip day
DRIVE_FOLDER_IDS = {
    1: "1hqMuktacySr3GopUhe1NMEeAeknZpf1A",   # Day 01 - Apr 3 - Tokyo Arrival
    2: "1DIBiiPknSHaDQODkLlpM-QDaccVA8OGK",   # Day 02 - Apr 4 - Tokyo
    3: "1dreeeD8l_Ho_938fcr4Jc5vq00eqZiCp",   # Day 03 - Apr 5 - Tokyo
    4: "1PahQ-EkFWreQxqltIlqjHgooPtSNykdM",   # Day 04 - Apr 6 - Tokyo to Osaka
    5: "16rZihI3OlMVVY33nhgb0KFlpCN-gGyx8",   # Day 05 - Apr 7 - Osaka
    6: "189S8xOMQ4clqReuwp7rCVv_JWVRXenN5",   # Day 06 - Apr 8 - Osaka (Nara)
    7: "1BzHZG3DRgwDjj67Iv3HNYn5tVvGwlbmb",   # Day 07 - Apr 9 - Osaka
    8: "1mbBcRNqJITUg6ynWqCWObJeSyFN7jEWj",   # Day 08 - Apr 10 - Himeji to Kyoto
    9: "1k-3-AI3NfCdpROeE0mG7Koy9hU4nFFDc",   # Day 09 - Apr 11 - Kyoto
    10: "1Xp7U-4tKDFkHqHbYUoRKTibwj6aVpP8A",  # Day 10 - Apr 12 - Kyoto
    11: "15d19FZx643eOGLoCtjbbGcIjVp8-z8Fc",   # Day 11 - Apr 13 - Kyoto
    12: "1FrF-SlI8UtE55zJsuz-V-UcuZxRxDB_t",   # Day 12 - Apr 14 - Kyoto to Tokyo
    13: "1i7Ghc3iac4rvnAhGbFgK5hn8DFtgh_jq",   # Day 13 - Apr 15 - Tokyo
    14: "1hQPiScYYeI9hGgoGqFSxWrTc9SovmmiM",   # Day 14 - Apr 16 - Tokyo
    15: "1LvL2Ay5n17H6ibgkH55XWHhjfYSQ2JeA",   # Day 15 - Apr 17 - Tokyo
    16: "1ipNbZw9P6a8a1wQLMx85rVcjs2yZpG4v",   # Day 16 - Apr 18 - Tokyo
    17: "1RCA1P62F83Mu6W1yzi2ikA6GhcJzH1Z3",   # Day 17 - Apr 19 - Departure
}
DRIVE_FOLDER_EXTRAS = "1oQ01PSG0LTO_AOHlHkCzzUFlL-UrBX4_"  # Highlights & Extras

# Day-to-date mapping
DAY_TO_DATE = {d: f"2026-04-{d + 2:02d}" for d in range(1, 18)}

# Day-to-city mapping
DAY_TO_CITY = {
    1: "Tokyo", 2: "Tokyo", 3: "Tokyo",
    4: "Osaka", 5: "Osaka", 6: "Osaka", 7: "Osaka",
    8: "Kyoto", 9: "Kyoto", 10: "Kyoto", 11: "Kyoto",
    12: "Tokyo", 13: "Tokyo", 14: "Tokyo", 15: "Tokyo", 16: "Tokyo", 17: "Tokyo",
}


def _get_current_trip_day() -> int | None:
    """Get current trip day number (1-17) or None if outside trip."""
    sim_file = Path(__file__).parent.parent / "data" / "japan_sim_date.txt"
    sim_date = ""
    if sim_file.exists():
        sim_date = sim_file.read_text().strip()

    if sim_date:
        try:
            dt = datetime.strptime(sim_date, "%Y-%m-%d")
        except ValueError:
            return None
    else:
        now_jst = datetime.now(JAPAN_TZ)
        dt = datetime(now_jst.year, now_jst.month, now_jst.day)

    trip_start = datetime(2026, 4, 3)
    trip_end = datetime(2026, 4, 19)
    if dt < trip_start or dt > trip_end:
        return None
    return (dt - trip_start).days + 1


def _japan_supabase_headers() -> dict:
    """Supabase headers targeting the japan schema."""
    return {
        **_supabase_headers(),
        "Content-Profile": "japan",
        "Accept-Profile": "japan",
    }


@router.post("/photobook/upload")
async def photobook_upload(request: Request):
    """Upload a photo to Google Drive and store metadata in Supabase.

    Body: {
        "local_path": "/path/to/photo.jpg",
        "caption": "Emmie feeding the deer at Nara",
        "sender": "Chris",
        "day_number": 6  (optional, auto-detected from JST date)
    }
    """
    body = await request.json()
    local_path = body.get("local_path", "")

    if not local_path or not Path(local_path).exists():
        raise HTTPException(status_code=400, detail=f"File not found: {local_path}")

    # Determine day number
    day_number = body.get("day_number") or _get_current_trip_day()
    if not day_number or day_number < 1 or day_number > 17:
        raise HTTPException(status_code=400, detail="Cannot determine trip day. Provide day_number (1-17).")

    folder_id = DRIVE_FOLDER_IDS.get(day_number, DRIVE_FOLDER_EXTRAS)
    sender = body.get("sender", "Chris")
    caption = body.get("caption", "")
    filename = Path(local_path).name

    # Upload to Google Drive
    try:
        from hadley_api.google_auth import get_drive_service
        from googleapiclient.http import MediaFileUpload
        import mimetypes

        drive = get_drive_service()
        mime_type = mimetypes.guess_type(local_path)[0] or "image/jpeg"

        file_metadata = {"name": filename, "parents": [folder_id]}
        media = MediaFileUpload(local_path, mimetype=mime_type)
        drive_file = drive.files().create(
            body=file_metadata, media_body=media,
            fields="id,webViewLink"
        ).execute()

        drive_file_id = drive_file.get("id", "")
        drive_url = drive_file.get("webViewLink", "")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Drive upload failed: {e}")

    # Store metadata in Supabase
    photo_row = {
        "day_number": day_number,
        "day_date": DAY_TO_DATE.get(day_number),
        "drive_file_id": drive_file_id,
        "drive_url": drive_url,
        "filename": filename,
        "caption": caption,
        "sent_by": sender,
        "city": DAY_TO_CITY.get(day_number, ""),
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/japan_photos",
            headers=_japan_supabase_headers(),
            json=photo_row,
        )

    return {
        "status": "uploaded",
        "day_number": day_number,
        "drive_url": drive_url,
        "filename": filename,
        "caption": caption,
    }


@router.post("/photobook/highlight")
async def photobook_highlight(request: Request):
    """Store a one-liner highlight for the photo book.

    Body: {
        "text": "Max fell asleep on the bullet train",
        "sender": "Chris",
        "day_number": 4  (optional, auto-detected)
    }
    """
    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    day_number = body.get("day_number") or _get_current_trip_day()
    if not day_number or day_number < 1 or day_number > 17:
        raise HTTPException(status_code=400, detail="Cannot determine trip day. Provide day_number (1-17).")

    row = {
        "day_number": day_number,
        "text": text,
        "sent_by": body.get("sender", "Chris"),
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/japan_highlights",
            headers=_japan_supabase_headers(),
            json=row,
        )

    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    return {"status": "saved", "day_number": day_number, "text": text}


@router.post("/photobook/diary")
async def photobook_diary(request: Request):
    """Store a diary entry or voice note transcription.

    Body: {
        "content": "Day 5 was all about Dotonbori...",
        "source": "text" or "voice_note",
        "sender": "Chris",
        "day_number": 5  (optional, auto-detected)
    }
    """
    body = await request.json()
    content = body.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content is required")

    day_number = body.get("day_number") or _get_current_trip_day()
    if not day_number or day_number < 1 or day_number > 17:
        raise HTTPException(status_code=400, detail="Cannot determine trip day. Provide day_number (1-17).")

    row = {
        "day_number": day_number,
        "content": content,
        "source": body.get("source", "text"),
        "sent_by": body.get("sender", "Chris"),
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/japan_diary",
            headers=_japan_supabase_headers(),
            json=row,
        )

    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    return {"status": "saved", "day_number": day_number, "source": row["source"], "length": len(content)}


@router.get("/photobook/coverage/{day_number}")
async def photobook_coverage(day_number: int):
    """Check photo book content coverage for a given day.

    Returns counts of photos, highlights, and diary entries.
    """
    if day_number < 1 or day_number > 17:
        raise HTTPException(status_code=400, detail="day_number must be 1-17")

    headers = _japan_supabase_headers()
    results = {}

    async with httpx.AsyncClient() as client:
        # Count photos
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/japan_photos",
            headers={**headers, "Prefer": "count=exact"},
            params={"day_number": f"eq.{day_number}", "select": "id"},
        )
        results["photos"] = int(resp.headers.get("content-range", "*/0").split("/")[-1])

        # Count highlights
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/japan_highlights",
            headers={**headers, "Prefer": "count=exact"},
            params={"day_number": f"eq.{day_number}", "select": "id"},
        )
        results["highlights"] = int(resp.headers.get("content-range", "*/0").split("/")[-1])

        # Count diary entries
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/japan_diary",
            headers={**headers, "Prefer": "count=exact"},
            params={"day_number": f"eq.{day_number}", "select": "id"},
        )
        results["diary_entries"] = int(resp.headers.get("content-range", "*/0").split("/")[-1])

    results["day_number"] = day_number
    results["city"] = DAY_TO_CITY.get(day_number, "")
    results["has_enough"] = results["photos"] >= 5 and (results["highlights"] > 0 or results["diary_entries"] > 0)

    return results


@router.post("/sim/time")
async def set_sim_time(request: Request):
    """Set simulated JST time for alert testing. Body: {"time": "12:00"} or {"time": ""} to clear."""
    body = await request.json()
    time_val = body.get("time", "")
    time_file = Path(__file__).parent.parent / "data" / "japan_sim_time.txt"
    time_file.write_text(time_val)
    if time_val:
        return {"status": "sim_time_active", "time": time_val}
    return {"status": "sim_time_cleared"}


@router.post("/alerts/test")
async def test_alerts(request: Request):
    """Dry-run alert check. Shows what alerts would fire without sending.

    Body: {"date": "2026-04-09", "time": "12:00"} (optional overrides)
    """
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    date_val = body.get("date", "")
    time_val = body.get("time", "")

    # Temporarily set sim files
    sim_file = Path(__file__).parent.parent / "data" / "japan_sim_date.txt"
    time_file = Path(__file__).parent.parent / "data" / "japan_sim_time.txt"

    old_date = sim_file.read_text().strip() if sim_file.exists() else ""
    old_time = time_file.read_text().strip() if time_file.exists() else ""

    try:
        if date_val:
            sim_file.write_text(date_val)
        if time_val:
            time_file.write_text(time_val)

        from domains.peterbot.japan_alerts import check_and_send_alerts
        alerts = await check_and_send_alerts(dry_run=True)

        return {
            "sim_date": date_val or old_date or "real",
            "sim_time": time_val or old_time or "real",
            "alerts_count": len(alerts),
            "alerts": alerts,
        }
    finally:
        # Restore original sim state
        sim_file.write_text(old_date)
        time_file.write_text(old_time)


@router.get("/trains/status")
async def train_status(city: str = "all"):
    """Check live train status for Japanese rail networks.

    Query params: ?city=tokyo|osaka|kyoto|all
    """
    from hadley_api.japan_train_status import get_train_status
    return await get_train_status(city)


@router.post("/alerts/send")
async def send_alerts_now():
    """Manually trigger alert check and send any pending alerts."""
    from domains.peterbot.japan_alerts import check_and_send_alerts
    alerts = await check_and_send_alerts(dry_run=False)
    return {"sent": len(alerts), "alerts": alerts}


# ============================================================
# Expense Tracking
# ============================================================

@router.post("/expenses")
async def add_expense(request: Request):
    """Add an expense to japan_expenses table.

    Body: {
        "amount": 3200,
        "currency": "JPY",
        "category": "food",
        "description": "Kushikatsu Daruma lunch",
        "payment_method": "cash",
        "day_date": "2026-04-07"  (optional, defaults to today JST)
    }

    Categories: food, transport, attraction, shopping, accommodation, cash_withdrawal, other
    Payment methods: card, cash, ic_card
    """
    body = await request.json()
    amount = body.get("amount")
    if not amount or float(amount) <= 0:
        raise HTTPException(status_code=400, detail="amount is required and must be > 0")

    # Default date to today JST
    day_date = body.get("day_date")
    if not day_date:
        day_date = datetime.now(JAPAN_TZ).strftime("%Y-%m-%d")

    expense = {
        "day_date": day_date,
        "amount": float(amount),
        "currency": body.get("currency", "JPY"),
        "category": body.get("category", "other"),
        "description": body.get("description", ""),
        "payment_method": body.get("payment_method", "cash"),
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/japan_expenses",
            headers={
                **_supabase_headers(),
                "Content-Profile": "japan",
                "Accept-Profile": "japan",
                "Prefer": "return=representation",
            },
            json=expense,
        )

    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    gbp = round(expense["amount"] / 200) if expense["currency"] == "JPY" else expense["amount"]
    return {
        "status": "logged",
        "amount": expense["amount"],
        "currency": expense["currency"],
        "gbp_approx": gbp,
        "category": expense["category"],
        "description": expense["description"],
        "day_date": day_date,
    }


# ============================================================
# Photo Book Compilation
# ============================================================


@router.get("/photobook/compile")
async def photobook_compile():
    """Compile all photo book data for all 17 days.

    Returns a JSON payload with photos, highlights, diary entries,
    day plans, and Google Drive thumbnail URLs for each day.
    Designed to feed into the print-ready HTML templates.
    """
    headers = _japan_supabase_headers()
    days = {}

    async with httpx.AsyncClient(timeout=30) as client:
        # Fetch all data in parallel
        photos_resp, highlights_resp, diary_resp, plans_resp = await asyncio.gather(
            client.get(f"{SUPABASE_URL}/rest/v1/japan_photos",
                       headers=headers, params={"select": "*", "order": "created_at.asc"}),
            client.get(f"{SUPABASE_URL}/rest/v1/japan_highlights",
                       headers=headers, params={"select": "*", "order": "created_at.asc"}),
            client.get(f"{SUPABASE_URL}/rest/v1/japan_diary",
                       headers=headers, params={"select": "*", "order": "created_at.asc"}),
            client.get(f"{SUPABASE_URL}/rest/v1/japan_day_plans",
                       headers=headers, params={"select": "day_date,city,stay_name,plan_data", "order": "day_date.asc"}),
        )

    photos = photos_resp.json() if photos_resp.status_code == 200 else []
    highlights = highlights_resp.json() if highlights_resp.status_code == 200 else []
    diary_entries = diary_resp.json() if diary_resp.status_code == 200 else []
    plans = plans_resp.json() if plans_resp.status_code == 200 else []

    # Build plan lookup by day number
    plan_by_day = {}
    for p in plans:
        try:
            dt = datetime.strptime(p["day_date"], "%Y-%m-%d")
            day_num = (dt - datetime(2026, 4, 3)).days + 1
            if 1 <= day_num <= 17:
                plan_by_day[day_num] = p
        except (ValueError, KeyError):
            pass

    # Build per-day structure
    for d in range(1, 18):
        plan = plan_by_day.get(d, {})
        day_photos = [p for p in photos if p.get("day_number") == d]

        # Build Google Drive thumbnail URLs for each photo
        for photo in day_photos:
            fid = photo.get("drive_file_id")
            if fid:
                photo["thumbnail_url"] = f"https://drive.google.com/thumbnail?id={fid}&sz=w800"
                photo["full_url"] = f"https://drive.google.com/uc?id={fid}"

        days[d] = {
            "day_number": d,
            "date": DAY_TO_DATE.get(d, ""),
            "city": DAY_TO_CITY.get(d, ""),
            "stay": plan.get("stay_name", ""),
            "activities": [
                item.get("title", "") for item in (plan.get("plan_data") or [])
                if item.get("title")
            ],
            "photos": day_photos,
            "highlights": [h for h in highlights if h.get("day_number") == d],
            "diary": [e for e in diary_entries if e.get("day_number") == d],
            "photo_count": len(day_photos),
            "highlight_count": len([h for h in highlights if h.get("day_number") == d]),
            "diary_count": len([e for e in diary_entries if e.get("day_number") == d]),
        }

    # Summary stats
    total_photos = sum(d["photo_count"] for d in days.values())
    total_highlights = sum(d["highlight_count"] for d in days.values())
    total_diary = sum(d["diary_count"] for d in days.values())
    days_with_content = sum(1 for d in days.values() if d["photo_count"] > 0 or d["highlight_count"] > 0)

    return {
        "days": days,
        "summary": {
            "total_photos": total_photos,
            "total_highlights": total_highlights,
            "total_diary_entries": total_diary,
            "days_with_content": days_with_content,
            "days_complete": sum(
                1 for d in days.values()
                if d["photo_count"] >= 5 and (d["highlight_count"] > 0 or d["diary_count"] > 0)
            ),
        },
    }


@router.get("/expenses/today")
async def get_today_expenses():
    """Get today's expenses and running total."""
    today = datetime.now(JAPAN_TZ).strftime("%Y-%m-%d")

    # Check sim date
    sim_file = Path(__file__).parent.parent / "data" / "japan_sim_date.txt"
    if sim_file.exists():
        sim = sim_file.read_text().strip()
        if sim:
            today = sim

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/japan_expenses",
            headers={**_supabase_headers(), "Accept-Profile": "japan"},
            params={"select": "*", "day_date": f"eq.{today}", "order": "created_at.asc"},
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    expenses = resp.json()
    total_jpy = sum(e["amount"] if e["currency"] == "JPY" else e["amount"] * 200 for e in expenses)

    return {
        "date": today,
        "count": len(expenses),
        "total_jpy": total_jpy,
        "total_gbp": round(total_jpy / 200),
        "expenses": expenses,
    }
