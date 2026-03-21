"""Japan Trip Context Loader for Peterbot.

Injects Japan trip awareness into WhatsApp conversations during Apr 3-19, 2026.
When active, Peter becomes a location-aware, schedule-aware Japan concierge.

Usage:
    from domains.peterbot.japan_context import get_japan_context
    ctx = get_japan_context()  # auto-detects JST date
    ctx = get_japan_context(sim_date="2026-04-09")  # testing from UK
"""

import json
import os
import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Optional

from logger import logger

JAPAN_TZ = ZoneInfo("Asia/Tokyo")
TRIP_START = datetime(2026, 4, 3)
TRIP_END = datetime(2026, 4, 19)

# Supabase config
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://modjoikyuhqzouxvieua.supabase.co")
SUPABASE_KEY = os.getenv(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1vZGpvaWt5dWhxem91eHZpZXVhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjYxNDE3MjksImV4cCI6MjA4MTcxNzcyOX0.EWGr0LOwFKFw3krrzZQZP_Gcew13s1Z9H3LxB0-JmPA",
)

# Sim mode — set JAPAN_SIM_DATE=2026-04-09 to test from UK
# Can be set via env var OR by writing to the sim file
JAPAN_SIM_DATE = os.getenv("JAPAN_SIM_DATE", "")
_SIM_FILE = Path("C:/Users/Chris Hadley/claude-projects/Discord-Messenger/data/japan_sim_date.txt")


def _get_sim_date() -> str:
    """Get sim date from env var or sim file."""
    if JAPAN_SIM_DATE:
        return JAPAN_SIM_DATE
    if _SIM_FILE.exists():
        try:
            val = _SIM_FILE.read_text().strip()
            if val and len(val) == 10:  # YYYY-MM-DD
                return val
        except Exception:
            pass
    return ""

# Accommodation per day
ACCOMMODATIONS = {
    1: {"name": "Kitashinjuku Apartment", "address": "2-9-9 Kitashinjuku, Shinjuku-ku", "host": "Tokyo Look In", "phone": "+81 90-8784-0766", "lat": 35.6983, "lng": 139.6980, "checkin": "16:00", "checkout": "10:00"},
    2: {"name": "Kitashinjuku Apartment", "address": "2-9-9 Kitashinjuku, Shinjuku-ku", "host": "Tokyo Look In", "phone": "+81 90-8784-0766", "lat": 35.6983, "lng": 139.6980, "checkin": "16:00", "checkout": "10:00"},
    3: {"name": "Kitashinjuku Apartment", "address": "2-9-9 Kitashinjuku, Shinjuku-ku", "host": "Tokyo Look In", "phone": "+81 90-8784-0766", "lat": 35.6983, "lng": 139.6980, "checkin": "16:00", "checkout": "10:00"},
    4: {"name": "Dotonbori Apartment", "address": "2-8-29 Nishishinsaibashi, Chuo-ku, Osaka", "host": "Yoko & Nobu", "phone": "+81 6-7656-0359", "lat": 34.6694, "lng": 135.4997, "checkin": "16:00", "checkout": "10:00"},
    5: {"name": "Dotonbori Apartment", "address": "2-8-29 Nishishinsaibashi, Chuo-ku, Osaka", "host": "Yoko & Nobu", "phone": "+81 6-7656-0359", "lat": 34.6694, "lng": 135.4997, "checkin": "16:00", "checkout": "10:00"},
    6: {"name": "Dotonbori Apartment", "address": "2-8-29 Nishishinsaibashi, Chuo-ku, Osaka", "host": "Yoko & Nobu", "phone": "+81 6-7656-0359", "lat": 34.6694, "lng": 135.4997, "checkin": "16:00", "checkout": "10:00"},
    7: {"name": "Dotonbori Apartment", "address": "2-8-29 Nishishinsaibashi, Chuo-ku, Osaka", "host": "Yoko & Nobu", "phone": "+81 6-7656-0359", "lat": 34.6694, "lng": 135.4997, "checkin": "16:00", "checkout": "10:00"},
    8: {"name": "Kyoto Machiya", "address": "Shimogyo Ward, Kyoto", "host": "Team LUX", "phone": "", "lat": 35.0050, "lng": 135.7590, "checkin": "15:00", "checkout": "11:00"},
    9: {"name": "Kyoto Machiya", "address": "Shimogyo Ward, Kyoto", "host": "Team LUX", "phone": "", "lat": 35.0050, "lng": 135.7590, "checkin": "15:00", "checkout": "11:00"},
    10: {"name": "Kyoto Machiya", "address": "Shimogyo Ward, Kyoto", "host": "Team LUX", "phone": "", "lat": 35.0050, "lng": 135.7590, "checkin": "15:00", "checkout": "11:00"},
    11: {"name": "Kyoto Machiya", "address": "Shimogyo Ward, Kyoto", "host": "Team LUX", "phone": "", "lat": 35.0050, "lng": 135.7590, "checkin": "15:00", "checkout": "11:00"},
    12: {"name": "Nezu Apartment", "address": "Near Nezu Station, Bunkyo-ku", "host": "Toshiko", "phone": "", "lat": 35.7206, "lng": 139.7631, "checkin": "15:00", "checkout": "11:00"},
    13: {"name": "Nezu Apartment", "address": "Near Nezu Station, Bunkyo-ku", "host": "Toshiko", "phone": "", "lat": 35.7206, "lng": 139.7631, "checkin": "15:00", "checkout": "11:00"},
    14: {"name": "Nezu Apartment", "address": "Near Nezu Station, Bunkyo-ku", "host": "Toshiko", "phone": "", "lat": 35.7206, "lng": 139.7631, "checkin": "15:00", "checkout": "11:00"},
    15: {"name": "Nezu Apartment", "address": "Near Nezu Station, Bunkyo-ku", "host": "Toshiko", "phone": "", "lat": 35.7206, "lng": 139.7631, "checkin": "15:00", "checkout": "11:00"},
    16: {"name": "Nezu Apartment", "address": "Near Nezu Station, Bunkyo-ku", "host": "Toshiko", "phone": "", "lat": 35.7206, "lng": 139.7631, "checkin": "15:00", "checkout": "11:00"},
    17: {"name": "Departure", "address": "Haneda Airport", "host": "", "phone": "", "lat": 35.5494, "lng": 139.7798, "checkin": "", "checkout": ""},
}

FESTIVALS = {
    "04-03": "Arrival day! Seiryu-e in Kyoto (miss — on a plane)",
    "04-04": "Tohoku Food Festival near accommodation",
    "04-05": "Tohoku Food Festival (last day). Chidorigafuchi Illuminations evening (6-10pm)",
    "04-06": "Travel to Osaka",
    "04-07": "USJ Cool Japan 2026 running",
    "04-08": "Nara day trip. Hana Matsuri at temples",
    "04-09": "Watch mint.go.jp for Mint Bureau announcement",
    "04-10": "Himeji to Kyoto. HIRANO SHRINE OKA-SAI (Procession 1pm, Illuminations 6-9pm)",
    "04-11": "Consider Miyako Odori evening show",
    "04-12": "Kyoto exploring",
    "04-13": "teamLab Biovortex 9am THEN Yasurai Festival noon — Can do BOTH!",
    "04-14": "Travel to Tokyo 2",
    "04-15": "DisneySea 25th Sparkling Jubilee LAUNCHES",
    "04-16": "Nezu Shrine azaleas (steps from stay)",
    "04-17": "Craft Sake Week opens. Nezu Shrine continues",
    "04-18": "Tohoku Food Festival (second run!). Craft Sake Week. LAST FULL DAY.",
    "04-19": "Red-eye departure 01:30",
}

# Cache for day plan (avoid repeated Supabase calls)
_day_plan_cache: dict = {}
_restaurants_cache: list | None = None


def _haversine_km(lat1, lng1, lat2, lng2) -> float:
    R = 6371
    dLat = math.radians(lat2 - lat1)
    dLng = math.radians(lng2 - lng1)
    a = math.sin(dLat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _fetch_day_plan(date_str: str) -> dict | None:
    """Fetch day plan from Supabase (cached)."""
    if date_str in _day_plan_cache:
        cached_at, data = _day_plan_cache[date_str]
        if (datetime.now() - cached_at).total_seconds() < 3600:
            return data

    try:
        import httpx
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Accept-Profile": "japan",
        }
        resp = httpx.get(
            f"{SUPABASE_URL}/rest/v1/japan_day_plans",
            headers=headers,
            params={"select": "*", "day_date": f"eq.{date_str}"},
            timeout=10,
        )
        if resp.status_code == 200 and resp.json():
            plan = resp.json()[0]
            _day_plan_cache[date_str] = (datetime.now(), plan)
            return plan
    except Exception as e:
        logger.debug(f"Japan context: failed to fetch day plan: {e}")
    return None


def _fetch_bookings(date_str: str) -> list:
    """Fetch bookings for a date from Supabase."""
    try:
        import httpx
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Accept-Profile": "japan",
        }
        resp = httpx.get(
            f"{SUPABASE_URL}/rest/v1/japan_bookings",
            headers=headers,
            params={"select": "*", "day_date": f"eq.{date_str}"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.debug(f"Japan context: failed to fetch bookings: {e}")
    return []


def _load_restaurants_near(lat: float, lng: float, limit: int = 30) -> list[dict]:
    """Load nearest restaurants from restaurants.json (cached)."""
    global _restaurants_cache

    if _restaurants_cache is None:
        # Direct path to japan-family-guide project
        json_path = Path("C:/Users/Chris Hadley/claude-projects/japan-family-guide/site/restaurants.json")
        if json_path.exists():
            try:
                with open(json_path, encoding="utf-8") as f:
                    _restaurants_cache = json.load(f)
                logger.info(f"Japan context: loaded {len(_restaurants_cache)} restaurants")
            except Exception as e:
                logger.error(f"Japan context: failed to load restaurants: {e}")
                _restaurants_cache = []
        else:
            _restaurants_cache = []

    if not _restaurants_cache:
        return []

    # Filter to entries with coords and known_for, then sort by distance
    candidates = [
        r for r in _restaurants_cache
        if r.get("lat") and r.get("lng") and r.get("known_for")
        and r.get("cuisine", "") not in ("Coffee", "Cafe", "🍞 Bakery", "🍨 Dessert")
    ]
    for r in candidates:
        r["_dist"] = _haversine_km(lat, lng, r["lat"], r["lng"])

    candidates.sort(key=lambda r: r["_dist"])
    return candidates[:limit]


def _load_food_picks() -> list[dict]:
    """Load food picks from food-picks.json."""
    json_path = Path("C:/Users/Chris Hadley/claude-projects/japan-family-guide/site/food-picks.json")
    if json_path.exists():
        try:
            with open(json_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.debug(f"Japan context: failed to load food picks: {e}")
    return []


def get_japan_context(sim_date: str | None = None) -> str:
    """Build Japan trip context for today's date.

    Args:
        sim_date: Optional "YYYY-MM-DD" override for testing (or use JAPAN_SIM_DATE env var)

    Returns:
        Markdown context string, or "" if not during the trip
    """
    # Determine today's date
    date_override = sim_date or _get_sim_date()
    if date_override:
        try:
            today = datetime.strptime(date_override, "%Y-%m-%d")
            date_str = date_override
        except ValueError:
            return ""
    else:
        now_jst = datetime.now(JAPAN_TZ)
        today = datetime(now_jst.year, now_jst.month, now_jst.day)
        date_str = today.strftime("%Y-%m-%d")

    # Check if in trip range
    if today < TRIP_START or today > TRIP_END:
        return ""

    trip_day = (today - TRIP_START).days + 1
    day_name = today.strftime("%A")
    day_label = today.strftime("%A, %B %-d" if os.name != "nt" else "%A, %B %#d")

    # Accommodation
    accom = ACCOMMODATIONS.get(trip_day, {})

    # Fetch day plan from Supabase
    plan = _fetch_day_plan(date_str)
    city = plan.get("city", "") if plan else ""
    stay_name = plan.get("stay_name", accom.get("name", "")) if plan else accom.get("name", "")
    items = plan.get("plan_data", []) if plan else []
    notes = plan.get("notes", "") if plan else ""

    # Fetch bookings
    bookings = _fetch_bookings(date_str)

    # Food picks for today
    all_picks = _load_food_picks()
    today_picks = [p for p in all_picks if p.get("day") == trip_day]

    # Nearby restaurants
    nearby = _load_restaurants_near(accom.get("lat", 0), accom.get("lng", 0), limit=30)

    # Festival
    mm_dd = date_str[5:]
    festival = FESTIVALS.get(mm_dd, "")

    # Build context
    parts = []
    parts.append(f"## 🇯🇵 JAPAN TRIP — Day {trip_day} of 17")
    parts.append(f"**{day_label}** · {city} · Staying: {stay_name}")
    parts.append(f"📍 Accommodation: {accom.get('address', '')}")
    if accom.get("host"):
        parts.append(f"🏠 Host: {accom['host']} · Phone: {accom.get('phone', 'N/A')}")
    parts.append("")

    # Festival alert
    if festival:
        parts.append(f"🎌 **Today's Events:** {festival}")
        parts.append("")

    # Today's schedule
    if items:
        parts.append("### Today's Schedule")
        for item in items:
            time_str = item.get("time", "")
            end_time = item.get("end_time", "")
            title = item.get("title", "")
            emoji = item.get("emoji", "")
            location = item.get("location", "")
            item_notes = item.get("notes", "")
            booked = item.get("booked", False)

            time_display = f"{time_str}–{end_time}" if end_time else time_str
            booked_tag = " **[BOOKED]**" if booked else ""
            loc_tag = f" ({location})" if location else ""
            notes_short = f" — {str(item_notes)[:80]}" if item_notes else ""

            parts.append(f"- **{time_display}** {emoji} {title}{booked_tag}{loc_tag}{notes_short}")
        parts.append("")

    # Bookings with details
    if bookings:
        parts.append("### Bookings & Confirmations")
        for b in bookings:
            status = b.get("status", "").upper()
            ref = f" (Ref: {b['confirmation_ref']})" if b.get("confirmation_ref") else ""
            notes_b = f" — {b['notes'][:100]}" if b.get("notes") else ""
            parts.append(f"- **{b.get('activity_title', '')}** [{status}]{ref}{notes_b}")
        parts.append("")

    # Food picks
    if today_picks:
        parts.append("### Planned Food")
        for p in today_picks:
            status = p.get("status", "").upper()
            parts.append(f"- **{p.get('meal', '').title()}:** {p.get('restaurant', '')} ({p.get('food_type', '')}) [{status}] — {p.get('notes', '')[:80]}")
        parts.append("")

    # Day notes
    if notes:
        parts.append(f"### Day Notes")
        parts.append(notes)
        parts.append("")

    # Nearby restaurants (compact)
    if nearby:
        parts.append("### Nearest Restaurants (from accommodation)")
        for r in nearby[:20]:
            score = f" ★{r['tabelog_score']}" if r.get("tabelog_score") else ""
            price = f" {r.get('price_range', '')[:20]}" if r.get("price_range") else ""
            known = f" — {r.get('known_for', '')[:60]}" if r.get("known_for") else ""
            dist = f" ({r['_dist']:.1f}km)" if r.get("_dist") else ""
            parts.append(f"- **{r['name']}**{score}{dist} [{r.get('cuisine', '')}]{price}{known}")
        parts.append("")

    # Practical info
    parts.append("### Practical Info")
    parts.append("- 🚨 Emergency: Police 110 · Ambulance 119 · Tourist helpline 050-3816-2787")
    parts.append("- 💴 Quick conversion: ¥200 ≈ £1")
    parts.append("- 📱 Day Guide: https://hadley-japan-2026.surge.sh/day-{}.html".format(trip_day))
    parts.append("- 🗺️ Food Map: https://hadley-japan-2026.surge.sh/food-map.html")
    parts.append("")

    # Response instructions
    parts.append("### How to respond about Japan")
    parts.append("- You are Peter, the Hadley family's personal concierge for this Japan trip")
    parts.append("- Be concise, practical, and family-friendly (kids Max 7, Emmie 9)")
    parts.append("- Prices in ¥ with £ equivalent (¥200 ≈ £1)")
    parts.append("- If asked about food, check the planned food picks first, then suggest from nearby restaurants")
    parts.append("- If asked about timing, reference today's schedule")
    parts.append("- If something is BOOKED, mention the ref/details")
    parts.append("- Warn about cash-only places, queue times, and kid-friendliness")
    parts.append("")
    parts.append("### Train Delays")
    parts.append("If asked about train delays or disruptions, direct them to:")
    parts.append("- JR East (Tokyo): https://traininfo.jreast.co.jp/train_info/e/")
    parts.append("- Osaka Metro: https://subway.osakametro.co.jp/guide/operation_status_en.php")
    parts.append("- Kyoto subway/bus: check Google Maps real-time transit")
    parts.append("- General: open Google Maps and check the route — it shows real-time delays")
    parts.append("If a major line is disrupted, suggest alternative routes using other lines.")
    parts.append("")
    parts.append("### Location-Aware Food Finding")
    parts.append("When someone shares their GPS location or asks 'find food near me' with coordinates:")
    parts.append("1. Use the coordinates to identify the nearest restaurants from the list above")
    parts.append("2. Calculate approximate walking distance (1km ≈ 12 min walk)")
    parts.append("3. Prioritise: kid-friendly places, food types not yet tried on the trip, Tabelog scores ≥ 3.5")
    parts.append("4. Suggest 3 options with: name, distance, cuisine type, price, and one-line description")
    parts.append("5. Include a Google Maps link for the top pick")
    parts.append("")
    parts.append("### Expense Logging")
    parts.append("When someone mentions spending money (e.g. 'spent ¥3,200 at Kushikatsu', 'paid ¥500 for train', 'bought souvenirs for ¥2,000'), log it by running:")
    parts.append('```bash')
    parts.append('curl -s -X POST http://172.19.64.1:8100/japan/expenses -H "Content-Type: application/json" -d \'{"amount": AMOUNT, "currency": "JPY", "category": "CATEGORY", "description": "DESCRIPTION", "payment_method": "METHOD"}\'')
    parts.append('```')
    parts.append("Categories: food, transport, attraction, shopping, accommodation, cash_withdrawal, other")
    parts.append("Payment methods: card, cash, ic_card")
    parts.append("After logging, confirm with a brief message like '✅ Logged ¥3,200 for Kushikatsu (food, cash). Today's total: check /japan/expenses/today'")
    parts.append("If they don't specify payment method, ask 'Cash or card?' or default to cash for food under ¥5,000")
    parts.append("")

    return "\n".join(parts)
